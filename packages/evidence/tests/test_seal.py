"""seal/compare_and_seal의 봉인·저장·감사·신호 조립을 네트워크·DB 없이 검증한다.

주입 fake(규칙 엔진·MAC·감사 저널·캡처 접근)와 실제 인메모리 저장소를 쓴다. 적용 사례:
S1-06(의존/감사 미완료 → 완료 비교 미발행), S1-09(HMAC 일치만으로 nontrivial=YES 금지),
S1-13(결과·receipt에 원문 없음), 캡처 소멸·감사 실패의 partial/failed 보존.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from abc2lab_contracts.audit import AuditEventKind, AuditReceipt, AuditRecordBinding
from abc2lab_contracts.capture import (
    CaptureRequest,
    ExecutedRequestView,
    RawHeader,
    RawResponse,
    ReleaseCapturesRequest,
)
from abc2lab_contracts.evidence import (
    CompareRequest,
    EvidenceSubmissionKind,
    RecoverSubmissionRequest,
    SealRequest,
)
from abc2lab_contracts.primitives import (
    CheckState,
    CloseResult,
    ParameterLocation,
    Purpose,
    ReasonCode,
    Ref,
    RequestParameter,
    ResponseClass,
    ResultStatus,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.registration import ComparisonRules
from abc2lab_contracts.session import IdentityResult, IdentityStatus
from abc2lab_evidence.adapters.memory_store import InMemoryEvidenceStore
from abc2lab_evidence.core.seal import LocalSealer, SealerConfig
from abc2lab_evidence.ports import DataSignals

_RUN = RunKey("org-1", "target-1", "env-1", "run-1")
_SOURCE = SourceVersion("issuer-1", "redaction-1", 1)
_RULES = ComparisonRules(_SOURCE, "normalizer-1", "oracle-1", "canary-1")
_NOW = datetime(2026, 10, 22, tzinfo=UTC)
_LATER = _NOW + timedelta(hours=1)
_FP = "0" * 64


def _now() -> datetime:
    return _NOW


def _refs() -> Callable[[], Ref]:
    count = 0

    def _next() -> Ref:
        nonlocal count
        count += 1
        return f"art-{count}"

    return _next


def _capture(ref_tag: str, *, status: int = 200, body: bytes = b"owner-order-42") -> CaptureRequest:
    view = ExecutedRequestView(
        run_key=_RUN,
        request_ref=f"request-{ref_tag}",
        attempt_ref=f"attempt-{ref_tag}",
        operation_ref="operation-1",
        operation_revision=1,
        resource_ref="resource-1",
        resource_binding_ref="binding-1",
        resource_binding_revision=1,
        account_ref=f"account-{ref_tag}",
        session_generation=1,
        purpose=Purpose.OBSERVE,
        method="GET",
        actual_origin="https://app.example",
        actual_path="/orders/42",
        actual_parameters=(RequestParameter("id", ParameterLocation.PATH, "42"),),
    )
    return CaptureRequest(
        run_key=_RUN,
        attempt_ref=view.attempt_ref,
        request_ref=view.request_ref,
        operation_ref=view.operation_ref,
        resource_ref=view.resource_ref,
        account_ref=view.account_ref,
        session_generation=view.session_generation,
        identity_ref=f"identity-{ref_tag}",
        observed_at=_NOW,
        executed_request=view,
        raw_response=RawResponse(status, (RawHeader("content-type", "application/json"),), body),
    )


def _identity(subject: str) -> IdentityResult:
    binding = AuditRecordBinding(
        AuditEventKind.IDENTITY, f"identity-record-{subject}", 1, _FP, None, None, None
    )
    receipt = AuditReceipt(_RUN, "webdiag", f"identity-event-{subject}", 1, binding, _NOW)
    return IdentityResult(
        run_key=_RUN,
        identity_ref=f"identity-{subject}",
        status=IdentityStatus.VERIFIED,
        session_ref=f"session-{subject}",
        account_ref=f"account-{subject}",
        generation=1,
        subject_ref=f"subject-{subject}",
        evidence_ref=f"identity-evidence-{subject}",
        verified_at=_NOW,
        valid_until=_LATER,
        audit_receipt=receipt,
        attempt_summaries=(),
        reason_codes=(),
    )


class _FakeCaptures:
    def __init__(self) -> None:
        self._items: dict[str, CaptureRequest] = {}
        self.released: list[tuple[Ref, ...]] = []

    def add(self, capture_ref: str, request: CaptureRequest) -> None:
        self._items[capture_ref] = request

    def acquire(self, run_key: RunKey, capture_ref: Ref) -> CaptureRequest | None:
        request = self._items.get(capture_ref)
        return request if request is not None and request.run_key == run_key else None

    def release_captures(self, request: ReleaseCapturesRequest) -> CloseResult:
        self.released.append(request.capture_refs)
        for ref in request.capture_refs:
            self._items.pop(ref, None)
        return CloseResult(request.run_key, ResultStatus.COMPLETE, ())


class _FakeEngine:
    def __init__(self, *, data: DataSignals, response_class: ResponseClass = ResponseClass.NORMAL):
        self._data = data
        self._class = response_class

    def classify(self, raw: RawResponse) -> ResponseClass:
        return self._class

    def normalize(self, raw: RawResponse) -> bytes:
        return raw.body

    def assess_data(
        self, owner: RawResponse, cross: RawResponse, *, hmac_match: bool
    ) -> DataSignals:
        return self._data


class _FakeMac:
    def compute(self, run_key: RunKey, data: bytes) -> bytes:
        return data


class _FakeJournal:
    def __init__(self, *, ok: bool = True) -> None:
        self._ok = ok
        self._sequence = 0

    async def commit(
        self, run_key: RunKey, producer: Ref, event_ref: Ref, binding: AuditRecordBinding
    ) -> AuditReceipt | None:
        if not self._ok:
            return None
        self._sequence += 1
        return AuditReceipt(run_key, producer, event_ref, self._sequence, binding, _NOW)


_ALL_YES = DataSignals(CheckState.YES, CheckState.YES, CheckState.YES)


def _sealer(
    captures: _FakeCaptures,
    *,
    engine: _FakeEngine | None = None,
    journal_ok: bool = True,
) -> LocalSealer:
    config = SealerConfig("evidence", _SOURCE, _refs(), _now)
    return LocalSealer(
        captures,
        InMemoryEvidenceStore(_now),
        engine or _FakeEngine(data=_ALL_YES),
        _FakeMac(),
        _FakeJournal(ok=journal_ok),
        config=config,
    )


@pytest.mark.asyncio
async def test_seal_complete_publishes_evidence_with_matching_receipt() -> None:
    captures = _FakeCaptures()
    captures.add("cap-1", _capture("owner"))
    result = await _sealer(captures).seal(SealRequest(_RUN, "submission-1", "cap-1", _RULES))
    assert result.status is ResultStatus.COMPLETE
    assert result.evidence is not None
    assert len(result.receipts) == 1
    assert "cap-1" in captures.released[0]


@pytest.mark.asyncio
async def test_seal_missing_capture_fails() -> None:
    result = await _sealer(_FakeCaptures()).seal(SealRequest(_RUN, "submission-1", "cap-x", _RULES))
    assert result.status is ResultStatus.FAILED
    assert result.evidence is None
    assert result.reason_codes == (ReasonCode.CAPTURE_EXPIRED,)


@pytest.mark.asyncio
async def test_seal_audit_failure_keeps_receipt_without_publishing_evidence() -> None:
    captures = _FakeCaptures()
    captures.add("cap-1", _capture("owner"))
    result = await _sealer(captures, journal_ok=False).seal(
        SealRequest(_RUN, "submission-1", "cap-1", _RULES)
    )
    assert result.status is ResultStatus.PARTIAL
    assert result.evidence is None
    assert len(result.receipts) == 1
    assert result.reason_codes == (ReasonCode.AUDIT_COMMIT_FAILED,)


def _compare_request() -> CompareRequest:
    return CompareRequest(
        run_key=_RUN,
        case_ref="case-1",
        submission_ref="submission-c1",
        resource_ref="resource-1",
        operation_ref="operation-1",
        owner_capture_ref="cap-owner",
        cross_capture_ref="cap-cross",
        owner_identity=_identity("a"),
        evaluated_identity=_identity("b"),
        rules=_RULES,
    )


def _compare_captures() -> _FakeCaptures:
    captures = _FakeCaptures()
    captures.add("cap-owner", _capture("owner"))
    captures.add("cap-cross", _capture("cross"))
    return captures


@pytest.mark.asyncio
async def test_compare_complete_emits_stored_comparison_and_projection() -> None:
    captures = _compare_captures()
    outcome = await _sealer(captures).compare_and_seal(_compare_request())
    assert outcome.status is ResultStatus.COMPLETE
    assert outcome.stored_comparison is not None
    assert outcome.projection_event is not None
    assert len(outcome.receipts) == 3
    signals = outcome.stored_comparison.payload.signals
    assert signals.distinct_verified_subjects is CheckState.YES
    assert signals.nontrivial_data_match is CheckState.YES
    assert set(captures.released[0]) == {"cap-owner", "cap-cross"}


@pytest.mark.asyncio
async def test_compare_hmac_match_alone_does_not_claim_nontrivial() -> None:
    # 엔진이 반사/동적으로 판정하면 HMAC가 같아도 nontrivial=NO를 유지한다(S1-09).
    reflection = DataSignals(CheckState.NO, CheckState.NO, CheckState.YES)
    engine = _FakeEngine(data=reflection)
    outcome = await _sealer(_compare_captures(), engine=engine).compare_and_seal(_compare_request())
    assert outcome.status is ResultStatus.COMPLETE
    assert outcome.stored_comparison is not None
    assert outcome.stored_comparison.payload.signals.nontrivial_data_match is CheckState.NO


@pytest.mark.asyncio
async def test_compare_audit_failure_is_partial_without_completed_artifacts() -> None:
    outcome = await _sealer(_compare_captures(), journal_ok=False).compare_and_seal(
        _compare_request()
    )
    assert outcome.status is ResultStatus.PARTIAL
    assert outcome.stored_comparison is None
    assert outcome.projection_event is None
    assert len(outcome.receipts) == 3
    assert outcome.reason_codes == (ReasonCode.AUDIT_COMMIT_FAILED,)


@pytest.mark.asyncio
async def test_compare_missing_capture_fails() -> None:
    captures = _FakeCaptures()
    captures.add("cap-owner", _capture("owner"))
    outcome = await _sealer(captures).compare_and_seal(_compare_request())
    assert outcome.status is ResultStatus.FAILED
    assert outcome.stored_comparison is None
    assert outcome.reason_codes == (ReasonCode.CAPTURE_EXPIRED,)


@pytest.mark.asyncio
async def test_seal_is_idempotent_without_recapture() -> None:
    captures = _FakeCaptures()
    captures.add("cap-1", _capture("owner"))
    sealer = _sealer(captures)
    first = await sealer.seal(SealRequest(_RUN, "submission-1", "cap-1", _RULES))
    second = await sealer.seal(SealRequest(_RUN, "submission-1", "cap-1", _RULES))
    assert first.status is ResultStatus.COMPLETE
    assert second == first
    # 재캡처 없이 기존 결과를 반환하므로 해제는 최초 1회뿐이다.
    assert len(captures.released) == 1


@pytest.mark.asyncio
async def test_seal_same_submission_different_capture_conflicts() -> None:
    captures = _FakeCaptures()
    captures.add("cap-1", _capture("owner"))
    captures.add("cap-2", _capture("owner"))
    sealer = _sealer(captures)
    await sealer.seal(SealRequest(_RUN, "submission-1", "cap-1", _RULES))
    conflict = await sealer.seal(SealRequest(_RUN, "submission-1", "cap-2", _RULES))
    assert conflict.status is ResultStatus.FAILED
    assert conflict.reason_codes == (ReasonCode.IDEMPOTENCY_CONFLICT,)


@pytest.mark.asyncio
async def test_recover_returns_committed_seal() -> None:
    captures = _FakeCaptures()
    captures.add("cap-1", _capture("owner"))
    sealer = _sealer(captures)
    committed = await sealer.seal(SealRequest(_RUN, "submission-1", "cap-1", _RULES))
    recovered = await sealer.recover_submission(
        RecoverSubmissionRequest(_RUN, "submission-1", EvidenceSubmissionKind.SEAL)
    )
    assert recovered == committed


@pytest.mark.asyncio
async def test_recover_returns_committed_compare() -> None:
    sealer = _sealer(_compare_captures())
    committed = await sealer.compare_and_seal(_compare_request())
    recovered = await sealer.recover_submission(
        RecoverSubmissionRequest(_RUN, "submission-c1", EvidenceSubmissionKind.COMPARE)
    )
    assert recovered == committed


@pytest.mark.asyncio
async def test_recover_unknown_submission_fails() -> None:
    recovered = await _sealer(_FakeCaptures()).recover_submission(
        RecoverSubmissionRequest(_RUN, "nope", EvidenceSubmissionKind.SEAL)
    )
    assert recovered.status is ResultStatus.FAILED
    assert recovered.reason_codes == (ReasonCode.NOT_FOUND,)


@pytest.mark.asyncio
async def test_recover_wrong_kind_conflicts() -> None:
    captures = _FakeCaptures()
    captures.add("cap-1", _capture("owner"))
    sealer = _sealer(captures)
    await sealer.seal(SealRequest(_RUN, "submission-1", "cap-1", _RULES))
    recovered = await sealer.recover_submission(
        RecoverSubmissionRequest(_RUN, "submission-1", EvidenceSubmissionKind.COMPARE)
    )
    assert recovered.status is ResultStatus.FAILED
    assert recovered.reason_codes == (ReasonCode.IDEMPOTENCY_CONFLICT,)
