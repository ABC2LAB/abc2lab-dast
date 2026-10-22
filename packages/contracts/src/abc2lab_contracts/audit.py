"""Immutable audit records and read/verification contracts for C2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from abc2lab_contracts._validation import ContractRecord, require_fingerprint
from abc2lab_contracts.primitives import (
    AuditLink,
    CaptureStatus,
    Purpose,
    ReadContext,
    ReasonCode,
    Ref,
    ResultStatus,
    Revision,
    RunKey,
    SendStatus,
    UtcTime,
)


class VerificationState(StrEnum):
    """State returned after checking a producer's committed record."""

    VERIFIED = "verified"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class AuditEventKind(StrEnum):
    """Closed set of producer record kinds understood by the S1 audit boundary."""

    RUN = "run"
    TASK = "task"
    IDENTITY = "identity"
    OBSERVATION = "observation"
    EXPECTED_POLICY = "expected_policy"
    POLICY_DECISION = "policy_decision"
    REQUEST_INTENT = "request_intent"
    ATTEMPT = "attempt"
    EVIDENCE = "evidence"
    COMPARISON = "comparison"
    VERDICT = "verdict"


class PolicyOutcome(StrEnum):
    """Policy outcome carried by an audit event."""

    ALLOW = "allow"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class RequestIntentRecord(ContractRecord):
    """Capture the secret-free intent committed before transport."""

    run_key: RunKey
    request_ref: Ref
    attempt_ref: Ref
    binding_id: Ref
    operation_ref: Ref
    operation_revision: Revision
    purpose: Purpose
    account_ref: Ref | None
    session_generation: int | None
    decision_ref: Ref
    evaluated_view_fingerprint: str
    created_at: UtcTime

    def _validate_invariants(self) -> None:
        require_fingerprint(self.evaluated_view_fingerprint)


@dataclass(frozen=True, slots=True)
class AttemptRecord(ContractRecord):
    """Record one transport attempt without retaining request secrets."""

    run_key: RunKey
    request_ref: Ref
    attempt_ref: Ref
    revision: Revision
    decision_ref: Ref | None
    binding_id: Ref | None
    operation_ref: Ref | None
    account_ref: Ref | None
    session_generation: int | None
    send_status: SendStatus
    capture_status: CaptureStatus
    occurred_at: UtcTime
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        valid_pairs = {
            (SendStatus.SENT, CaptureStatus.CAPTURED),
            (SendStatus.SENT, CaptureStatus.UNAVAILABLE),
            (SendStatus.NOT_SENT, CaptureStatus.NOT_APPLICABLE),
            (SendStatus.UNKNOWN, CaptureStatus.INDETERMINATE),
        }
        if (self.send_status, self.capture_status) not in valid_pairs:
            raise ValueError("invalid send and capture status combination")


@dataclass(frozen=True, slots=True)
class AuditRecordBinding(ContractRecord):
    """Identify the exact immutable record covered by a receipt."""

    event_kind: AuditEventKind
    record_ref: Ref
    record_revision: Revision
    record_fingerprint: str
    request_ref: Ref | None
    attempt_ref: Ref | None
    binding_id: Ref | None

    def _validate_invariants(self) -> None:
        require_fingerprint(self.record_fingerprint)
        if self.event_kind is AuditEventKind.ATTEMPT:
            if self.attempt_ref != self.record_ref or self.request_ref is None:
                raise ValueError("attempt audit binding requires matching attempt and request refs")
        if self.event_kind is AuditEventKind.EVIDENCE and self.attempt_ref is None:
            raise ValueError("Evidence audit binding requires an attempt ref")
        if self.event_kind is AuditEventKind.COMPARISON and any(
            value is not None for value in (self.request_ref, self.attempt_ref, self.binding_id)
        ):
            raise ValueError("comparison audit binding cannot carry request/attempt/binding refs")


@dataclass(frozen=True, slots=True)
class AuditReceipt(ContractRecord):
    """Proof reference returned by a producer after journal commit."""

    run_key: RunKey
    producer: Ref
    event_ref: Ref
    sequence: Revision
    binding: AuditRecordBinding
    committed_at: UtcTime

    def _validate_invariants(self) -> None:
        if self.sequence < 1:
            raise ValueError("audit sequence must be positive")


@dataclass(frozen=True, slots=True)
class AuditEvent(ContractRecord):
    """Journal event with causal links and bounded public metadata."""

    receipt: AuditReceipt
    causal_links: tuple[AuditLink, ...]
    goal_ref: Ref | None
    task_ref: Ref | None
    case_ref: Ref | None
    account_ref: Ref | None
    session_generation: int | None
    evidence_refs: tuple[Ref, ...]
    verdict_refs: tuple[Ref, ...]
    occurred_at: UtcTime
    recorded_at: UtcTime
    producer_instance_ref: Ref
    elapsed_ms: int
    policy_outcome: PolicyOutcome | None
    send_status: SendStatus | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.elapsed_ms < 0:
            raise ValueError("elapsed milliseconds must not be negative")


@dataclass(frozen=True, slots=True)
class AuditVerifyRequest(ContractRecord):
    """Request a producer-side verification of a committed record."""

    run_key: RunKey
    receipt: AuditReceipt
    expected: AuditRecordBinding


@dataclass(frozen=True, slots=True)
class AuditVerifyResult(ContractRecord):
    """Result of producer-side receipt verification."""

    run_key: RunKey
    state: VerificationState
    reason_codes: tuple[ReasonCode, ...]


@dataclass(frozen=True, slots=True)
class AuditReadRequest(ContractRecord):
    """Read one stable page from a producer's audit journal."""

    run_key: RunKey
    context: ReadContext
    producer: Ref
    cursor: Ref | None
    snapshot: Ref | None
    limit: int

    def _validate_invariants(self) -> None:
        if not 1 <= self.limit <= 100:
            raise ValueError("audit page limit must be between one and one hundred")
        if self.cursor is not None and self.snapshot is None:
            raise ValueError("audit cursor requires a snapshot")


@dataclass(frozen=True, slots=True)
class AuditPage(ContractRecord):
    """A page and journal watermarks returned by a producer reader."""

    run_key: RunKey
    status: ResultStatus
    producer: Ref
    events: tuple[AuditEvent, ...]
    next_cursor: Ref | None
    snapshot: Ref | None
    first_sequence: int | None
    committed_through: int | None
    terminal_sequence: int | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.next_cursor is not None and self.snapshot is None:
            raise ValueError("audit next cursor requires a snapshot")
        for name in ("first_sequence", "committed_through", "terminal_sequence"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must not be negative")
        if self.first_sequence is not None:
            if self.first_sequence < 1:
                raise ValueError("audit first sequence must be positive")
            if self.committed_through is not None and self.first_sequence > self.committed_through:
                raise ValueError("first sequence cannot exceed committed watermark")
        if self.terminal_sequence is not None and self.committed_through is not None:
            if self.committed_through > self.terminal_sequence:
                raise ValueError("committed watermark cannot exceed terminal watermark")
        if self.status is ResultStatus.COMPLETE and self.terminal_sequence == 0:
            if self.events or self.first_sequence is not None or self.committed_through != 0:
                raise ValueError("sealed empty audit page must have zero watermarks and no events")
        if self.committed_through == 0 or self.terminal_sequence == 0:
            if not (
                self.status is ResultStatus.COMPLETE
                and self.first_sequence is None
                and self.committed_through == 0
                and self.terminal_sequence == 0
                and not self.events
            ):
                raise ValueError("zero watermarks require a confirmed sealed empty journal")
