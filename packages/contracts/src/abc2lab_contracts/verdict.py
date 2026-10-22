"""Judge-owned verdict content; judgement and source verification stay in Judge."""

from dataclasses import dataclass
from enum import StrEnum

from abc2lab_contracts._validation import ContractRecord
from abc2lab_contracts.primitives import (
    AuditLink,
    CheckState,
    ReasonCode,
    Ref,
    Revision,
    RunKey,
    SourceVersion,
)


class VerdictValue(StrEnum):
    """Separate findings, unresolved conclusions and verified policy permission."""

    CONFIRMED = "CONFIRMED"
    SUSPECTED = "SUSPECTED"
    UNDECIDABLE = "UNDECIDABLE"
    ALLOWED = "ALLOWED"


@dataclass(frozen=True, slots=True)
class Verdict(ContractRecord):
    """Carry verdict.v2 structure without authenticating policy or reason claims.

    Judge independently verifies signals and excludes verified allow policies
    from SUSPECTED. A reason label alone does not prove policy provenance.
    ALLOWED also requires service-verified B identity and registered permission;
    identity_check measures distinct A/B subjects, not B verification alone,
    and data_check measures cross-data exposure, not policy authorization.
    """

    run_key: RunKey
    verdict_ref: Ref
    revision: Revision
    case_ref: Ref
    value: VerdictValue
    policy_check: CheckState
    identity_check: CheckState
    data_check: CheckState
    expected_policy_source: SourceVersion | None
    comparison_ref: Ref | None
    evidence_refs: tuple[Ref, ...]
    oracle_version: SourceVersion
    source_event: AuditLink
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.value is not VerdictValue.CONFIRMED and not self.reason_codes:
            raise ValueError("unconfirmed verdict requires a reason")
        if self.value is VerdictValue.CONFIRMED:
            if any(
                check is not CheckState.YES
                for check in (self.policy_check, self.identity_check, self.data_check)
            ):
                raise ValueError("confirmed verdict requires all three checks")
            if (
                self.expected_policy_source is None
                or self.comparison_ref is None
                or not self.evidence_refs
            ):
                raise ValueError("confirmed verdict requires policy, comparison and Evidence refs")
        elif self.value is VerdictValue.SUSPECTED:
            if (
                self.policy_check is not CheckState.UNKNOWN
                or self.identity_check is not CheckState.YES
                or self.data_check is not CheckState.YES
            ):
                raise ValueError(
                    "suspected verdict requires unknown policy and verified identity/data"
                )
            if self.comparison_ref is None or not self.evidence_refs:
                raise ValueError("suspected verdict requires comparison and Evidence refs")
        elif self.value is VerdictValue.ALLOWED:
            if self.policy_check is not CheckState.NO or self.expected_policy_source is None:
                raise ValueError("allowed verdict requires no policy violation and a policy source")
            if not any(
                reason in (ReasonCode.POLICY_ALLOWS, ReasonCode.SHARING_OR_DELEGATION_ALLOWS)
                for reason in self.reason_codes
            ):
                raise ValueError(
                    "allowed verdict requires a policy/sharing/delegation allow reason"
                )
