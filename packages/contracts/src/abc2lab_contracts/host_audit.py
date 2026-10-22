"""Versioned Host journal payloads with explicit deterministic normalization."""

from __future__ import annotations

from dataclasses import dataclass, replace

from abc2lab_contracts._validation import ContractRecord, validate_record
from abc2lab_contracts.host import RunState, TaskKind, TaskState
from abc2lab_contracts.primitives import (
    AttemptSummary,
    ReasonCode,
    Ref,
    Revision,
    RunKey,
    UtcTime,
)


def normalize_reason_codes(reasons: tuple[ReasonCode, ...]) -> tuple[ReasonCode, ...]:
    """Sort and deduplicate reason codes before a Host audit revision is sealed."""
    if type(reasons) is not tuple or any(type(item) is not ReasonCode for item in reasons):
        raise TypeError("reason codes must be a tuple of ReasonCode")
    return tuple(sorted(set(reasons), key=lambda item: item.value))


def normalize_attempt_summaries(
    attempts: tuple[AttemptSummary, ...],
) -> tuple[AttemptSummary, ...]:
    """Canonicalize public attempt metadata; reject conflicting duplicate refs."""
    if type(attempts) is not tuple or any(type(item) is not AttemptSummary for item in attempts):
        raise TypeError("attempts must be a tuple of AttemptSummary")
    normalized_by_ref: dict[Ref, AttemptSummary] = {}
    for item in attempts:
        validate_record(item)
        links = tuple(
            sorted(set(item.audit_links), key=lambda link: (link.producer, link.event_ref))
        )
        normalized = replace(
            item,
            audit_links=links,
            reason_codes=normalize_reason_codes(item.reason_codes),
        )
        key = normalized.attempt_ref
        previous = normalized_by_ref.get(key)
        if previous is not None and previous != normalized:
            raise ValueError("conflicting attempt refs require audit unknown; cannot deduplicate")
        normalized_by_ref[key] = normalized
    return tuple(normalized_by_ref[key] for key in sorted(normalized_by_ref))


@dataclass(frozen=True, slots=True)
class RunAuditRecord(ContractRecord):
    """Immutable Host run revision for the run.v1 fingerprint and audit binding."""

    run_key: RunKey
    registration_ref: Ref
    submission_ref: Ref
    revision: Revision
    state: RunState
    created_at: UtcTime
    updated_at: UtcTime
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.updated_at < self.created_at:
            raise ValueError("run update precedes creation")
        if self.reason_codes != normalize_reason_codes(self.reason_codes):
            raise ValueError("run audit reason codes must be normalized")
        if self.state in (RunState.STOPPING, RunState.FAILED) and not self.reason_codes:
            raise ValueError("stopping/failed run audit requires reasons")


@dataclass(frozen=True, slots=True)
class TaskAuditRecord(ContractRecord):
    """Immutable Host task revision with no raw request/response material."""

    run_key: RunKey
    task_ref: Ref
    revision: Revision
    kind: TaskKind
    case_ref: Ref | None
    state: TaskState
    attempt_summaries: tuple[AttemptSummary, ...]
    created_at: UtcTime
    updated_at: UtcTime
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.updated_at < self.created_at:
            raise ValueError("task update precedes creation")
        if self.reason_codes != normalize_reason_codes(self.reason_codes):
            raise ValueError("task audit reason codes must be normalized")
        if self.attempt_summaries != normalize_attempt_summaries(self.attempt_summaries):
            raise ValueError("task audit attempts must be normalized")
        if self.state in (TaskState.PARTIAL, TaskState.FAILED, TaskState.CANCELLED):
            if not self.reason_codes:
                raise ValueError("incomplete task audit requires reasons")
        if any(attempt.run_key != self.run_key for attempt in self.attempt_summaries):
            raise ValueError("task audit attempt run mismatch")
