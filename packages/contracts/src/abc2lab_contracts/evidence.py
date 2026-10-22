"""C3 public Evidence artifacts and private execution-only request contracts.

These immutable values enforce shapes and local structural invariants. Real
storage, source provenance, journal commits, authorization, redaction, capture
ownership, submission leases and fencing are owned by the Evidence service.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from abc2lab_contracts._validation import (
    ContractRecord,
    require_fingerprint,
    require_positive,
    validate_record,
)
from abc2lab_contracts.audit import AuditEvent, AuditEventKind, AuditReceipt, AuditRecordBinding
from abc2lab_contracts.primitives import (
    AuditLink,
    CheckState,
    ReadContext,
    ReasonCode,
    Ref,
    ResponseClass,
    ResultStatus,
    Revision,
    RunKey,
    SourceVersion,
    UtcTime,
)
from abc2lab_contracts.recipe import RegisteredRequestRecipe
from abc2lab_contracts.registration import ComparisonRules
from abc2lab_contracts.session import IdentityResult


class ArtifactKind(StrEnum):
    """Artifact kinds accepted by the redacted Evidence store."""

    EVIDENCE = "evidence"
    COMPARISON = "comparison"


class EvidenceSubmissionKind(StrEnum):
    """Kind of an already registered private Evidence submission."""

    SEAL = "seal"
    COMPARE = "compare"


@dataclass(frozen=True, slots=True)
class EvidenceSummary(ContractRecord):
    """Redacted immutable evidence, linked to its OWN producer audit event."""

    run_key: RunKey
    evidence_ref: Ref
    attempt_ref: Ref
    operation_ref: Ref
    resource_ref: Ref | None
    account_ref: Ref | None
    session_generation: int | None
    identity_ref: Ref | None
    response_class: ResponseClass
    http_status: int
    observed_at: UtcTime
    redaction_version: SourceVersion
    source_event: AuditLink
    request_recipe: RegisteredRequestRecipe | None
    recipe_reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.session_generation is not None:
            require_positive("session_generation", self.session_generation)
        if not 100 <= self.http_status <= 599:
            raise ValueError("evidence HTTP status must be between 100 and 599")
        if self.request_recipe is None and not self.recipe_reason_codes:
            raise ValueError("missing recipe must retain a reason")
        if self.request_recipe is not None and (
            self.request_recipe.operation_ref != self.operation_ref
            or self.request_recipe.resource_ref != self.resource_ref
        ):
            raise ValueError("evidence recipe operation/resource binding mismatch")


@dataclass(frozen=True, slots=True)
class ComparisonSignals(ContractRecord):
    """Separate verified signals from unknown access and data observations."""

    same_resource: CheckState
    distinct_verified_subjects: CheckState
    owner_normal_data: CheckState
    cross_normal_data: CheckState
    nontrivial_data_match: CheckState
    reflection_excluded: CheckState
    template_excluded: CheckState


@dataclass(frozen=True, slots=True)
class ComparisonPayload(ContractRecord):
    """Receipt-free immutable comparison payload used for comparison.v1."""

    run_key: RunKey
    comparison_ref: Ref
    case_ref: Ref
    resource_ref: Ref
    operation_ref: Ref
    owner_evidence_ref: Ref
    cross_evidence_ref: Ref
    owner_identity_ref: Ref
    evaluated_identity_ref: Ref
    signals: ComparisonSignals
    rules: ComparisonRules

    def _validate_invariants(self) -> None:
        if self.owner_evidence_ref == self.cross_evidence_ref:
            raise ValueError("owner/cross must reference different evidence artifacts")


@dataclass(frozen=True, slots=True)
class StoreReceipt(ContractRecord):
    """Immutable artifact receipt; original submission/source MUST be preserved."""

    run_key: RunKey
    submission_ref: Ref
    artifact_ref: Ref
    artifact_kind: ArtifactKind
    source: SourceVersion
    committed_at: UtcTime
    content_fingerprint: str

    def _validate_invariants(self) -> None:
        require_fingerprint(self.content_fingerprint)


@dataclass(frozen=True, slots=True)
class StoredComparison(ContractRecord):
    """Structurally complete receipt tuple; service still verifies each commit."""

    payload: ComparisonPayload
    receipts: tuple[StoreReceipt, ...]

    def _validate_invariants(self) -> None:
        if len(self.receipts) != 3:
            raise ValueError("stored comparison requires exactly three receipts")
        owner, cross, comparison = self.receipts
        matches = (
            (owner, ArtifactKind.EVIDENCE, self.payload.owner_evidence_ref),
            (cross, ArtifactKind.EVIDENCE, self.payload.cross_evidence_ref),
            (comparison, ArtifactKind.COMPARISON, self.payload.comparison_ref),
        )
        for receipt, expected_kind, expected_ref in matches:
            if receipt.run_key != self.payload.run_key:
                raise ValueError("comparison and receipt run mismatch")
            if receipt.artifact_kind is not expected_kind or receipt.artifact_ref != expected_ref:
                raise ValueError("comparison receipt kind/ref or order mismatch")
        # Original submission_ref and source may legitimately differ across receipts.
        if len({(r.artifact_kind, r.artifact_ref) for r in self.receipts}) != 3:
            raise ValueError("duplicate comparison receipts")
        from abc2lab_contracts.fingerprint import comparison_fingerprint

        if comparison.content_fingerprint != comparison_fingerprint(self.payload):
            raise ValueError("comparison store receipt content fingerprint mismatch")


@dataclass(frozen=True, slots=True)
class RedactedBundle(ContractRecord):
    """Only a redacted, typed set of Evidence artifacts can reach the store."""

    run_key: RunKey
    submission_ref: Ref
    evidence: tuple[EvidenceSummary, ...]
    comparison: ComparisonPayload | None
    source: SourceVersion

    def _validate_invariants(self) -> None:
        if not self.evidence and self.comparison is None:
            raise ValueError("cannot store an empty Evidence bundle")
        if any(item.run_key != self.run_key for item in self.evidence):
            raise ValueError("bundle Evidence run mismatch")
        if len({item.evidence_ref for item in self.evidence}) != len(self.evidence):
            raise ValueError("duplicate Evidence artifact")
        if self.comparison is not None and self.comparison.run_key != self.run_key:
            raise ValueError("bundle comparison run mismatch")
        # Comparison dependencies may be from this bundle OR prior same-run storage.
        # The Evidence service must read/verify every referenced dependency.


@dataclass(frozen=True, slots=True)
class StoreOutcome(ContractRecord):
    """Preserve every successfully committed receipt, even for partial writes."""

    run_key: RunKey
    status: ResultStatus
    receipts: tuple[StoreReceipt, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if any(receipt.run_key != self.run_key for receipt in self.receipts):
            raise ValueError("store receipt run mismatch")
        if self.status is ResultStatus.COMPLETE and not self.receipts:
            raise ValueError("complete store requires at least one receipt")
        if self.status is ResultStatus.FAILED and self.receipts:
            raise ValueError("stored receipts require a partial or complete store result")
        if self.status is not ResultStatus.COMPLETE and not self.reason_codes:
            raise ValueError("incomplete store requires a reason")


@dataclass(frozen=True, slots=True)
class EvidenceReadRequest(ContractRecord):
    """Read only authorized redacted evidence by explicit run-bound refs."""

    run_key: RunKey
    context: ReadContext
    evidence_refs: tuple[Ref, ...]
    comparison_refs: tuple[Ref, ...]


@dataclass(frozen=True, slots=True)
class EvidenceReadResult(ContractRecord):
    """Return committed public records; absence never authorizes disclosure."""

    run_key: RunKey
    status: ResultStatus
    evidence: tuple[EvidenceSummary, ...]
    comparisons: tuple[StoredComparison, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is not ResultStatus.COMPLETE and not self.reason_codes:
            raise ValueError("incomplete Evidence read requires a reason")
        if self.status is ResultStatus.FAILED and (self.evidence or self.comparisons):
            raise ValueError("failed read cannot publish artifacts")
        if any(item.run_key != self.run_key for item in self.evidence):
            raise ValueError("Evidence read run mismatch")
        if any(item.payload.run_key != self.run_key for item in self.comparisons):
            raise ValueError("comparison read run mismatch")


@dataclass(frozen=True, slots=True, repr=False)
class SealRequest(ContractRecord):
    """Private one-shot seal input: capture_ref is NEVER publicly serialized."""

    run_key: RunKey
    submission_ref: Ref
    capture_ref: Ref
    rules: ComparisonRules


@dataclass(frozen=True, slots=True)
class SealResult(ContractRecord):
    """Complete only after Evidence store and producer audit are verified."""

    run_key: RunKey
    status: ResultStatus
    evidence: EvidenceSummary | None
    receipts: tuple[StoreReceipt, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is not ResultStatus.COMPLETE and not self.reason_codes:
            raise ValueError("incomplete seal requires a reason")
        if any(item.run_key != self.run_key for item in self.receipts):
            raise ValueError("seal receipt run mismatch")
        if self.status is ResultStatus.FAILED and self.receipts:
            raise ValueError("stored receipts require a partial or complete seal result")
        if self.status is ResultStatus.COMPLETE:
            if self.evidence is None or self.evidence.run_key != self.run_key:
                raise ValueError("complete seal requires matching Evidence")
            if len(self.receipts) != 1:
                raise ValueError("complete seal requires one Evidence receipt")
            receipt = self.receipts[0]
            if (
                receipt.artifact_kind is not ArtifactKind.EVIDENCE
                or receipt.artifact_ref != self.evidence.evidence_ref
            ):
                raise ValueError("complete seal receipt must match Evidence")
            from abc2lab_contracts.fingerprint import evidence_fingerprint

            if receipt.content_fingerprint != evidence_fingerprint(self.evidence):
                raise ValueError("seal receipt content fingerprint mismatch")
        elif self.evidence is not None:
            raise ValueError("incomplete seal cannot publish Evidence")


@dataclass(frozen=True, slots=True, repr=False)
class CompareRequest(ContractRecord):
    """Private A/B capture handles and already-verified identity snapshots."""

    run_key: RunKey
    case_ref: Ref
    submission_ref: Ref
    resource_ref: Ref
    operation_ref: Ref
    owner_capture_ref: Ref
    cross_capture_ref: Ref
    owner_identity: IdentityResult
    evaluated_identity: IdentityResult
    rules: ComparisonRules

    def _validate_invariants(self) -> None:
        if self.owner_capture_ref == self.cross_capture_ref:
            raise ValueError("comparison requires two distinct capture handles")
        if (
            self.owner_identity.run_key != self.run_key
            or self.evaluated_identity.run_key != self.run_key
        ):
            raise ValueError("comparison identity run mismatch")
        # Valid/expired subject and source proof are independently checked by Evidence.


@dataclass(frozen=True, slots=True)
class ComparisonProjected(ContractRecord):
    """Producer-owned projection bound to an actual COMPARISON journal receipt."""

    kind: AuditEventKind
    event_ref: Ref
    run_key: RunKey
    producer: Ref
    source_revision: Revision
    source_receipt: AuditReceipt
    comparison: StoredComparison

    def _validate_invariants(self) -> None:
        if self.kind is not AuditEventKind.COMPARISON:
            raise ValueError("projection kind must be comparison")
        receipt = self.source_receipt
        if (
            self.source_revision != 1
            or self.run_key != self.comparison.payload.run_key
            or receipt.run_key != self.run_key
            or receipt.event_ref != self.event_ref
            or receipt.producer != self.producer
            or receipt.binding.event_kind is not AuditEventKind.COMPARISON
            or receipt.binding.record_ref != self.comparison.payload.comparison_ref
            or receipt.binding.record_revision != self.source_revision
        ):
            raise ValueError("comparison projection audit binding mismatch")
        from abc2lab_contracts.fingerprint import comparison_fingerprint

        if receipt.binding.record_fingerprint != comparison_fingerprint(self.comparison.payload):
            raise ValueError("comparison projection content fingerprint mismatch")


@dataclass(frozen=True, slots=True)
class CompareOutcome(ContractRecord):
    """No complete StoredComparison or projection before ALL verified commits."""

    run_key: RunKey
    status: ResultStatus
    stored_comparison: StoredComparison | None
    projection_event: ComparisonProjected | None
    receipts: tuple[StoreReceipt, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is not ResultStatus.COMPLETE and not self.reason_codes:
            raise ValueError("incomplete compare requires a reason")
        if any(item.run_key != self.run_key for item in self.receipts):
            raise ValueError("compare receipt run mismatch")
        if self.status is ResultStatus.FAILED and self.receipts:
            raise ValueError("stored receipts require a partial or complete compare result")
        if self.status is ResultStatus.COMPLETE:
            if self.stored_comparison is None or self.projection_event is None:
                raise ValueError("complete compare requires stored comparison and projection")
            if self.stored_comparison.payload.run_key != self.run_key:
                raise ValueError("complete comparison run mismatch")
            if (
                self.projection_event.comparison != self.stored_comparison
                or self.receipts != self.stored_comparison.receipts
            ):
                raise ValueError("complete comparison receipts/projection mismatch")
        elif self.stored_comparison is not None or self.projection_event is not None:
            raise ValueError("incomplete compare cannot publish completed artifacts")


@dataclass(frozen=True, slots=True)
class RecoverSubmissionRequest(ContractRecord):
    """Private no-capture reconciliation of a previously committed submission."""

    run_key: RunKey
    submission_ref: Ref
    kind: EvidenceSubmissionKind


def validate_recovery_result(
    request: RecoverSubmissionRequest, result: SealResult | CompareOutcome
) -> None:
    """Reject a recovery kind/type or run mismatch without performing recovery I/O."""
    if type(request) is not RecoverSubmissionRequest:
        raise TypeError("expected exact RecoverSubmissionRequest")
    validate_record(request)
    expected_type = SealResult if request.kind is EvidenceSubmissionKind.SEAL else CompareOutcome
    if type(result) is not expected_type:
        raise TypeError("recovery kind/result type mismatch")
    validate_record(result)
    if result.run_key != request.run_key:
        raise ValueError("recovery result run mismatch")


def validate_evidence_audit(summary: EvidenceSummary, event: AuditEvent) -> None:
    """Check local Evidence/audit coherence; producer lookup still proves the commit."""
    if type(summary) is not EvidenceSummary or type(event) is not AuditEvent:
        raise TypeError("expected exact EvidenceSummary and AuditEvent")
    validate_record(summary)
    validate_record(event)
    from abc2lab_contracts.fingerprint import evidence_fingerprint

    expected = AuditRecordBinding(
        AuditEventKind.EVIDENCE,
        summary.evidence_ref,
        1,
        evidence_fingerprint(summary),
        None,
        summary.attempt_ref,
        None,
    )
    receipt = event.receipt
    if (
        receipt.run_key != summary.run_key
        or receipt.producer != summary.source_event.producer
        or receipt.event_ref != summary.source_event.event_ref
        or receipt.binding != expected
        or event.account_ref != summary.account_ref
        or event.session_generation != summary.session_generation
        or event.evidence_refs != (summary.evidence_ref,)
        or event.verdict_refs != ()
        or event.policy_outcome is not None
        or event.send_status is not None
    ):
        raise ValueError("Evidence audit binding mismatch")


def validate_comparison_audit(payload: ComparisonPayload, event: AuditEvent) -> None:
    """Check comparison digest and diagnostic metadata, not journal authenticity."""
    if type(payload) is not ComparisonPayload or type(event) is not AuditEvent:
        raise TypeError("expected exact ComparisonPayload and AuditEvent")
    validate_record(payload)
    validate_record(event)
    from abc2lab_contracts.fingerprint import comparison_fingerprint

    binding = event.receipt.binding
    if (
        event.receipt.run_key != payload.run_key
        or binding.event_kind is not AuditEventKind.COMPARISON
        or binding.record_ref != payload.comparison_ref
        or binding.record_revision != 1
        or binding.record_fingerprint != comparison_fingerprint(payload)
        or binding.request_ref is not None
        or binding.attempt_ref is not None
        or binding.binding_id is not None
        or event.case_ref != payload.case_ref
        or event.evidence_refs != (payload.owner_evidence_ref, payload.cross_evidence_ref)
        or event.account_ref is not None
        or event.session_generation is not None
        or event.policy_outcome is not None
        or event.verdict_refs != ()
        or event.send_status is not None
    ):
        raise ValueError("comparison audit binding mismatch")
    _validate_comparison_reasons(payload.signals, event.reason_codes)


def _validate_comparison_reasons(
    signals: ComparisonSignals, reasons: tuple[ReasonCode, ...]
) -> None:
    canary_states = (
        ReasonCode.COMPARISON_CANARY_PASSED,
        ReasonCode.COMPARISON_CANARY_FAILED,
        ReasonCode.COMPARISON_CANARY_UNKNOWN,
    )
    if sum(reason in canary_states for reason in reasons) != 1:
        raise ValueError("comparison audit requires exactly one canary state")
    if ReasonCode.COMPARISON_CANARY_PASSED not in reasons:
        if signals.nontrivial_data_match is not CheckState.UNKNOWN:
            raise ValueError("unverified canary requires unknown data match")
    unknown_reasons = (
        (signals.same_resource, ReasonCode.COMPARISON_SAME_RESOURCE_UNKNOWN),
        (signals.distinct_verified_subjects, ReasonCode.COMPARISON_SUBJECTS_UNKNOWN),
        (signals.owner_normal_data, ReasonCode.COMPARISON_OWNER_DATA_UNKNOWN),
        (signals.cross_normal_data, ReasonCode.COMPARISON_CROSS_DATA_UNKNOWN),
        (signals.nontrivial_data_match, ReasonCode.COMPARISON_DATA_MATCH_UNKNOWN),
        (signals.reflection_excluded, ReasonCode.COMPARISON_REFLECTION_UNKNOWN),
        (signals.template_excluded, ReasonCode.COMPARISON_TEMPLATE_UNKNOWN),
    )
    for state, reason in unknown_reasons:
        if (state is CheckState.UNKNOWN) != (reason in reasons):
            raise ValueError("comparison unknown signal/reason mismatch")
