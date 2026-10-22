"""실행영역 로컬 봉인·비교: 캡처 원문을 민감값 제거 근거로 봉인하고 저장·감사한다.

원문/캡처 핸들/run HMAC 키는 이 영역 밖으로 반환·전송·로그하지 않는다. StoredComparison과
ComparisonProjected는 저장 영수증과 생산자 감사가 모두 확인된 COMPLETE에서만 발행한다.
정규화·canary 규칙은 주입된 엔진(judge 소유)이 수행하며 HMAC 일치만으로 비자명 일치를
단정하지 않는다(s1-api-spec §7, evidence-c3-freeze §2~5).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from hashlib import sha256

from abc2lab_contracts.audit import AuditEventKind, AuditRecordBinding
from abc2lab_contracts.capture import CaptureRequest, RawResponse, ReleaseCapturesRequest
from abc2lab_contracts.evidence import (
    ArtifactKind,
    CompareOutcome,
    CompareRequest,
    ComparisonPayload,
    ComparisonProjected,
    ComparisonSignals,
    EvidenceSubmissionKind,
    EvidenceSummary,
    RecoverSubmissionRequest,
    RedactedBundle,
    SealRequest,
    SealResult,
    StoredComparison,
    StoreReceipt,
)
from abc2lab_contracts.fingerprint import comparison_fingerprint, evidence_fingerprint
from abc2lab_contracts.ports import EvidencePort
from abc2lab_contracts.primitives import (
    AuditLink,
    CheckState,
    Purpose,
    ReasonCode,
    Ref,
    ResponseClass,
    ResultStatus,
    RunKey,
    SourceVersion,
    UtcTime,
)
from abc2lab_contracts.recipe import RecipeParameter, RegisteredRequestRecipe
from abc2lab_contracts.registration import ComparisonRules
from abc2lab_contracts.session import IdentityResult, IdentityStatus

from abc2lab_evidence.ports import (
    CaptureAccess,
    CaptureRegistry,
    ComparisonRuleEngine,
    EvidenceAuditJournal,
    RunMac,
)

_HTTP_MIN = 100
_HTTP_MAX = 599


@dataclass(frozen=True, slots=True)
class SealerConfig:
    """봉인 생산자의 고정 설정: 생산자 식별·민감값 제거 버전·참조/시각 공급기."""

    producer_ref: Ref
    redaction_version: SourceVersion
    new_ref: Callable[[], Ref]
    now: Callable[[], UtcTime]


@dataclass(frozen=True, slots=True)
class _SubmissionRecord:
    """제출별 내구 기록(슬라이스 인메모리): 종류·바인딩 지문·발행 결과."""

    kind: EvidenceSubmissionKind
    binding: str
    result: SealResult | CompareOutcome


def _find_receipt(
    receipts: Sequence[StoreReceipt], artifact_ref: Ref, kind: ArtifactKind
) -> StoreReceipt | None:
    for receipt in receipts:
        if receipt.artifact_ref == artifact_ref and receipt.artifact_kind is kind:
            return receipt
    return None


class LocalSealer:
    """단일 캡처 봉인과 A/B 교차 비교 봉인을 수행하는 실행영역 로컬 구성요소다."""

    def __init__(
        self,
        captures: CaptureAccess,
        store: EvidencePort,
        engine: ComparisonRuleEngine,
        mac: RunMac,
        journal: EvidenceAuditJournal,
        registry: CaptureRegistry,
        *,
        config: SealerConfig,
    ) -> None:
        """캡처 접근·저장·규칙 엔진·MAC·감사 저널·등록 조회와 생산자 설정을 주입받는다."""
        self._captures = captures
        self._store = store
        self._engine = engine
        self._mac = mac
        self._journal = journal
        self._registry = registry
        self._config = config
        self._submissions: dict[tuple[RunKey, Ref], _SubmissionRecord] = {}

    async def seal(self, request: SealRequest) -> SealResult:
        """제출 멱등: 커밋된 동일 제출은 재캡처 없이 기존 SealResult를 반환한다."""
        key = (request.run_key, request.submission_ref)
        binding = self._seal_binding(request)
        record = self._submissions.get(key)
        if record is not None:
            if record.kind is EvidenceSubmissionKind.SEAL and record.binding == binding:
                if isinstance(record.result, SealResult):
                    return record.result
            return self._failed_seal(request.run_key, ReasonCode.IDEMPOTENCY_CONFLICT)
        result = await self._run_seal(request)
        self._record(key, EvidenceSubmissionKind.SEAL, binding, result)
        return result

    async def compare_and_seal(self, request: CompareRequest) -> CompareOutcome:
        """제출 멱등: 커밋된 동일 제출은 재캡처 없이 기존 CompareOutcome을 반환한다."""
        key = (request.run_key, request.submission_ref)
        binding = self._compare_binding(request)
        record = self._submissions.get(key)
        if record is not None:
            if record.kind is EvidenceSubmissionKind.COMPARE and record.binding == binding:
                if isinstance(record.result, CompareOutcome):
                    return record.result
            return self._compare_failed(request.run_key, ReasonCode.IDEMPOTENCY_CONFLICT)
        result = await self._run_compare(request)
        self._record(key, EvidenceSubmissionKind.COMPARE, binding, result)
        return result

    async def recover_submission(
        self, request: RecoverSubmissionRequest
    ) -> SealResult | CompareOutcome:
        """캡처 재취득·대상 재전송 없이 커밋된 제출의 현재 상태를 재조회한다."""
        record = self._submissions.get((request.run_key, request.submission_ref))
        if record is None:
            return self._failed_for(request.kind, request.run_key, ReasonCode.NOT_FOUND)
        if record.kind is not request.kind:
            return self._failed_for(request.kind, request.run_key, ReasonCode.IDEMPOTENCY_CONFLICT)
        return record.result

    def _record(
        self,
        key: tuple[RunKey, Ref],
        kind: EvidenceSubmissionKind,
        binding: str,
        result: SealResult | CompareOutcome,
    ) -> None:
        # 내구 artifact(성공 receipt)가 생긴 제출만 기록한다. 최초 기록 전 실패는 남기지 않는다.
        if result.receipts:
            self._submissions[key] = _SubmissionRecord(kind, binding, result)

    def _failed_seal(self, run_key: RunKey, reason: ReasonCode) -> SealResult:
        return SealResult(run_key, ResultStatus.FAILED, None, (), (reason,))

    def _failed_for(
        self, kind: EvidenceSubmissionKind, run_key: RunKey, reason: ReasonCode
    ) -> SealResult | CompareOutcome:
        if kind is EvidenceSubmissionKind.SEAL:
            return self._failed_seal(run_key, reason)
        return self._compare_failed(run_key, reason)

    def _seal_binding(self, request: SealRequest) -> str:
        return _submission_fingerprint(("seal", request.capture_ref, *_rules_parts(request.rules)))

    def _compare_binding(self, request: CompareRequest) -> str:
        return _submission_fingerprint(
            (
                "compare",
                request.owner_capture_ref,
                request.cross_capture_ref,
                request.resource_ref,
                request.operation_ref,
                request.case_ref,
                request.owner_identity.identity_ref or "",
                request.evaluated_identity.identity_ref or "",
                *_rules_parts(request.rules),
            )
        )

    async def _run_seal(self, request: SealRequest) -> SealResult:
        """캡처를 민감값 제거 근거로 봉인·저장·감사하고 완료 시 Evidence를 반환한다."""
        capture = self._captures.acquire(request.run_key, request.capture_ref)
        if capture is None:
            return SealResult(
                request.run_key, ResultStatus.FAILED, None, (), (ReasonCode.CAPTURE_EXPIRED,)
            )
        try:
            summary = self._build_summary(capture)
            if summary is None:
                return SealResult(
                    request.run_key,
                    ResultStatus.FAILED,
                    None,
                    (),
                    (ReasonCode.CAPTURE_UNAVAILABLE,),
                )
            bundle = RedactedBundle(
                request.run_key,
                request.submission_ref,
                (summary,),
                None,
                self._config.redaction_version,
            )
            outcome = await self._store.store_evidence(bundle)
            receipt = _find_receipt(outcome.receipts, summary.evidence_ref, ArtifactKind.EVIDENCE)
            if receipt is None:
                reasons = outcome.reason_codes or (ReasonCode.EVIDENCE_STORE_FAILED,)
                return SealResult(request.run_key, ResultStatus.FAILED, None, (), reasons)
            event_ref = summary.source_event.event_ref
            binding = self._evidence_binding(summary)
            audit = await self._journal.commit(
                request.run_key, self._config.producer_ref, event_ref, binding
            )
            if audit is None:
                return SealResult(
                    request.run_key,
                    ResultStatus.PARTIAL,
                    None,
                    (receipt,),
                    (ReasonCode.AUDIT_COMMIT_FAILED,),
                )
            return SealResult(request.run_key, ResultStatus.COMPLETE, summary, (receipt,), ())
        finally:
            self._captures.release_captures(
                ReleaseCapturesRequest(request.run_key, (request.capture_ref,))
            )

    async def _run_compare(self, request: CompareRequest) -> CompareOutcome:
        """A/B 캡처를 비교·봉인하고 세 저장·감사가 모두 확인되면 완료 비교를 발행한다."""
        owner = self._captures.acquire(request.run_key, request.owner_capture_ref)
        cross = self._captures.acquire(request.run_key, request.cross_capture_ref)
        try:
            if owner is None or cross is None:
                return self._compare_failed(request.run_key, ReasonCode.CAPTURE_EXPIRED)
            owner_id = request.owner_identity.identity_ref
            evaluated_id = request.evaluated_identity.identity_ref
            if owner_id is None or evaluated_id is None:
                return self._compare_failed(request.run_key, ReasonCode.IDENTITY_UNKNOWN)
            owner_summary = self._build_summary(owner)
            cross_summary = self._build_summary(cross)
            if owner_summary is None or cross_summary is None:
                return self._compare_failed(request.run_key, ReasonCode.CAPTURE_UNAVAILABLE)
            payload = ComparisonPayload(
                run_key=request.run_key,
                comparison_ref=self._config.new_ref(),
                case_ref=request.case_ref,
                resource_ref=request.resource_ref,
                operation_ref=request.operation_ref,
                owner_evidence_ref=owner_summary.evidence_ref,
                cross_evidence_ref=cross_summary.evidence_ref,
                owner_identity_ref=owner_id,
                evaluated_identity_ref=evaluated_id,
                signals=self._signals(request, owner, cross),
                rules=request.rules,
            )
            bundle = RedactedBundle(
                request.run_key,
                request.submission_ref,
                (owner_summary, cross_summary),
                payload,
                self._config.redaction_version,
            )
            outcome = await self._store.store_evidence(bundle)
            stored = self._assemble_stored(payload, owner_summary, cross_summary, outcome.receipts)
            if stored is None:
                reasons = outcome.reason_codes or (ReasonCode.COMPARISON_INCOMPLETE,)
                return CompareOutcome(
                    request.run_key,
                    _incomplete_status(outcome.receipts),
                    None,
                    None,
                    outcome.receipts,
                    reasons,
                )
            projection = await self._project(
                request.run_key, payload, owner_summary, cross_summary, stored
            )
            if projection is None:
                return CompareOutcome(
                    request.run_key,
                    ResultStatus.PARTIAL,
                    None,
                    None,
                    stored.receipts,
                    (ReasonCode.AUDIT_COMMIT_FAILED,),
                )
            return CompareOutcome(
                request.run_key, ResultStatus.COMPLETE, stored, projection, stored.receipts, ()
            )
        finally:
            self._release(request.run_key, (request.owner_capture_ref, request.cross_capture_ref))

    def _build_summary(self, capture: CaptureRequest) -> EvidenceSummary | None:
        status = capture.raw_response.status_code
        if not _HTTP_MIN <= status <= _HTTP_MAX:
            return None
        recipe, recipe_reasons = self._build_recipe(capture)
        event_ref = self._config.new_ref()
        return EvidenceSummary(
            run_key=capture.run_key,
            evidence_ref=self._config.new_ref(),
            attempt_ref=capture.attempt_ref,
            operation_ref=capture.operation_ref,
            resource_ref=capture.resource_ref,
            account_ref=capture.account_ref,
            session_generation=capture.session_generation,
            identity_ref=capture.identity_ref,
            response_class=self._engine.classify(capture.raw_response),
            http_status=status,
            observed_at=capture.observed_at,
            redaction_version=self._config.redaction_version,
            source_event=AuditLink(self._config.producer_ref, event_ref),
            request_recipe=recipe,
            recipe_reason_codes=recipe_reasons,
        )

    def _build_recipe(
        self, capture: CaptureRequest
    ) -> tuple[RegisteredRequestRecipe | None, tuple[ReasonCode, ...]]:
        """등록 동작/바인딩을 placeholder 레시피로 변환한다(실제 값·origin 미포함)."""
        view = capture.executed_request
        if view.purpose not in (Purpose.OBSERVE, Purpose.ACCESS_COMPARE) or view.method != "GET":
            return None, (ReasonCode.RECIPE_UNSUPPORTED,)
        resource_ref = capture.resource_ref
        binding_ref = view.resource_binding_ref
        binding_revision = view.resource_binding_revision
        if resource_ref is None or binding_ref is None or binding_revision is None:
            return None, (ReasonCode.RECIPE_UNSUPPORTED,)
        operation = self._registry.operation(view.operation_ref)
        binding = self._registry.resource_binding(binding_ref)
        if operation is None or binding is None:
            return None, (ReasonCode.RECIPE_MISSING,)
        try:
            parameters = tuple(
                RecipeParameter(item.name, item.location, _placeholder(item.name))
                for item in binding.parameters
            )
            recipe = RegisteredRequestRecipe(
                schema_version="poc.v0.1",
                operation_ref=view.operation_ref,
                operation_revision=view.operation_revision,
                resource_ref=resource_ref,
                resource_binding_ref=binding_ref,
                resource_binding_revision=binding_revision,
                method="GET",
                origin_placeholder="${REGISTERED_ORIGIN}",
                path_template=operation.path_template,
                parameters=parameters,
                authentication="fresh_registered_session",
                source=operation.source,
            )
        except ValueError:
            # 등록 경로/슬롯을 안전한 placeholder로 공개할 수 없으면 비공개로 둔다.
            return None, (ReasonCode.RECIPE_NOT_EXPORTABLE,)
        return recipe, ()

    def _signals(
        self, request: CompareRequest, owner: CaptureRequest, cross: CaptureRequest
    ) -> ComparisonSignals:
        owner_normal = self._normal(owner.raw_response)
        cross_normal = self._normal(cross.raw_response)
        same_resource = (
            CheckState.YES
            if owner.resource_ref == request.resource_ref
            and cross.resource_ref == request.resource_ref
            else CheckState.NO
        )
        owner_mac = self._mac.compute(request.run_key, self._engine.normalize(owner.raw_response))
        cross_mac = self._mac.compute(request.run_key, self._engine.normalize(cross.raw_response))
        data = self._engine.assess_data(
            owner.raw_response, cross.raw_response, hmac_match=owner_mac == cross_mac
        )
        return ComparisonSignals(
            same_resource=same_resource,
            distinct_verified_subjects=_distinct_subjects(
                request.owner_identity, request.evaluated_identity
            ),
            owner_normal_data=owner_normal,
            cross_normal_data=cross_normal,
            nontrivial_data_match=data.nontrivial_data_match,
            reflection_excluded=data.reflection_excluded,
            template_excluded=data.template_excluded,
        )

    def _normal(self, raw: RawResponse) -> CheckState:
        return (
            CheckState.YES if self._engine.classify(raw) is ResponseClass.NORMAL else CheckState.NO
        )

    def _assemble_stored(
        self,
        payload: ComparisonPayload,
        owner_summary: EvidenceSummary,
        cross_summary: EvidenceSummary,
        receipts: Sequence[StoreReceipt],
    ) -> StoredComparison | None:
        owner_r = _find_receipt(receipts, owner_summary.evidence_ref, ArtifactKind.EVIDENCE)
        cross_r = _find_receipt(receipts, cross_summary.evidence_ref, ArtifactKind.EVIDENCE)
        comparison_r = _find_receipt(receipts, payload.comparison_ref, ArtifactKind.COMPARISON)
        if owner_r is None or cross_r is None or comparison_r is None:
            return None
        return StoredComparison(payload, (owner_r, cross_r, comparison_r))

    async def _project(
        self,
        run_key: RunKey,
        payload: ComparisonPayload,
        owner_summary: EvidenceSummary,
        cross_summary: EvidenceSummary,
        stored: StoredComparison,
    ) -> ComparisonProjected | None:
        producer = self._config.producer_ref
        owner_audit = await self._journal.commit(
            run_key,
            producer,
            owner_summary.source_event.event_ref,
            self._evidence_binding(owner_summary),
        )
        cross_audit = await self._journal.commit(
            run_key,
            producer,
            cross_summary.source_event.event_ref,
            self._evidence_binding(cross_summary),
        )
        comparison_event = self._config.new_ref()
        comparison_audit = await self._journal.commit(
            run_key, producer, comparison_event, self._comparison_binding(payload)
        )
        if owner_audit is None or cross_audit is None or comparison_audit is None:
            return None
        return ComparisonProjected(
            kind=AuditEventKind.COMPARISON,
            event_ref=comparison_event,
            run_key=run_key,
            producer=producer,
            source_revision=1,
            source_receipt=comparison_audit,
            comparison=stored,
        )

    def _evidence_binding(self, summary: EvidenceSummary) -> AuditRecordBinding:
        return AuditRecordBinding(
            event_kind=AuditEventKind.EVIDENCE,
            record_ref=summary.evidence_ref,
            record_revision=1,
            record_fingerprint=evidence_fingerprint(summary),
            request_ref=None,
            attempt_ref=summary.attempt_ref,
            binding_id=None,
        )

    def _comparison_binding(self, payload: ComparisonPayload) -> AuditRecordBinding:
        return AuditRecordBinding(
            event_kind=AuditEventKind.COMPARISON,
            record_ref=payload.comparison_ref,
            record_revision=1,
            record_fingerprint=comparison_fingerprint(payload),
            request_ref=None,
            attempt_ref=None,
            binding_id=None,
        )

    def _compare_failed(self, run_key: RunKey, reason: ReasonCode) -> CompareOutcome:
        return CompareOutcome(run_key, ResultStatus.FAILED, None, None, (), (reason,))

    def _release(self, run_key: RunKey, capture_refs: tuple[Ref, ...]) -> None:
        self._captures.release_captures(ReleaseCapturesRequest(run_key, capture_refs))


def _placeholder(name: str) -> str:
    """등록 매개변수 이름을 공개 가능한 ${SLOT} placeholder로 바꾼다(실제 값 제외)."""
    token = re.sub(r"[^A-Z0-9_]", "_", name.upper())
    return f"${{{token}}}"


def _incomplete_status(receipts: Sequence[StoreReceipt]) -> ResultStatus:
    return ResultStatus.PARTIAL if receipts else ResultStatus.FAILED


def _rules_parts(rules: ComparisonRules) -> tuple[str, ...]:
    return (
        rules.source.issuer,
        rules.source.source_ref,
        str(rules.source.revision),
        rules.normalizer_ref,
        rules.oracle_ref,
        rules.canary_profile_ref,
    )


def _submission_fingerprint(parts: tuple[str, ...]) -> str:
    # 원문 capture_ref가 아니라 도메인 분리 지문만 기록해 제출 충돌을 대조한다.
    joined = "\x1f".join(parts)
    return sha256(f"evidence.submission.v1\x1f{joined}".encode()).hexdigest()


def _distinct_subjects(owner: IdentityResult, evaluated: IdentityResult) -> CheckState:
    if (
        owner.status is IdentityStatus.VERIFIED
        and evaluated.status is IdentityStatus.VERIFIED
        and owner.subject_ref is not None
        and evaluated.subject_ref is not None
    ):
        return CheckState.YES if owner.subject_ref != evaluated.subject_ref else CheckState.NO
    return CheckState.UNKNOWN
