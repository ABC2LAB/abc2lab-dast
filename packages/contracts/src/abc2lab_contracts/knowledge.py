"""C4 Knowledge requests and results shared with Host and producer services."""

from dataclasses import dataclass
from enum import StrEnum

from abc2lab_contracts._validation import ContractRecord
from abc2lab_contracts.primitives import (
    ReadContext,
    ReasonCode,
    Ref,
    ResultStatus,
    Revision,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.projection import ProjectionEvent

MAX_CASE_READ_LIMIT = 100


class DiscoveryKind(StrEnum):
    """Distinguish registered seeds from observed discovery hints."""

    REGISTERED_SEED = "registered_seed"
    OBSERVED_LINK = "observed_link"


class ProjectionDisposition(StrEnum):
    """Separate graph application, idempotent replay and unverified submissions."""

    APPLIED = "applied"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
    DEFERRED = "deferred"


@dataclass(frozen=True, slots=True)
class CandidateHint(ContractRecord):
    """Carry a redacted discovery hint without a Knowledge-assigned identity."""

    operation_ref: Ref
    resource_ref: Ref | None
    discovery_kind: DiscoveryKind
    source: SourceVersion
    evidence_refs: tuple[Ref, ...]
    unresolved: tuple[ReasonCode, ...]


@dataclass(frozen=True, slots=True)
class Candidate(ContractRecord):
    """Identify a Knowledge-owned candidate snapshot without execution authority."""

    run_key: RunKey
    candidate_ref: Ref
    revision: Revision
    operation_ref: Ref
    resource_ref: Ref | None
    source: SourceVersion
    evidence_refs: tuple[Ref, ...]
    unresolved: tuple[ReasonCode, ...]


@dataclass(frozen=True, slots=True)
class CandidateSubmission(ContractRecord):
    """Submit Host-forwarded discovery hints under one run-bound idempotency key."""

    run_key: RunKey
    submission_ref: Ref
    hints: tuple[CandidateHint, ...]


@dataclass(frozen=True, slots=True)
class CandidateAck(ContractRecord):
    """Keep accepted candidates and their graph revision on partial registration."""

    run_key: RunKey
    status: ResultStatus
    candidates: tuple[Candidate, ...]
    knowledge_revision: Revision | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        _validate_candidates(self.run_key, self.candidates)
        if self.status is ResultStatus.FAILED:
            if self.candidates or self.knowledge_revision is not None:
                raise ValueError("failed candidate registration cannot publish candidates/revision")
        elif self.knowledge_revision is None:
            raise ValueError("accepted candidate registration requires a knowledge revision")
        if self.status is ResultStatus.PARTIAL and not self.candidates:
            raise ValueError("partial registration requires accepted candidates")
        if self.status is not ResultStatus.COMPLETE and not self.reason_codes:
            raise ValueError("incomplete candidate registration requires a reason")


@dataclass(frozen=True, slots=True)
class ProjectionSubmission(ContractRecord):
    """Forward one unchanged committed source event to Knowledge."""

    run_key: RunKey
    source_event: ProjectionEvent

    def _validate_invariants(self) -> None:
        if self.source_event.run_key != self.run_key:
            raise ValueError("projection submission run mismatch")


@dataclass(frozen=True, slots=True)
class ProjectionAck(ContractRecord):
    """Do not report a deferred or rejected event as applied graph state."""

    run_key: RunKey
    status: ResultStatus
    disposition: ProjectionDisposition
    knowledge_revision: Revision | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        expected_status = {
            ProjectionDisposition.APPLIED: ResultStatus.COMPLETE,
            ProjectionDisposition.DUPLICATE: ResultStatus.COMPLETE,
            ProjectionDisposition.DEFERRED: ResultStatus.PARTIAL,
            ProjectionDisposition.REJECTED: ResultStatus.FAILED,
        }
        if self.status is not expected_status[self.disposition]:
            raise ValueError("projection disposition/status mismatch")
        if (self.status is ResultStatus.COMPLETE) != (self.knowledge_revision is not None):
            raise ValueError("only applied/duplicate projection has a knowledge revision")
        if self.status is not ResultStatus.COMPLETE and not self.reason_codes:
            raise ValueError("incomplete projection requires a reason")


@dataclass(frozen=True, slots=True)
class CaseReadRequest(ContractRecord):
    """Read explicit candidate refs from a bounded authorized graph snapshot."""

    run_key: RunKey
    context: ReadContext
    candidate_refs: tuple[Ref, ...]
    at_revision: Revision | None
    limit: int

    def _validate_invariants(self) -> None:
        if not 1 <= self.limit <= MAX_CASE_READ_LIMIT:
            raise ValueError("case read limit must be between 1 and 100")


@dataclass(frozen=True, slots=True)
class CaseReadResult(ContractRecord):
    """Preserve partial/denied reads without manufacturing successful absence."""

    run_key: RunKey
    status: ResultStatus
    candidates: tuple[Candidate, ...]
    events: tuple[ProjectionEvent, ...]
    knowledge_revision: Revision | None
    truncated: bool
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        _validate_candidates(self.run_key, self.candidates)
        if any(event.run_key != self.run_key for event in self.events):
            raise ValueError("case read event run mismatch")
        if len({(event.producer, event.event_ref) for event in self.events}) != len(self.events):
            raise ValueError("duplicate case read event")
        if self.status is ResultStatus.FAILED:
            if (
                self.candidates
                or self.events
                or self.knowledge_revision is not None
                or self.truncated
            ):
                raise ValueError("failed case read cannot publish snapshot data")
        elif self.knowledge_revision is None:
            raise ValueError("successful case read requires a knowledge revision")
        if self.truncated and self.status is not ResultStatus.PARTIAL:
            raise ValueError("truncated case read must be partial")
        if self.truncated and ReasonCode.RESULT_LIMIT_EXCEEDED not in self.reason_codes:
            raise ValueError("truncated case read requires result_limit_exceeded")
        if self.status is not ResultStatus.COMPLETE and not self.reason_codes:
            raise ValueError("incomplete case read requires a reason")


def _validate_candidates(run_key: RunKey, candidates: tuple[Candidate, ...]) -> None:
    if any(candidate.run_key != run_key for candidate in candidates):
        raise ValueError("candidate run mismatch")
    if len({candidate.candidate_ref for candidate in candidates}) != len(candidates):
        raise ValueError("duplicate candidate ref")
