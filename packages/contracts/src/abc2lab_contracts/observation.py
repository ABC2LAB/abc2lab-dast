"""Producer-owned, redacted observation content used by Knowledge projections."""

from dataclasses import dataclass

from abc2lab_contracts._validation import ContractRecord, require_positive
from abc2lab_contracts.primitives import (
    AuditLink,
    ReasonCode,
    Ref,
    ResponseClass,
    RunKey,
    UtcTime,
)


@dataclass(frozen=True, slots=True)
class Observation(ContractRecord):
    """Link an observation to stored Evidence without asserting resource ownership."""

    run_key: RunKey
    observation_ref: Ref
    candidate_ref: Ref
    resource_ref: Ref
    operation_ref: Ref
    account_ref: Ref
    session_generation: int
    identity_ref: Ref
    response_class: ResponseClass
    evidence_ref: Ref
    source_event: AuditLink
    observed_at: UtcTime
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        require_positive("session_generation", self.session_generation)
