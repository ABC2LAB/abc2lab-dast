"""C3 frozen Evidence contract shapes, structural receipts and private port split."""

from dataclasses import replace
from datetime import UTC, datetime
from inspect import iscoroutinefunction
from typing import cast

import pytest
from abc2lab_contracts.audit import (
    AuditEventKind,
    AuditReceipt,
    AuditRecordBinding,
)
from abc2lab_contracts.evidence import (
    ArtifactKind,
    CompareOutcome,
    ComparisonPayload,
    ComparisonProjected,
    ComparisonSignals,
    EvidenceReadResult,
    EvidenceSubmissionKind,
    EvidenceSummary,
    RecoverSubmissionRequest,
    RedactedBundle,
    SealResult,
    StoredComparison,
    StoreReceipt,
)
from abc2lab_contracts.fingerprint import comparison_fingerprint, evidence_fingerprint
from abc2lab_contracts.ports import EvidencePort, ExecutionEvidencePort, LocalCapturePort
from abc2lab_contracts.primitives import (
    AuditLink,
    CheckState,
    ParameterLocation,
    ReasonCode,
    ResponseClass,
    ResultStatus,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.recipe import RecipeParameter, RegisteredRequestRecipe
from abc2lab_contracts.registration import ComparisonRules

STAMP = datetime(2026, 10, 21, tzinfo=UTC)


def _run() -> RunKey:
    return RunKey("org", "target", "environment", "run")


def _source(revision: int = 1) -> SourceVersion:
    return SourceVersion("app", "registered-evidence", revision)


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


def _evidence(ref: str) -> EvidenceSummary:
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
        AuditLink("evidence-producer", f"event-{ref}"),
        _recipe(),
        (),
    )


def _comparison() -> ComparisonPayload:
    return ComparisonPayload(
        _run(),
        "comparison",
        "case",
        "resource",
        "operation",
        "owner",
        "cross",
        "identity-owner",
        "identity-cross",
        ComparisonSignals(
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


def _receipts(payload: ComparisonPayload) -> tuple[StoreReceipt, ...]:
    # Prior submissions and source revisions are intentionally different.
    return (
        StoreReceipt(
            _run(),
            "sub-owner",
            "owner",
            ArtifactKind.EVIDENCE,
            _source(),
            STAMP,
            evidence_fingerprint(_evidence("owner")),
        ),
        StoreReceipt(
            _run(),
            "sub-cross",
            "cross",
            ArtifactKind.EVIDENCE,
            _source(),
            STAMP,
            evidence_fingerprint(_evidence("cross")),
        ),
        StoreReceipt(
            _run(),
            "sub-compare",
            "comparison",
            ArtifactKind.COMPARISON,
            _source(2),
            STAMP,
            comparison_fingerprint(payload),
        ),
    )


def _projection(stored: StoredComparison) -> ComparisonProjected:
    payload = stored.payload
    audit = AuditReceipt(
        _run(),
        "evidence-producer",
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
    return ComparisonProjected(
        AuditEventKind.COMPARISON,
        "comparison-event",
        _run(),
        "evidence-producer",
        1,
        audit,
        stored,
    )


def test_port_split_and_async_boundaries() -> None:
    assert not iscoroutinefunction(LocalCapturePort.capture)
    assert not iscoroutinefunction(LocalCapturePort.release_captures)
    assert iscoroutinefunction(ExecutionEvidencePort.seal)
    assert iscoroutinefunction(ExecutionEvidencePort.compare_and_seal)
    assert iscoroutinefunction(ExecutionEvidencePort.recover_submission)
    assert iscoroutinefunction(EvidencePort.store_evidence)
    assert iscoroutinefunction(EvidencePort.evidence_read_summary)
    assert not hasattr(EvidencePort, "capture")
    assert not hasattr(EvidencePort, "recover_submission")


def test_recovery_request_never_contains_capture_or_raw_data() -> None:
    request = RecoverSubmissionRequest(_run(), "submission", EvidenceSubmissionKind.COMPARE)
    assert request.kind is EvidenceSubmissionKind.COMPARE
    assert not hasattr(request, "capture_ref")
    with pytest.raises(TypeError):
        RecoverSubmissionRequest(_run(), "submission", cast(EvidenceSubmissionKind, "compare"))
    with pytest.raises(ValueError):
        RecoverSubmissionRequest(_run(), "", EvidenceSubmissionKind.SEAL)


def test_stored_comparison_accepts_original_receipts_and_fixed_order() -> None:
    payload = _comparison()
    receipts = _receipts(payload)
    stored = StoredComparison(payload, receipts)
    assert stored.receipts[0].submission_ref == "sub-owner"
    assert stored.receipts[1].submission_ref == "sub-cross"
    assert stored.receipts[2].submission_ref == "sub-compare"
    assert stored.receipts[2].source.revision == 2
    assert _projection(stored).comparison == stored


@pytest.mark.parametrize(
    "alter",
    [
        lambda r: r[:2],
        lambda r: (r[1], r[0], r[2]),
        lambda r: (r[0], r[0], r[2]),
        lambda r: (
            replace(r[0], run_key=RunKey("other", "target", "environment", "run")),
            r[1],
            r[2],
        ),
        lambda r: (replace(r[0], artifact_kind=ArtifactKind.COMPARISON), r[1], r[2]),
        lambda r: (r[0], r[1], replace(r[2], artifact_ref="other")),
    ],
)
def test_stored_comparison_rejects_bad_receipts(alter: object) -> None:
    payload = _comparison()
    with pytest.raises(ValueError):
        StoredComparison(payload, alter(_receipts(payload)))  # type: ignore[operator]


def test_projection_binds_original_journal_receipt_not_store_receipt() -> None:
    payload = _comparison()
    original = _projection(StoredComparison(payload, _receipts(payload)))
    assert original.source_revision == 1
    with pytest.raises(ValueError, match="binding mismatch"):
        replace(original, event_ref="forged-event")
    with pytest.raises(ValueError, match="kind must be comparison"):
        replace(original, kind=AuditEventKind.EVIDENCE)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        replace(
            original,
            source_receipt=replace(
                original.source_receipt,
                binding=replace(
                    original.source_receipt.binding,
                    record_fingerprint="a" * 64,
                ),
            ),
        )


def test_completed_result_requires_comparison_and_projection() -> None:
    payload = _comparison()
    stored = StoredComparison(payload, _receipts(payload))
    projected = _projection(stored)
    complete = CompareOutcome(_run(), ResultStatus.COMPLETE, stored, projected, stored.receipts, ())
    assert complete.status is ResultStatus.COMPLETE
    with pytest.raises(ValueError, match="requires"):
        replace(complete, projection_event=None)
    with pytest.raises(ValueError, match="incomplete"):
        replace(complete, status=ResultStatus.PARTIAL)
    partial = CompareOutcome(
        _run(),
        ResultStatus.PARTIAL,
        None,
        None,
        stored.receipts[:1],
        (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,),
    )
    assert len(partial.receipts) == 1


def test_seal_preserves_receipts_without_publishing_incomplete_evidence() -> None:
    evidence = _evidence("owner")
    receipt = _receipts(_comparison())[0]
    assert SealResult(_run(), ResultStatus.COMPLETE, evidence, (receipt,), ()).evidence == evidence
    partial = SealResult(
        _run(), ResultStatus.PARTIAL, None, (receipt,), (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,)
    )
    assert partial.receipts == (receipt,)
    with pytest.raises(ValueError, match="incomplete"):
        replace(partial, evidence=evidence)


def test_bundle_allows_existing_evidence_dependencies_and_enforces_run() -> None:
    # Existing same-run Evidence can be referenced without resubmitting it.
    assert RedactedBundle(_run(), "compare-sub", (), _comparison(), _source(2)).comparison
    with pytest.raises(ValueError, match="empty"):
        RedactedBundle(_run(), "sub", (), None, _source())
    with pytest.raises(ValueError, match="duplicate"):
        RedactedBundle(_run(), "sub", (_evidence("owner"), _evidence("owner")), None, _source())
    assert EvidenceReadResult(_run(), ResultStatus.COMPLETE, (_evidence("owner"),), (), ()).evidence


def test_recipe_rejects_raw_and_unsupported_values() -> None:
    recipe = _recipe()
    with pytest.raises(ValueError, match="GET"):
        replace(recipe, method="POST")
    with pytest.raises(ValueError, match="origin"):
        replace(recipe, origin_placeholder="https://target.invalid")
    with pytest.raises(ValueError, match="session"):
        replace(recipe, authentication="old_cookie")
    with pytest.raises(ValueError, match="path"):
        replace(recipe, path_template="https://target.invalid/objects/1")
    with pytest.raises(ValueError, match="placeholder"):
        RecipeParameter("object_id", ParameterLocation.PATH, "real-123")
    with pytest.raises(ValueError, match="path/query"):
        RecipeParameter("password", ParameterLocation.FORM, "${RESOURCE_ID}")
    with pytest.raises(ValueError, match="version"):
        replace(recipe, schema_version="poc.v0.2")


def test_evidence_recipe_none_has_nonsecret_reason() -> None:
    evidence = _evidence("owner")
    with pytest.raises(ValueError, match="reason"):
        replace(evidence, request_recipe=None)
    without_recipe = replace(
        evidence, request_recipe=None, recipe_reason_codes=(ReasonCode.RECIPE_UNSUPPORTED,)
    )
    assert without_recipe.request_recipe is None
    assert evidence_fingerprint(without_recipe) != evidence_fingerprint(evidence)
