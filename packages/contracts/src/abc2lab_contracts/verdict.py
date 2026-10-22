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
    """Keep an unresolved diagnostic conclusion distinct from confirmed findings."""

    CONFIRMED = "CONFIRMED"
    SUSPECTED = "SUSPECTED"
    UNDECIDABLE = "UNDECIDABLE"


@dataclass(frozen=True, slots=True)
class Verdict(ContractRecord):
    """Carry immutable verdict content before and after its producer audit commit."""

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
        elif not self.reason_codes:
            raise ValueError("unconfirmed verdict requires a reason")
