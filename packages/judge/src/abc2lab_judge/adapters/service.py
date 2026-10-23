"""judge의 공개 `JudgePort` 제공자와 판정 발행 어댑터.

`JudgeService.judge`는 호출자 입력을 믿지 않는다. 매 호출 인가 → submission 멱등 확인 → 정본 정책
조회 → EvidencePort에서 비교·근거 읽기 → 감사 검증(독립 재계산·attestation) → 대응 관계 대조 →
오라클 판정 → 발행 순서로 진행하고, 입력 관문이 하나라도 실패하면 commit 없이 FAILED를 낸다. 판정이
났으면 값과 무관하게 COMPLETE이며 호출 사유는 비운다(진단 사유는 Verdict 안에 둔다).

발행(C4 계약 §3)은 event_ref 선고정 → `Verdict` 구성 → `verdict_fingerprint` → journal commit →
영수증 → `verify_committed`(저장 내용에서 재계산 대조) → `VerdictProjected` 순서다. 전송·저장·판정
상태를 꾸미지 않고, 자동 재시도·재발행을 하지 않는다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from abc2lab_contracts.audit import AuditEventKind, AuditVerifyRequest, VerificationState
from abc2lab_contracts.judge import JudgePolicyReadRequest, JudgeRequest, JudgeResult
from abc2lab_contracts.ports import AuditVerifier, EvidencePort, JudgePolicyReader
from abc2lab_contracts.primitives import ReasonCode, Ref, ResultStatus, RunKey, SourceVersion
from abc2lab_contracts.projection import VerdictProjected
from abc2lab_contracts.registration import ComparisonRules, ExpectedAccessPolicySnapshot

from abc2lab_judge.adapters.attestation import (
    DEFAULT_AUDIT_MAX_PAGES,
    DEFAULT_AUDIT_PAGE_LIMIT,
    AuditSource,
    CallFailure,
    LoadedComparison,
    ScanScope,
    attest_comparison,
    keep_failure_reasons,
    load_comparison,
    source_mismatch,
    verify_identity,
)
from abc2lab_judge.adapters.correspondence import CaseRecords, check_correspondence
from abc2lab_judge.adapters.distill import JudgmentInputs, distill_case
from abc2lab_judge.adapters.idempotency import (
    InMemorySubmissionStore,
    SemanticInput,
    StoredSubmission,
)
from abc2lab_judge.adapters.journal import (
    JournalCommitError,
    VerdictJournal,
    verdict_record_binding,
)
from abc2lab_judge.adapters.ports import JudgeReadAuthorizer
from abc2lab_judge.adapters.translation import VerdictContext, to_verdict
from abc2lab_judge.core.model import OracleVerdict, VerdictValue
from abc2lab_judge.core.oracle import evaluate_case

_LOGGER = logging.getLogger(__name__)


def new_event_ref(producer: Ref, run_key: RunKey) -> Ref:
    """다른 판정과 겹치지 않는 새 감사 event_ref를 만든다(commit 전에 고정한다)."""
    return f"{producer}:{run_key.run_ref}:{uuid4().hex}"


class VerdictPublisher:
    """내부 판정을 공개 `Verdict`로 발행하고 commit·검증한 `VerdictProjected`를 낸다."""

    def __init__(
        self,
        journal: VerdictJournal,
        producer: Ref,
        *,
        event_ref_factory: Callable[[Ref, RunKey], Ref] = new_event_ref,
    ) -> None:
        self._journal = journal
        self._producer = producer
        self._new_event_ref = event_ref_factory

    async def publish(
        self, oracle: OracleVerdict, context: VerdictContext, *, occurred_at: datetime
    ) -> VerdictProjected:
        """판정을 발행하고 저장을 검증한 투영 이벤트를 반환한다.

        `occurred_at`은 Judge 감사 이벤트 발생 시각으로 journal에 그대로 보존한다.

        Raises:
            ValueError: 미확정 판정인데 공개 사유가 하나도 없다(`Verdict` 생성자가 거부). 계약 사유
                코드 부재를 채움용 코드로 막지 않고 그대로 드러낸다.
            JournalCommitError: commit·검증을 확인하지 못했다. `reason_code`에 계약 사유를 담는다.
        """
        event_ref = self._new_event_ref(self._producer, context.run_key)
        verdict = to_verdict(oracle, context, producer=self._producer, event_ref=event_ref)

        receipt = await self._journal.append(verdict, occurred_at=occurred_at)
        expected = verdict_record_binding(verdict)
        if receipt.run_key != verdict.run_key or receipt.binding != expected:
            _log_failure("receipt mismatch", verdict.verdict_ref, ReasonCode.AUDIT_COMMIT_FAILED)
            raise JournalCommitError(
                "journal returned a receipt for another record",
                reason_code=ReasonCode.AUDIT_COMMIT_FAILED,
            )

        verification = await self._journal.verify_committed(
            AuditVerifyRequest(run_key=verdict.run_key, receipt=receipt, expected=expected)
        )
        verified = (
            verification.run_key == verdict.run_key
            and verification.state is VerificationState.VERIFIED
        )
        if not verified:
            reason = (
                ReasonCode.AUDIT_VERIFICATION_UNKNOWN
                if verification.state is VerificationState.UNKNOWN
                else ReasonCode.AUDIT_COMMIT_FAILED
            )
            _log_failure("verification failed", verdict.verdict_ref, reason)
            raise JournalCommitError("verdict commit verification failed", reason_code=reason)

        _LOGGER.info(
            "judge verdict committed: run=%s verdict=%s revision=%s value=%s",
            verdict.run_key.run_ref,
            verdict.verdict_ref,
            verdict.revision,
            verdict.value,
        )
        return VerdictProjected(
            kind=AuditEventKind.VERDICT,
            event_ref=event_ref,
            run_key=verdict.run_key,
            producer=self._producer,
            source_revision=verdict.revision,
            source_receipt=receipt,
            verdict=verdict,
        )


def _log_failure(stage: str, verdict_ref: Ref, reason: ReasonCode) -> None:
    _LOGGER.error("judge verdict %s: verdict=%s reason=%s", stage, verdict_ref, reason)


@dataclass(frozen=True, slots=True)
class JudgeDependencies:
    """app이 주입하는 판정 협력자. 감사 원본은 생산자별로 묶는다."""

    authorizer: JudgeReadAuthorizer
    policy_reader: JudgePolicyReader
    evidence: EvidencePort
    evidence_audit: AuditSource
    gateway_audit: AuditSource
    webdiag_verifier: AuditVerifier
    journal: VerdictJournal
    clock: Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class JudgeSettings:
    """판정 설정. producer ref는 여기서만 받고 호출자 값으로 대신하지 않는다."""

    producer: Ref
    webdiag_producer: Ref
    oracle_version: SourceVersion
    comparison_rules: ComparisonRules
    audit_page_limit: int = DEFAULT_AUDIT_PAGE_LIMIT
    audit_max_pages: int = DEFAULT_AUDIT_MAX_PAGES


class JudgeService:
    """`JudgePort` 제공자. 검증된 근거로만 판정하고 COMPLETE/FAILED를 엄격히 가른다."""

    def __init__(
        self,
        dependencies: JudgeDependencies,
        settings: JudgeSettings,
        *,
        submissions: InMemorySubmissionStore | None = None,
        event_ref_factory: Callable[[Ref, RunKey], Ref] = new_event_ref,
    ) -> None:
        self._deps = dependencies
        self._settings = settings
        self._submissions = submissions if submissions is not None else InMemorySubmissionStore()
        self._publisher = VerdictPublisher(
            dependencies.journal, settings.producer, event_ref_factory=event_ref_factory
        )

    async def judge(self, request: JudgeRequest) -> JudgeResult:
        """요청 case를 판정한다. 인가는 캐시된 결과를 돌려줄 때도 매 호출 확인한다."""
        run_key = request.run_key
        # 신뢰 시계는 호출당 한 번만 읽는다. Judge 감사 occurred_at이며, 비교 없는 판정의
        # 기준 시각이기도 하다.
        judged_at = self._deps.clock()
        if not await self._deps.authorizer.authorize(run_key, request.context, request.case_ref):
            return _failed(run_key, (ReasonCode.ACCESS_DENIED,), "read authorization denied")
        semantic = SemanticInput.of(request)
        async with self._submissions.lock_for(run_key, request.submission_ref):
            stored = self._submissions.get(run_key, request.submission_ref)
            if stored is not None:
                if stored.semantic == semantic:
                    return stored.result
                return _failed(
                    run_key, (ReasonCode.IDEMPOTENCY_CONFLICT,), "submission reused with new input"
                )
            try:
                result = await self._judge_once(request, judged_at)
            except CallFailure as failure:
                return _failed(run_key, failure.reason_codes, failure.detail)
            self._submissions.put(
                run_key, request.submission_ref, StoredSubmission(semantic=semantic, result=result)
            )
            return result

    async def _judge_once(self, request: JudgeRequest, judged_at: datetime) -> JudgeResult:
        scope = ScanScope(
            run_key=request.run_key,
            context=request.context,
            page_limit=self._settings.audit_page_limit,
            max_pages=self._settings.audit_max_pages,
        )
        canonical, hint_matches = await self._read_policy(request)
        comparison = await self._verified_comparison(request, scope)
        for identity in (request.owner_identity, request.evaluated_identity):
            if identity is not None:
                await verify_identity(
                    self._settings.webdiag_producer,
                    self._deps.webdiag_verifier,
                    request.run_key,
                    identity,
                )
        check_correspondence(
            CaseRecords(
                case_ref=request.case_ref,
                policy=canonical,
                owner_identity=request.owner_identity,
                evaluated_identity=request.evaluated_identity,
                comparison=comparison,
                expected_rules=self._settings.comparison_rules,
            )
        )
        case, basis = distill_case(
            JudgmentInputs(
                policy=canonical,
                hint_matches_canonical=hint_matches,
                owner_identity=request.owner_identity,
                evaluated_identity=request.evaluated_identity,
                comparison=comparison,
                judged_at=judged_at,
            )
        )
        oracle = evaluate_case(case, basis)
        context = await self._verdict_context(request, canonical, hint_matches, comparison)
        _require_publishable(oracle.value, context)
        projected = await self._publish(oracle, context, judged_at)
        return JudgeResult(
            run_key=request.run_key,
            status=ResultStatus.COMPLETE,
            verdict=projected.verdict,
            projection_event=projected,
            reason_codes=(),
        )

    async def _read_policy(
        self, request: JudgeRequest
    ) -> tuple[ExpectedAccessPolicySnapshot | None, bool]:
        # 정책은 reader의 정본만 쓴다. JudgeRequest.expected_policy는 reader에 넘기는 힌트일 뿐이다.
        result = await self._deps.policy_reader.read_case_policy(
            JudgePolicyReadRequest(
                run_key=request.run_key,
                context=request.context,
                case_ref=request.case_ref,
                expected_policy=request.expected_policy,
            )
        )
        if result.run_key != request.run_key or result.case_ref != request.case_ref:
            raise source_mismatch("policy read run/case mismatch")
        if result.status is not ResultStatus.COMPLETE:
            # 읽기 실패·위조는 정책 부재가 아니라 호출 실패다.
            raise CallFailure(
                "policy read failed",
                keep_failure_reasons(result.reason_codes, ReasonCode.SOURCE_UNVERIFIED),
            )
        canonical = result.expected_policy
        hint = request.expected_policy
        return canonical, hint is None or hint == canonical

    async def _verified_comparison(
        self, request: JudgeRequest, scope: ScanScope
    ) -> LoadedComparison | None:
        if request.comparison_ref is None:
            return None
        loaded = await load_comparison(self._deps.evidence, scope, request.comparison_ref)
        await attest_comparison(scope, self._deps.evidence_audit, self._deps.gateway_audit, loaded)
        return loaded

    async def _verdict_context(
        self,
        request: JudgeRequest,
        canonical: ExpectedAccessPolicySnapshot | None,
        hint_matches: bool,
        comparison: LoadedComparison | None,
    ) -> VerdictContext:
        run_key = request.run_key
        verdict_ref = f"{self._settings.producer}:verdict:{run_key.run_ref}:{request.case_ref}"
        revision = await self._deps.journal.latest_revision(run_key, verdict_ref) + 1
        policy_source = canonical.source if canonical is not None and hint_matches else None
        comparison_ref: Ref | None = None
        evidence_refs: tuple[Ref, ...] = ()
        if comparison is not None:
            comparison_ref = comparison.payload.comparison_ref
            evidence_refs = (comparison.owner.evidence_ref, comparison.cross.evidence_ref)
        return VerdictContext(
            run_key=run_key,
            verdict_ref=verdict_ref,
            revision=revision,
            case_ref=request.case_ref,
            oracle_version=self._settings.oracle_version,
            expected_policy_source=policy_source,
            comparison_ref=comparison_ref,
            evidence_refs=evidence_refs,
        )

    async def _publish(
        self, oracle: OracleVerdict, context: VerdictContext, judged_at: datetime
    ) -> VerdictProjected:
        try:
            return await self._publisher.publish(oracle, context, occurred_at=judged_at)
        except JournalCommitError as error:
            reason = (
                ReasonCode.REVISION_CONFLICT
                if error.reason_code is ReasonCode.IDEMPOTENCY_CONFLICT
                else error.reason_code
            )
            raise CallFailure("verdict commit failed", (reason,)) from error


def _require_publishable(value: VerdictValue, context: VerdictContext) -> None:
    # 검증된 값이 없으면 그 Verdict를 만들지 않는다(생성자 거부에 기대지 않는다). 도달하면 불변식
    # 위반이므로 내부 오류로 실패시킨다.
    has_comparison = context.comparison_ref is not None and bool(context.evidence_refs)
    has_policy = context.expected_policy_source is not None
    missing = (
        (value is VerdictValue.SUSPECTED and not has_comparison)
        or (value is VerdictValue.ALLOWED and not has_policy)
        or (value is VerdictValue.CONFIRMED and not (has_comparison and has_policy))
    )
    if missing:
        raise CallFailure("verdict preconditions not verified", (ReasonCode.INTERNAL_ERROR,))


def _failed(run_key: RunKey, reasons: tuple[ReasonCode, ...], detail: str) -> JudgeResult:
    _LOGGER.info("judge call failed: run=%s reasons=%s detail=%s", run_key.run_ref, reasons, detail)
    return JudgeResult(
        run_key=run_key,
        status=ResultStatus.FAILED,
        verdict=None,
        projection_event=None,
        reason_codes=reasons,
    )
