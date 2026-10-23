"""저장된 비교·근거·신원·전송 감사를 독립 확인하는 어댑터.

두 종류의 확인을 구분한다(명세 §6.1·§10).
- 공개 레코드(EvidenceSummary·ComparisonPayload·IdentityResult)는 contracts codec으로 binding을 독립
  재계산하고, 생산자 `verify_committed`로 commit을 확인한다.
- Gateway ATTEMPT는 소비자가 전체 레코드를 받지 않으므로 신뢰된 reader가 준 binding으로 생산자에게
  commit 확인을 요청하는 attestation이다. 이를 독립 재계산이라 하지 않는다.

확인하지 못한 것은 근거 부족이 아니라 호출 실패(`CallFailure`)로 올린다. producer ref는 설정에서만
받고 호출자가 준 producer·receipt를 조회 원본으로 쓰지 않는다. 같은 `audit_verification_unknown`
이라도 감사 인프라 장애(WARNING)와 검증된 기록이 스스로 unknown인 사실(INFO)을 로그에서 구분한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from abc2lab_contracts.audit import (
    AuditEvent,
    AuditEventKind,
    AuditReadRequest,
    AuditRecordBinding,
    AuditVerifyRequest,
    AuditVerifyResult,
    VerificationState,
)
from abc2lab_contracts.evidence import (
    ComparisonPayload,
    EvidenceReadRequest,
    EvidenceReadResult,
    EvidenceSummary,
    StoredComparison,
    validate_comparison_audit,
    validate_evidence_audit,
)
from abc2lab_contracts.fingerprint import (
    comparison_fingerprint,
    evidence_fingerprint,
    identity_fingerprint,
)
from abc2lab_contracts.ports import AuditReader, AuditVerifier, EvidencePort
from abc2lab_contracts.primitives import (
    AuditLink,
    ReadContext,
    ReasonCode,
    Ref,
    ResultStatus,
    RunKey,
    SendStatus,
)
from abc2lab_contracts.reason_codes import CALL_AUDIT_FAILURE_REASON_CODES
from abc2lab_contracts.session import IdentityResult

_LOGGER = logging.getLogger(__name__)

DEFAULT_AUDIT_PAGE_LIMIT = 100
DEFAULT_AUDIT_MAX_PAGES = 20


class CallFailure(Exception):
    """판정 호출을 끝낼 수 없는 실패. `reason_codes`는 호출·감사 실패 사유다."""

    def __init__(self, detail: str, reason_codes: tuple[ReasonCode, ...]) -> None:
        super().__init__(detail)
        self.detail = detail
        self.reason_codes = reason_codes


@dataclass(frozen=True, slots=True)
class AuditSource:
    """한 생산자의 신뢰된 감사 reader·verifier와 설정에서 받은 producer ref."""

    producer: Ref
    reader: AuditReader
    verifier: AuditVerifier


@dataclass(frozen=True, slots=True)
class ScanScope:
    """한 판정 호출의 감사 조회 범위와 페이지 상한."""

    run_key: RunKey
    context: ReadContext
    page_limit: int
    max_pages: int


@dataclass(frozen=True, slots=True)
class LoadedComparison:
    """EvidencePort에서 읽은 비교 payload와 owner/cross 근거 요약."""

    payload: ComparisonPayload
    owner: EvidenceSummary
    cross: EvidenceSummary


def keep_failure_reasons(
    reasons: tuple[ReasonCode, ...], default: ReasonCode
) -> tuple[ReasonCode, ...]:
    """외부 결과 사유 중 호출·감사 실패 사유만 남긴다. 하나도 없으면 `default`."""
    kept = tuple(reason for reason in reasons if reason in CALL_AUDIT_FAILURE_REASON_CODES)
    return kept or (default,)


def infra_unknown(detail: str, *extra: ReasonCode) -> CallFailure:
    """감사 조회·검증 인프라가 답하지 못한 실패."""
    _LOGGER.warning("judge audit verification unavailable: %s", detail)
    return CallFailure(detail, (ReasonCode.AUDIT_VERIFICATION_UNKNOWN, *extra))


def recorded_unknown(detail: str) -> CallFailure:
    """검증된 기록이 스스로 unknown 상태인 사실. 인프라 장애가 아니다."""
    _LOGGER.info("judge source record is genuinely unknown: %s", detail)
    return CallFailure(detail, (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,))


def source_mismatch(detail: str, reason: ReasonCode = ReasonCode.SOURCE_UNVERIFIED) -> CallFailure:
    """출처·연결·주체가 서로 맞지 않는 실패(변조·바인딩 불일치)."""
    _LOGGER.warning("judge source mismatch: %s", detail)
    return CallFailure(detail, (reason,))


def require_verified(result: AuditVerifyResult, run_key: RunKey, stage: str) -> None:
    """생산자 검증이 같은 run에서 VERIFIED일 때만 통과시킨다."""
    if result.run_key != run_key:
        raise source_mismatch(f"{stage} verification run mismatch")
    if result.state is VerificationState.VERIFIED:
        return
    if result.state is VerificationState.INVALID:
        raise source_mismatch(f"{stage} commit invalid")
    raise infra_unknown(f"{stage} commit verification unknown")


async def read_snapshot(
    reader: AuditReader, scope: ScanScope, producer: Ref
) -> tuple[AuditEvent, ...]:
    """한 생산자 journal의 같은 snapshot을 끝까지 읽는다. 상한 안에 못 끝내면 실패다."""
    events: list[AuditEvent] = []
    cursor: Ref | None = None
    snapshot: Ref | None = None
    for _ in range(scope.max_pages):
        page = await reader.read_audit(
            AuditReadRequest(
                scope.run_key, scope.context, producer, cursor, snapshot, scope.page_limit
            )
        )
        if page.run_key != scope.run_key or page.producer != producer:
            raise source_mismatch("audit page run/producer mismatch")
        if page.status is ResultStatus.FAILED:
            # 조회 실패는 검증 불가로 남기고, 페이지가 밝힌 실패 사유(snapshot_expired 등)도
            # 함께 보존한다.
            kept = keep_failure_reasons(page.reason_codes, ReasonCode.AUDIT_VERIFICATION_UNKNOWN)
            reasons = tuple(dict.fromkeys((ReasonCode.AUDIT_VERIFICATION_UNKNOWN, *kept)))
            _LOGGER.warning("judge audit page failed: producer=%s reasons=%s", producer, reasons)
            raise CallFailure("audit page read failed", reasons)
        if snapshot is not None and page.snapshot != snapshot:
            raise infra_unknown("audit snapshot changed between pages")
        snapshot = page.snapshot
        events.extend(page.events)
        if page.next_cursor is None:
            _require_contiguous(events)
            return tuple(events)
        cursor = page.next_cursor
    raise infra_unknown("audit snapshot exceeded page limit", ReasonCode.RESULT_LIMIT_EXCEEDED)


def _require_contiguous(events: list[AuditEvent]) -> None:
    sequences = [event.receipt.sequence for event in events]
    if any(after != before + 1 for before, after in zip(sequences, sequences[1:], strict=False)):
        raise infra_unknown("audit sequence gap or reorder")


async def load_comparison(
    evidence: EvidencePort, scope: ScanScope, comparison_ref: Ref
) -> LoadedComparison:
    """비교와 owner/cross 근거를 EvidencePort에서만 읽는다(호출자 구성 값을 믿지 않는다)."""
    stored = _single_comparison(
        await evidence.evidence_read_summary(
            EvidenceReadRequest(scope.run_key, scope.context, (), (comparison_ref,))
        ),
        scope.run_key,
        comparison_ref,
    )
    payload = stored.payload
    refs = (payload.owner_evidence_ref, payload.cross_evidence_ref)
    read = await evidence.evidence_read_summary(
        EvidenceReadRequest(scope.run_key, scope.context, refs, ())
    )
    _require_complete_read(read, scope.run_key)
    by_ref = {summary.evidence_ref: summary for summary in read.evidence}
    if any(ref not in by_ref for ref in refs):
        raise CallFailure("comparison evidence not returned", (ReasonCode.NOT_FOUND,))
    owner, cross = by_ref[refs[0]], by_ref[refs[1]]
    _require_receipt_fingerprints(stored, owner, cross)
    return LoadedComparison(payload=payload, owner=owner, cross=cross)


def _single_comparison(
    read: EvidenceReadResult, run_key: RunKey, comparison_ref: Ref
) -> StoredComparison:
    _require_complete_read(read, run_key)
    matches = [item for item in read.comparisons if item.payload.comparison_ref == comparison_ref]
    if not matches:
        raise CallFailure("comparison not returned", (ReasonCode.NOT_FOUND,))
    if len(matches) > 1:
        raise source_mismatch("duplicate comparisons returned")
    return matches[0]


def _require_complete_read(read: EvidenceReadResult, run_key: RunKey) -> None:
    if read.run_key != run_key:
        raise source_mismatch("evidence read run mismatch")
    if read.status is not ResultStatus.COMPLETE:
        reasons = keep_failure_reasons(read.reason_codes, ReasonCode.NOT_FOUND)
        _LOGGER.warning("judge evidence read incomplete: reasons=%s", reasons)
        raise CallFailure("evidence read incomplete", reasons)


def _require_receipt_fingerprints(
    stored: StoredComparison, owner: EvidenceSummary, cross: EvidenceSummary
) -> None:
    owner_receipt, cross_receipt, _ = stored.receipts
    if owner_receipt.content_fingerprint != evidence_fingerprint(
        owner
    ) or cross_receipt.content_fingerprint != evidence_fingerprint(cross):
        raise source_mismatch("evidence store receipt fingerprint mismatch")


async def attest_comparison(
    scope: ScanScope, evidence: AuditSource, gateway: AuditSource, loaded: LoadedComparison
) -> None:
    """비교·근거의 Evidence 감사와 각 근거의 Gateway 전송 감사를 확인한다."""
    evidence_events = await read_snapshot(evidence.reader, scope, evidence.producer)
    await _attest_comparison_record(scope, evidence, loaded, evidence_events)
    gateway_events = await read_snapshot(gateway.reader, scope, gateway.producer)
    for summary in (loaded.owner, loaded.cross):
        event = await _attest_evidence_record(scope, evidence, summary, evidence_events)
        await _attest_attempt(scope, gateway, summary, event, gateway_events)


async def _attest_comparison_record(
    scope: ScanScope,
    evidence: AuditSource,
    loaded: LoadedComparison,
    events: tuple[AuditEvent, ...],
) -> None:
    payload = loaded.payload
    matches = [
        event
        for event in events
        if event.receipt.binding.event_kind is AuditEventKind.COMPARISON
        and event.receipt.binding.record_ref == payload.comparison_ref
    ]
    event = _exactly_one(matches, "comparison audit event")
    try:
        validate_comparison_audit(payload, event)
    except ValueError as error:
        raise source_mismatch("comparison audit content mismatch") from error
    if not {loaded.owner.source_event, loaded.cross.source_event} <= set(event.causal_links):
        raise source_mismatch("comparison not causally linked to its evidence")
    expected = AuditRecordBinding(
        AuditEventKind.COMPARISON,
        payload.comparison_ref,
        1,
        comparison_fingerprint(payload),
        None,
        None,
        None,
    )
    result = await evidence.verifier.verify_committed(
        AuditVerifyRequest(scope.run_key, event.receipt, expected)
    )
    require_verified(result, scope.run_key, "comparison")


async def _attest_evidence_record(
    scope: ScanScope,
    evidence: AuditSource,
    summary: EvidenceSummary,
    events: tuple[AuditEvent, ...],
) -> AuditEvent:
    if summary.source_event.producer != evidence.producer:
        raise source_mismatch("evidence source producer is not the configured Evidence producer")
    matches = [
        event
        for event in events
        if event.receipt.producer == summary.source_event.producer
        and event.receipt.event_ref == summary.source_event.event_ref
    ]
    event = _exactly_one(matches, "evidence audit event")
    try:
        validate_evidence_audit(summary, event)
    except ValueError as error:
        raise source_mismatch("evidence audit content mismatch") from error
    expected = AuditRecordBinding(
        AuditEventKind.EVIDENCE,
        summary.evidence_ref,
        1,
        evidence_fingerprint(summary),
        None,
        summary.attempt_ref,
        None,
    )
    result = await evidence.verifier.verify_committed(
        AuditVerifyRequest(scope.run_key, event.receipt, expected)
    )
    require_verified(result, scope.run_key, "evidence")
    return event


async def _attest_attempt(
    scope: ScanScope,
    gateway: AuditSource,
    summary: EvidenceSummary,
    evidence_event: AuditEvent,
    events: tuple[AuditEvent, ...],
) -> None:
    attempts = [
        event
        for event in events
        if event.receipt.binding.event_kind is AuditEventKind.ATTEMPT
        and event.receipt.binding.record_ref == summary.attempt_ref
    ]
    adopted = _adopt_latest_revision(attempts)
    if adopted.receipt.producer != gateway.producer:
        raise source_mismatch("attempt producer is not the configured Gateway producer")
    # attestation: reader가 준 binding으로 Gateway에 commit 확인을 요청한다(독립 재계산 아님).
    result = await gateway.verifier.verify_committed(
        AuditVerifyRequest(scope.run_key, adopted.receipt, adopted.receipt.binding)
    )
    require_verified(result, scope.run_key, "attempt")
    if (
        adopted.account_ref != summary.account_ref
        or adopted.session_generation != summary.session_generation
    ):
        raise source_mismatch("attempt account/generation differs from evidence")
    _require_sent(adopted)
    link = AuditLink(adopted.receipt.producer, adopted.receipt.event_ref)
    if link not in evidence_event.causal_links:
        raise source_mismatch("evidence not causally linked to its attempt")


def _adopt_latest_revision(attempts: list[AuditEvent]) -> AuditEvent:
    if not attempts:
        raise infra_unknown("attempt audit event not found")
    fingerprints_by_revision: dict[int, set[str]] = {}
    for event in attempts:
        binding = event.receipt.binding
        fingerprints_by_revision.setdefault(binding.record_revision, set()).add(
            binding.record_fingerprint
        )
    if any(len(fingerprints) > 1 for fingerprints in fingerprints_by_revision.values()):
        raise infra_unknown("conflicting attempt records for one revision")
    latest = max(fingerprints_by_revision)
    if set(fingerprints_by_revision) != set(range(1, latest + 1)):
        raise infra_unknown("attempt revision history has gaps")
    return next(event for event in attempts if event.receipt.binding.record_revision == latest)


def _require_sent(event: AuditEvent) -> None:
    # SENT만 전송 연결 근거다. 확정 NOT_SENT에 응답 근거가 붙었으면 바인딩 불일치이고, UNKNOWN은
    # 변조가 아니라 보존해야 할 사실이다(§6.1-6). 둘은 같은 실패로 뭉치지 않는다.
    if event.send_status is SendStatus.SENT:
        return
    if event.send_status is SendStatus.NOT_SENT:
        raise source_mismatch("confirmed not_sent attempt carries response evidence")
    raise recorded_unknown("verified attempt send status is unknown")


def _exactly_one(events: list[AuditEvent], what: str) -> AuditEvent:
    if not events:
        raise infra_unknown(f"{what} not found")
    if len(events) > 1:
        raise infra_unknown(f"conflicting {what}s")
    return events[0]


async def verify_identity(
    webdiag_producer: Ref, verifier: AuditVerifier, run_key: RunKey, identity: IdentityResult
) -> None:
    """공급된 신원의 감사 receipt를 독립 binding으로 WebDiag에 확인한다.

    receipt가 없는 신원(미검증 상태)은 확인할 commit이 없으므로 그대로 둔다 — 판정에서 검증된
    주체로 쓰이지 않는다.
    """
    receipt = identity.audit_receipt
    if receipt is None:
        return
    if identity.identity_ref is None or receipt.producer != webdiag_producer:
        raise source_mismatch("identity receipt producer/ref mismatch")
    expected = AuditRecordBinding(
        AuditEventKind.IDENTITY,
        identity.identity_ref,
        1,
        identity_fingerprint(identity),
        None,
        None,
        None,
    )
    if receipt.binding != expected:
        raise source_mismatch("identity receipt binding differs from its content")
    result = await verifier.verify_committed(AuditVerifyRequest(run_key, receipt, expected))
    require_verified(result, run_key, "identity")
