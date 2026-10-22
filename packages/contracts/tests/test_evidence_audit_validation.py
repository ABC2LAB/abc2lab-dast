"""Regression coverage for the PR27 Evidence and audit validation helpers."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from abc2lab_contracts.audit import (
    AuditEvent,
    AuditEventKind,
    AuditReceipt,
    AuditRecordBinding,
    PolicyOutcome,
)
from abc2lab_contracts.evidence import (
    ArtifactKind,
    CompareOutcome,
    ComparisonPayload,
    ComparisonProjected,
    ComparisonSignals,
    EvidenceSubmissionKind,
    EvidenceSummary,
    RecoverSubmissionRequest,
    SealResult,
    StoredComparison,
    StoreReceipt,
    validate_comparison_audit,
    validate_evidence_audit,
    validate_recovery_result,
)
from abc2lab_contracts.fingerprint import comparison_fingerprint, evidence_fingerprint
from abc2lab_contracts.primitives import (
    AuditLink,
    CheckState,
    ParameterLocation,
    ReasonCode,
    ResponseClass,
    ResultStatus,
    RunKey,
    SendStatus,
    SourceVersion,
)
from abc2lab_contracts.recipe import RecipeParameter, RegisteredRequestRecipe
from abc2lab_contracts.registration import ComparisonRules

STAMP = datetime(2026, 10, 21, tzinfo=UTC)


def _run() -> RunKey:
    return RunKey("org", "target", "environment", "run")


def _source() -> SourceVersion:
    return SourceVersion("app", "source", 1)


def _recipe() -> RegisteredRequestRecipe:
    return RegisteredRequestRecipe(
        "poc.v0.1",
        "operation",
        1,
        "resource",
        "resource-binding",
        1,
        "GET",
        "${REGISTERED_ORIGIN}",
        "/objects/${RESOURCE_ID}",
        (RecipeParameter("object_id", ParameterLocation.PATH, "${RESOURCE_ID}"),),
        "fresh_registered_session",
        _source(),
    )


def _evidence(ref: str = "evidence") -> EvidenceSummary:
    return EvidenceSummary(
        _run(),
        ref,
        f"attempt-{ref}",
        "operation",
        "resource",
        "account",
        1,
        f"identity-{ref}",
        ResponseClass.NORMAL,
        200,
        STAMP,
        _source(),
        AuditLink("producer", f"event-{ref}"),
        _recipe(),
        (),
    )


def _audit_event(
    binding: AuditRecordBinding, *, send_status: SendStatus | None = None
) -> AuditEvent:
    receipt = AuditReceipt(_run(), "producer", "event-evidence", 1, binding, STAMP)
    return AuditEvent(
        receipt,
        (),
        None,
        None,
        "case",
        "account",
        1,
        (binding.record_ref,),
        (),
        STAMP,
        STAMP,
        "producer-instance",
        10,
        None,
        send_status,
        (),
    )


def _evidence_event(summary: EvidenceSummary | None = None) -> AuditEvent:
    summary = summary or _evidence()
    binding = AuditRecordBinding(
        AuditEventKind.EVIDENCE,
        summary.evidence_ref,
        1,
        evidence_fingerprint(summary),
        None,
        summary.attempt_ref,
        None,
    )
    return _audit_event(binding)


@pytest.mark.parametrize(
    ("record_ref", "attempt_ref", "request_ref", "valid"),
    [
        ("attempt", "attempt", "request", True),
        ("attempt", None, "request", False),
        ("attempt", "other", "request", False),
        ("attempt", "attempt", None, False),
    ],
)
def test_attempt_audit_binding_requires_its_attempt_and_request_refs(
    record_ref: str, attempt_ref: str | None, request_ref: str | None, valid: bool
) -> None:
    if valid:
        binding = AuditRecordBinding(
            AuditEventKind.ATTEMPT, record_ref, 1, "a" * 64, request_ref, attempt_ref, None
        )
        assert binding.attempt_ref == "attempt"
    else:
        with pytest.raises(ValueError, match="attempt audit binding"):
            AuditRecordBinding(
                AuditEventKind.ATTEMPT,
                record_ref,
                1,
                "a" * 64,
                request_ref,
                attempt_ref,
                None,
            )


def test_evidence_audit_binding_requires_attempt_ref() -> None:
    with pytest.raises(ValueError, match="Evidence audit binding"):
        AuditRecordBinding(AuditEventKind.EVIDENCE, "evidence", 1, "a" * 64, None, None, None)


@pytest.mark.parametrize(
    "alter_binding",
    [
        lambda binding: replace(binding, request_ref="foreign"),
        lambda binding: replace(binding, attempt_ref="foreign"),
        lambda binding: replace(binding, binding_id="foreign"),
    ],
    ids=["request_ref", "attempt_ref", "binding_id"],
)
def test_comparison_projection_cannot_carry_transport_binding_refs(
    alter_binding: Callable[[AuditRecordBinding], AuditRecordBinding],
) -> None:
    projection = _compare(ResultStatus.COMPLETE).projection_event
    assert projection is not None
    receipt = projection.source_receipt
    with pytest.raises(ValueError, match="comparison audit binding"):
        replace(
            projection,
            source_receipt=replace(receipt, binding=alter_binding(receipt.binding)),
        )


def test_validate_evidence_audit_accepts_c3_binding() -> None:
    summary = _evidence()
    validate_evidence_audit(summary, _evidence_event(summary))


@pytest.mark.parametrize(
    "alter",
    [
        lambda e: replace(e, receipt=replace(e.receipt, run_key=replace(_run(), run_ref="other"))),
        lambda e: replace(e, receipt=replace(e.receipt, producer="other")),
        lambda e: replace(e, receipt=replace(e.receipt, event_ref="other")),
        lambda e: replace(e, account_ref="other"),
        lambda e: replace(e, session_generation=2),
        lambda e: replace(e, evidence_refs=("other",)),
        lambda e: replace(e, evidence_refs=("evidence", "unrelated")),
        lambda e: replace(e, verdict_refs=("future-verdict",)),
        lambda e: replace(e, policy_outcome=PolicyOutcome.ALLOW),
        lambda e: replace(e, send_status=SendStatus.SENT),
        lambda e: replace(
            e,
            receipt=replace(
                e.receipt,
                binding=replace(e.receipt.binding, record_fingerprint="b" * 64),
            ),
        ),
        lambda e: replace(
            e,
            receipt=replace(
                e.receipt,
                binding=replace(e.receipt.binding, attempt_ref="other-attempt"),
            ),
        ),
    ],
)
def test_validate_evidence_audit_rejects_any_binding_drift(alter: object) -> None:
    with pytest.raises(ValueError, match="Evidence audit binding"):
        validate_evidence_audit(_evidence(), alter(_evidence_event()))  # type: ignore[operator]


def _comparison(signals: ComparisonSignals | None = None) -> ComparisonPayload:
    return ComparisonPayload(
        _run(),
        "comparison",
        "case",
        "resource",
        "operation",
        "owner-evidence",
        "cross-evidence",
        "owner-identity",
        "cross-identity",
        signals
        or ComparisonSignals(
            CheckState.YES,
            CheckState.YES,
            CheckState.YES,
            CheckState.YES,
            CheckState.UNKNOWN,
            CheckState.YES,
            CheckState.UNKNOWN,
        ),
        ComparisonRules(_source(), "normalizer", "oracle", "canary"),
    )


def _comparison_event(payload: ComparisonPayload | None = None) -> AuditEvent:
    payload = payload or _comparison()
    binding = AuditRecordBinding(
        AuditEventKind.COMPARISON,
        payload.comparison_ref,
        1,
        comparison_fingerprint(payload),
        None,
        None,
        None,
    )
    return replace(
        _audit_event(binding),
        account_ref=None,
        session_generation=None,
        evidence_refs=(payload.owner_evidence_ref, payload.cross_evidence_ref),
    )


def test_validate_comparison_audit_accepts_canonical_unknown_signals() -> None:
    payload = _comparison()
    event = replace(
        _comparison_event(payload),
        reason_codes=(
            ReasonCode.COMPARISON_CANARY_PASSED,
            ReasonCode.COMPARISON_DATA_MATCH_UNKNOWN,
            ReasonCode.COMPARISON_TEMPLATE_UNKNOWN,
        ),
    )
    validate_comparison_audit(payload, event)


@pytest.mark.parametrize(
    "alter",
    [
        lambda e: replace(e, receipt=replace(e.receipt, run_key=replace(_run(), run_ref="other"))),
        lambda e: replace(
            e,
            receipt=replace(
                e.receipt,
                binding=replace(e.receipt.binding, event_kind=AuditEventKind.REQUEST_INTENT),
            ),
        ),
        lambda e: replace(
            e,
            receipt=replace(e.receipt, binding=replace(e.receipt.binding, record_ref="other")),
        ),
        lambda e: replace(
            e,
            receipt=replace(e.receipt, binding=replace(e.receipt.binding, record_revision=2)),
        ),
        lambda e: replace(
            e,
            receipt=replace(
                e.receipt,
                binding=replace(e.receipt.binding, record_fingerprint="b" * 64),
            ),
        ),
        lambda e: replace(e, case_ref="other-case"),
        lambda e: replace(e, evidence_refs=("owner-evidence", "wrong")),
        lambda e: replace(e, account_ref="owner-account"),
        lambda e: replace(e, session_generation=1),
        lambda e: replace(e, policy_outcome=PolicyOutcome.ALLOW),
        lambda e: replace(e, verdict_refs=("future-verdict",)),
        lambda e: replace(e, send_status=SendStatus.SENT),
        lambda e: replace(
            e,
            receipt=replace(
                e.receipt,
                binding=replace(e.receipt.binding, request_ref="request"),
            ),
        ),
    ],
)
def test_validate_comparison_audit_rejects_reference_and_metadata_drift(alter: object) -> None:
    event = replace(
        _comparison_event(),
        reason_codes=(
            ReasonCode.COMPARISON_CANARY_PASSED,
            ReasonCode.COMPARISON_DATA_MATCH_UNKNOWN,
            ReasonCode.COMPARISON_TEMPLATE_UNKNOWN,
        ),
    )
    validate_comparison_audit(_comparison(), event)
    with pytest.raises(ValueError, match="comparison audit binding"):
        validate_comparison_audit(_comparison(), alter(event))  # type: ignore[operator]


@pytest.mark.parametrize(
    "reasons",
    [
        (),
        (ReasonCode.COMPARISON_CANARY_PASSED, ReasonCode.COMPARISON_CANARY_FAILED),
        (ReasonCode.COMPARISON_CANARY_FAILED,),
        (ReasonCode.COMPARISON_CANARY_UNKNOWN,),
        (ReasonCode.COMPARISON_CANARY_PASSED, ReasonCode.COMPARISON_SAME_RESOURCE_UNKNOWN),
    ],
)
def test_validate_comparison_audit_requires_canary_and_unknown_reason_consistency(
    reasons: tuple[ReasonCode, ...],
) -> None:
    event = replace(_comparison_event(), reason_codes=reasons)
    with pytest.raises(ValueError, match="comparison"):
        validate_comparison_audit(_comparison(), event)


@pytest.mark.parametrize(
    ("index", "reason"),
    list(
        enumerate(
            (
                ReasonCode.COMPARISON_SAME_RESOURCE_UNKNOWN,
                ReasonCode.COMPARISON_SUBJECTS_UNKNOWN,
                ReasonCode.COMPARISON_OWNER_DATA_UNKNOWN,
                ReasonCode.COMPARISON_CROSS_DATA_UNKNOWN,
                ReasonCode.COMPARISON_DATA_MATCH_UNKNOWN,
                ReasonCode.COMPARISON_REFLECTION_UNKNOWN,
                ReasonCode.COMPARISON_TEMPLATE_UNKNOWN,
            )
        )
    ),
)
def test_each_unknown_signal_requires_its_own_reason_marker(index: int, reason: ReasonCode) -> None:
    states = [CheckState.YES] * 7
    states[index] = CheckState.UNKNOWN
    signals = ComparisonSignals(*states)
    payload = _comparison(signals)
    event = replace(
        _comparison_event(payload),
        reason_codes=(ReasonCode.COMPARISON_CANARY_PASSED, reason),
    )
    validate_comparison_audit(payload, event)
    with pytest.raises(ValueError, match="comparison"):
        validate_comparison_audit(
            payload,
            replace(event, reason_codes=(ReasonCode.COMPARISON_CANARY_PASSED,)),
        )


@pytest.mark.parametrize(
    "canary", [ReasonCode.COMPARISON_CANARY_FAILED, ReasonCode.COMPARISON_CANARY_UNKNOWN]
)
def test_untrusted_canary_preserves_unknown_and_explanatory_reason(canary: ReasonCode) -> None:
    payload = _comparison()
    event = replace(
        _comparison_event(payload),
        reason_codes=(
            canary,
            ReasonCode.COMPARISON_DATA_MATCH_UNKNOWN,
            ReasonCode.COMPARISON_TEMPLATE_UNKNOWN,
            ReasonCode.SOURCE_UNVERIFIED,
        ),
    )
    validate_comparison_audit(payload, event)
    assert ReasonCode.SOURCE_UNVERIFIED in event.reason_codes
    # Recompute the digest as well: the rejection must be for canary semantics.
    for state in (CheckState.YES, CheckState.NO):
        changed = replace(payload, signals=replace(payload.signals, nontrivial_data_match=state))
        changed_event = replace(
            _comparison_event(changed),
            reason_codes=(canary, ReasonCode.COMPARISON_TEMPLATE_UNKNOWN),
        )
        with pytest.raises(ValueError, match="unverified canary"):
            validate_comparison_audit(changed, changed_event)


def _seal(status: ResultStatus) -> SealResult:
    if status is ResultStatus.COMPLETE:
        evidence = _evidence()
        receipt = StoreReceipt(
            _run(),
            "submission",
            evidence.evidence_ref,
            ArtifactKind.EVIDENCE,
            _source(),
            STAMP,
            evidence_fingerprint(evidence),
        )
        return SealResult(_run(), status, evidence, (receipt,), ())
    return SealResult(_run(), status, None, (), (ReasonCode.AUDIT_GAP,))


def _compare(status: ResultStatus) -> CompareOutcome:
    if status is ResultStatus.COMPLETE:
        payload = _comparison()
        evidence_receipts = tuple(
            StoreReceipt(
                _run(),
                f"submission-{ref}",
                f"{ref}-evidence",
                ArtifactKind.EVIDENCE,
                _source(),
                STAMP,
                evidence_fingerprint(_evidence(f"{ref}-evidence")),
            )
            for ref in ("owner", "cross")
        )
        comparison_receipt = StoreReceipt(
            _run(),
            "submission-comparison",
            payload.comparison_ref,
            ArtifactKind.COMPARISON,
            _source(),
            STAMP,
            comparison_fingerprint(payload),
        )
        stored = StoredComparison(payload, evidence_receipts + (comparison_receipt,))
        source_receipt = AuditReceipt(
            _run(),
            "producer",
            "comparison-event",
            1,
            AuditRecordBinding(
                AuditEventKind.COMPARISON,
                payload.comparison_ref,
                1,
                comparison_fingerprint(payload),
                None,
                None,
                None,
            ),
            STAMP,
        )
        projection = ComparisonProjected(
            AuditEventKind.COMPARISON,
            "comparison-event",
            _run(),
            "producer",
            1,
            source_receipt,
            stored,
        )
        return CompareOutcome(_run(), status, stored, projection, stored.receipts, ())
    return CompareOutcome(_run(), status, None, None, (), (ReasonCode.AUDIT_GAP,))


@pytest.mark.parametrize("status", tuple(ResultStatus))
def test_validate_recovery_result_accepts_each_seal_status(status: ResultStatus) -> None:
    validate_recovery_result(
        RecoverSubmissionRequest(_run(), "submission", EvidenceSubmissionKind.SEAL), _seal(status)
    )


@pytest.mark.parametrize("status", tuple(ResultStatus))
def test_validate_recovery_result_accepts_each_compare_status(status: ResultStatus) -> None:
    validate_recovery_result(
        RecoverSubmissionRequest(_run(), "submission", EvidenceSubmissionKind.COMPARE),
        _compare(status),
    )


@pytest.mark.parametrize(
    ("kind", "result"),
    [
        (EvidenceSubmissionKind.SEAL, _compare(ResultStatus.FAILED)),
        (EvidenceSubmissionKind.COMPARE, _seal(ResultStatus.FAILED)),
    ],
)
def test_validate_recovery_result_rejects_wrong_result_type_even_when_failed(
    kind: EvidenceSubmissionKind, result: object
) -> None:
    with pytest.raises(TypeError, match="kind/result type"):
        validate_recovery_result(RecoverSubmissionRequest(_run(), "submission", kind), result)  # type: ignore[arg-type]


def test_validate_recovery_result_rejects_foreign_run() -> None:
    result = _seal(ResultStatus.FAILED)
    foreign = replace(_run(), run_ref="other-run")
    with pytest.raises(ValueError, match="run mismatch"):
        validate_recovery_result(
            RecoverSubmissionRequest(foreign, "submission", EvidenceSubmissionKind.SEAL), result
        )
