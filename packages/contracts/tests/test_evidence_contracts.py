"""C3 frozen Evidence contract shapes, structural receipts and private port split."""

from collections.abc import Callable
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
    CompareRequest,
    ComparisonPayload,
    ComparisonProjected,
    ComparisonSignals,
    EvidenceReadRequest,
    EvidenceReadResult,
    EvidenceSubmissionKind,
    EvidenceSummary,
    RecoverSubmissionRequest,
    RedactedBundle,
    SealResult,
    StoredComparison,
    StoreOutcome,
    StoreReceipt,
)
from abc2lab_contracts.fingerprint import (
    comparison_fingerprint,
    evidence_fingerprint,
    identity_content_fingerprint,
)
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
from abc2lab_contracts.session import IdentityContent, IdentityResult

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


def test_same_identity_ref_cannot_claim_distinct_verified_subjects() -> None:
    payload = _comparison()
    with pytest.raises(ValueError, match="same identity ref"):
        replace(payload, evaluated_identity_ref=payload.owner_identity_ref)


@pytest.mark.parametrize("state", [CheckState.NO, CheckState.UNKNOWN])
def test_same_identity_comparison_preserves_negative_or_unknown_signal(state: CheckState) -> None:
    payload = _comparison()
    same_identity = replace(
        payload,
        evaluated_identity_ref=payload.owner_identity_ref,
        signals=replace(payload.signals, distinct_verified_subjects=state),
    )
    assert same_identity.signals.distinct_verified_subjects is state
    assert comparison_fingerprint(same_identity) != comparison_fingerprint(payload)


@pytest.mark.parametrize("distinct_refs", [False, True])
def test_same_subject_compare_request_is_preserved_for_signal_evaluation(
    identity: IdentityResult, identity_content: IdentityContent, distinct_refs: bool
) -> None:
    evaluated = identity
    if distinct_refs:
        content = replace(
            identity_content, identity_ref="identity-b", session_ref="session-b", account_ref="b"
        )
        receipt = identity.audit_receipt
        assert receipt is not None and content.identity_ref is not None
        evaluated = IdentityResult.from_content(
            content,
            replace(
                receipt,
                event_ref="event-identity-b",
                binding=replace(
                    receipt.binding,
                    record_ref=content.identity_ref,
                    record_fingerprint=identity_content_fingerprint(content),
                ),
            ),
        )
    request = CompareRequest(
        identity.run_key,
        "case",
        "submission",
        "resource",
        "operation",
        "capture-owner",
        "capture-cross",
        identity,
        evaluated,
        ComparisonRules(_source(), "normalizer", "oracle", "canary"),
    )
    assert request.owner_identity.subject_ref == request.evaluated_identity.subject_ref
    assert (identity.identity_ref != evaluated.identity_ref) is distinct_refs


@pytest.mark.parametrize("status", tuple(ResultStatus))
def test_store_outcome_rejects_receipt_from_another_run(status: ResultStatus) -> None:
    foreign = replace(_run(), run_ref="other-run")
    receipt = replace(_receipts(_comparison())[0], run_key=foreign)
    with pytest.raises(ValueError, match="run mismatch"):
        StoreOutcome(_run(), status, (receipt,), (ReasonCode.EVIDENCE_STORE_FAILED,))


def test_failed_read_never_publishes_artifacts() -> None:
    stored = StoredComparison(_comparison(), _receipts(_comparison()))
    with pytest.raises(ValueError, match="failed read"):
        EvidenceReadResult(
            _run(), ResultStatus.FAILED, (_evidence("owner"),), (), (ReasonCode.ACCESS_DENIED,)
        )
    with pytest.raises(ValueError, match="failed read"):
        EvidenceReadResult(_run(), ResultStatus.FAILED, (), (stored,), (ReasonCode.ACCESS_DENIED,))


def test_failed_read_is_distinct_from_successful_empty_lookup() -> None:
    failed = EvidenceReadResult(_run(), ResultStatus.FAILED, (), (), (ReasonCode.ACCESS_DENIED,))
    complete = EvidenceReadResult(_run(), ResultStatus.COMPLETE, (), (), ())
    assert failed.status is not complete.status
    partial = EvidenceReadResult(
        _run(), ResultStatus.PARTIAL, (_evidence("owner"),), (), (ReasonCode.NOT_FOUND,)
    )
    assert partial.evidence


def test_complete_seal_rejects_receipt_for_different_content() -> None:
    receipt = replace(_receipts(_comparison())[0], content_fingerprint="a" * 64)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        SealResult(_run(), ResultStatus.COMPLETE, _evidence("owner"), (receipt,), ())


def test_stored_comparison_rejects_mismatched_comparison_store_digest() -> None:
    payload = _comparison()
    receipts = _receipts(payload)
    mismatched = receipts[:2] + (replace(receipts[2], content_fingerprint="a" * 64),)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        StoredComparison(payload, mismatched)


def test_recipe_must_describe_the_same_evidence_operation_and_resource() -> None:
    evidence = _evidence("owner")
    recipe = _recipe()
    with pytest.raises(ValueError, match="recipe.*binding"):
        replace(evidence, request_recipe=replace(recipe, operation_ref="other-operation"))
    with pytest.raises(ValueError, match="recipe.*binding"):
        replace(evidence, request_recipe=replace(recipe, resource_ref="other-resource"))
    with pytest.raises(ValueError, match="recipe.*binding"):
        replace(evidence, resource_ref=None)


@pytest.mark.parametrize("path", ["//other.invalid/objects/1", "/\\other.invalid/objects/1"])
def test_recipe_rejects_authority_like_paths(path: str) -> None:
    with pytest.raises(ValueError, match="path"):
        replace(_recipe(), path_template=path)


def test_complete_store_requires_a_committed_receipt() -> None:
    with pytest.raises(ValueError, match="complete store.*receipt"):
        StoreOutcome(_run(), ResultStatus.COMPLETE, (), ())


@pytest.mark.parametrize("status", [ResultStatus.PARTIAL, ResultStatus.FAILED])
def test_incomplete_outputs_require_a_reason(status: ResultStatus) -> None:
    with pytest.raises(ValueError, match="reason"):
        StoreOutcome(_run(), status, (), ())
    with pytest.raises(ValueError, match="reason"):
        EvidenceReadResult(_run(), status, (), (), ())
    with pytest.raises(ValueError, match="reason"):
        SealResult(_run(), status, None, (), ())
    with pytest.raises(ValueError, match="reason"):
        CompareOutcome(_run(), status, None, None, (), ())


def test_successful_receipts_are_preserved_as_partial_even_after_terminal_failure() -> None:
    receipts = _receipts(_comparison())[:1]
    reasons = (ReasonCode.CAPTURE_EXPIRED,)
    assert StoreOutcome(_run(), ResultStatus.PARTIAL, receipts, reasons).receipts == receipts
    assert SealResult(_run(), ResultStatus.PARTIAL, None, receipts, reasons).receipts == receipts
    assert (
        CompareOutcome(_run(), ResultStatus.PARTIAL, None, None, receipts, reasons).receipts
        == receipts
    )
    with pytest.raises(ValueError, match="partial or complete"):
        StoreOutcome(_run(), ResultStatus.FAILED, receipts, reasons)
    with pytest.raises(ValueError, match="partial or complete"):
        SealResult(_run(), ResultStatus.FAILED, None, receipts, reasons)
    with pytest.raises(ValueError, match="partial or complete"):
        CompareOutcome(_run(), ResultStatus.FAILED, None, None, receipts, reasons)


class _RegisteredRecipeStore:
    """등록 recipe 한 건과의 대조를 재생하며 실제 저장·감사·인가를 구현하지 않는다."""

    def __init__(self, expected: RegisteredRequestRecipe) -> None:
        self.expected = expected
        self.saved: tuple[EvidenceSummary, ...] = ()

    async def store_evidence(self, request: RedactedBundle) -> StoreOutcome:
        if request.comparison is not None or len(request.evidence) != 1:
            raise AssertionError("this example only stores one Evidence artifact")
        evidence = request.evidence[0]
        # Equality checks every field, including path, slots, source and revisions.
        # Actual trusted registration/provenance validation belongs to Evidence.
        if evidence.request_recipe != self.expected:
            return StoreOutcome(
                request.run_key, ResultStatus.FAILED, (), (ReasonCode.RECIPE_BINDING_MISMATCH,)
            )
        self.saved = request.evidence
        receipt = StoreReceipt(
            request.run_key,
            request.submission_ref,
            evidence.evidence_ref,
            ArtifactKind.EVIDENCE,
            request.source,
            STAMP,
            evidence_fingerprint(evidence),
        )
        return StoreOutcome(request.run_key, ResultStatus.COMPLETE, (receipt,), ())

    async def evidence_read_summary(self, request: EvidenceReadRequest) -> EvidenceReadResult:
        return EvidenceReadResult(
            request.run_key, ResultStatus.FAILED, (), (), (ReasonCode.ACCESS_DENIED,)
        )


_RECIPE_CHANGES: tuple[Callable[[RegisteredRequestRecipe], RegisteredRequestRecipe], ...] = (
    lambda recipe: replace(recipe, operation_ref="unregistered-operation"),
    lambda recipe: replace(recipe, operation_revision=2),
    lambda recipe: replace(recipe, resource_ref="unregistered-resource"),
    lambda recipe: replace(recipe, resource_binding_ref="unregistered-binding"),
    lambda recipe: replace(recipe, resource_binding_revision=2),
    lambda recipe: replace(recipe, path_template="/objects/unregistered-value"),
    lambda recipe: replace(
        recipe,
        parameters=(RecipeParameter("object_id", ParameterLocation.PATH, "${UNKNOWN_SLOT}"),),
    ),
    lambda recipe: replace(recipe, source=_source(2)),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", _RECIPE_CHANGES)
async def test_recipe_consumer_rejects_shape_valid_unregistered_recipes_before_storage(
    change: Callable[[RegisteredRequestRecipe], RegisteredRequestRecipe],
) -> None:
    changed = change(_recipe())
    evidence = replace(
        _evidence("owner"),
        request_recipe=changed,
        operation_ref=changed.operation_ref,
        resource_ref=changed.resource_ref,
    )
    example = _RegisteredRecipeStore(_recipe())
    port: EvidencePort = example
    result = await port.store_evidence(RedactedBundle(_run(), "sub", (evidence,), None, _source()))
    assert result.status is ResultStatus.FAILED
    assert result.reason_codes == (ReasonCode.RECIPE_BINDING_MISMATCH,)
    assert not result.receipts
    assert not example.saved


@pytest.mark.asyncio
async def test_recipe_consumer_accepts_registered_recipe_without_target_io() -> None:
    evidence = _evidence("owner")
    example = _RegisteredRecipeStore(_recipe())
    port: EvidencePort = example
    result = await port.store_evidence(RedactedBundle(_run(), "sub", (evidence,), None, _source()))
    assert result.status is ResultStatus.COMPLETE
    assert result.receipts[0].content_fingerprint == evidence_fingerprint(evidence)
    assert example.saved == (evidence,)
