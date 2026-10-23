"""Public S1 Host control-plane request, result and state contracts.

Records validate shape and local consistency, not the caller's actual authority,
registration provenance, durable admission or completion of transport cleanup.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from abc2lab_contracts._validation import ContractRecord
from abc2lab_contracts.primitives import (
    AttemptSummary,
    ReadContext,
    ReasonCode,
    Ref,
    ResultStatus,
    Revision,
    RunKey,
    UtcTime,
)

START_REJECTION_REASON_CODES: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.CONFIGURATION_MISSING,
        ReasonCode.NOT_FOUND,
        ReasonCode.ACCESS_DENIED,
        ReasonCode.SCOPE_MISMATCH,
        ReasonCode.IDEMPOTENCY_CONFLICT,
        ReasonCode.QUEUE_FULL,
        ReasonCode.UNSUPPORTED_SCHEMA_VERSION,
        ReasonCode.SOURCE_UNVERIFIED,
    }
)

START_UNCERTAINTY_REASON_CODES: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.AUDIT_COMMIT_FAILED,
        ReasonCode.AUDIT_VERIFICATION_UNKNOWN,
        ReasonCode.AUDIT_GAP,
        ReasonCode.REVISION_UNAVAILABLE,
        ReasonCode.INTERNAL_ERROR,
        ReasonCode.DEADLINE_EXCEEDED,
        ReasonCode.SNAPSHOT_EXPIRED,
    }
)


class RunState(StrEnum):
    """The Host-owned lifecycle of an accepted run."""

    QUEUED = "queued"
    RUNNING = "running"
    STOPPING = "stopping"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class TaskKind(StrEnum):
    """S1 tasks that Host may schedule; internal planning stays private."""

    COLLECT = "collect"
    OBSERVE = "observe"
    COMPARE = "compare"
    JUDGE = "judge"
    REPORT = "report"


class TaskState(StrEnum):
    """Task execution completeness, distinct from transport send status."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuditCompleteness(StrEnum):
    """A run audit is complete only with verified producer journals."""

    COMPLETE = "complete"
    UNKNOWN = "unknown"


class StopState(StrEnum):
    """Distinguish a stop request from confirmed resource cleanup."""

    REQUESTED = "requested"
    STOPPED = "stopped"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class StartRunRequest(ContractRecord):
    """Request admission for an app-registered target, never raw credentials.

    ReadContext carries shared caller/authorization references; its name neither
    grants authority nor limits an operation to reads. Host authorizes admission
    independently on every call, as it does status reads and stop requests.
    """

    organization_ref: Ref
    target_ref: Ref
    environment_ref: Ref
    registration_ref: Ref
    submission_ref: Ref
    context: ReadContext


@dataclass(frozen=True, slots=True)
class RunHandle(ContractRecord):
    """Return the admitted run identity before background diagnosis completes."""

    run_key: RunKey
    created_at: UtcTime


@dataclass(frozen=True, slots=True)
class StartRunResult(ContractRecord):
    """Distinguish admission from uncertainty and a verified rejection reason class.

    Reasons restrict what the provider may claim; they do not prove admission
    or rejection. The service must reconcile the submission's durable original.
    """

    status: ResultStatus
    run: RunHandle | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.COMPLETE:
            if self.run is None or self.reason_codes:
                raise ValueError("complete admission requires a run and no failure reasons")
        elif self.run is not None or not self.reason_codes:
            raise ValueError("unconfirmed or rejected admission cannot publish a run")
        elif self.status is ResultStatus.FAILED:
            if any(reason not in START_REJECTION_REASON_CODES for reason in self.reason_codes):
                raise ValueError("failed admission requires confirmed rejection reasons only")
        elif any(reason not in START_UNCERTAINTY_REASON_CODES for reason in self.reason_codes):
            raise ValueError("partial admission requires uncertainty reasons only")


@dataclass(frozen=True, slots=True)
class GetRunStatusRequest(ContractRecord):
    """Read a specific run with independently verified caller authorization."""

    run_key: RunKey
    context: ReadContext


@dataclass(frozen=True, slots=True)
class SendCounts(ContractRecord):
    """Count known sent/not_sent/unknown attempts without conflating states."""

    sent: int
    not_sent: int
    unknown: int

    def _validate_invariants(self) -> None:
        if any(
            type(value) is not int or value < 0
            for value in (self.sent, self.not_sent, self.unknown)
        ):
            raise ValueError("send counts must be non-negative integers")


@dataclass(frozen=True, slots=True)
class TaskSummary(ContractRecord):
    """Retain public attempts and reasons for one Host task.

    Tuple order is retained without audit normalization; attempt refs are unique.
    Host explicitly normalizes attempts and reasons for TaskAuditRecord instead.
    """

    task_ref: Ref
    revision: Revision
    kind: TaskKind
    case_ref: Ref | None
    state: TaskState
    attempt_summaries: tuple[AttemptSummary, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.state in (TaskState.PARTIAL, TaskState.FAILED, TaskState.CANCELLED):
            if not self.reason_codes:
                raise ValueError("incomplete task requires reason codes")
        attempts = {item.attempt_ref for item in self.attempt_summaries}
        if len(attempts) != len(self.attempt_summaries):
            raise ValueError("duplicate task attempt")


@dataclass(frozen=True, slots=True)
class RunStatus(ContractRecord):
    """Separate the run business revision from the complete public snapshot version.

    Host assigns snapshot_revision consistently with task, count and audit
    changes. Local validation cannot prove version history or completed cleanup.
    """

    run_key: RunKey
    revision: Revision
    snapshot_revision: Revision
    state: RunState
    tasks: tuple[TaskSummary, ...]
    send_counts: SendCounts
    audit_completeness: AuditCompleteness
    operations_audit_completeness: AuditCompleteness
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if len({task.task_ref for task in self.tasks}) != len(self.tasks):
            raise ValueError("duplicate run task ref")
        if any(
            attempt.run_key != self.run_key
            for task in self.tasks
            for attempt in task.attempt_summaries
        ):
            raise ValueError("task attempt run mismatch")
        if self.state in (RunState.FAILED, RunState.STOPPING) and not self.reason_codes:
            raise ValueError("failed/stopping run requires reason codes")
        if self.state in (
            RunState.FINALIZING,
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.STOPPED,
        ) and any(task.state in (TaskState.QUEUED, TaskState.RUNNING) for task in self.tasks):
            raise ValueError("terminal run cannot have active tasks")


@dataclass(frozen=True, slots=True)
class GetRunStatusResult(ContractRecord):
    """Describe lookup completeness separately from the run's audit state.

    A coherent, full snapshot is COMPLETE even with UNKNOWN audit completeness.
    PARTIAL means the lookup returned only a coherent, versioned partial view;
    audit UNKNOWN or unfinished/failed tasks alone do not make lookup PARTIAL.
    No coherent snapshot version means FAILED with REVISION_UNAVAILABLE.
    """

    run_key: RunKey
    status: ResultStatus
    run_status: RunStatus | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if ReasonCode.ACCESS_DENIED in self.reason_codes:
            raise ValueError("status lookup must conceal denied run access as not_found")
        if ReasonCode.NOT_FOUND in self.reason_codes and (
            self.status is not ResultStatus.FAILED or self.reason_codes != (ReasonCode.NOT_FOUND,)
        ):
            raise ValueError("not_found lookup requires an exact single failed reason")
        if (
            ReasonCode.REVISION_UNAVAILABLE in self.reason_codes
            and self.status is not ResultStatus.FAILED
        ):
            raise ValueError("unavailable snapshot revision requires a failed lookup")
        if self.status is ResultStatus.FAILED:
            if self.run_status is not None or not self.reason_codes:
                raise ValueError("failed lookup must have no snapshot and a reason")
            return
        if self.run_status is None or self.run_status.run_key != self.run_key:
            raise ValueError("successful/partial lookup requires matching snapshot")
        if (self.status is ResultStatus.PARTIAL) != bool(self.reason_codes):
            raise ValueError("partial lookup requires reasons; complete does not")


@dataclass(frozen=True, slots=True)
class StopRunRequest(ContractRecord):
    """Request stop without assuming outstanding transport has ceased."""

    run_key: RunKey
    context: ReadContext


@dataclass(frozen=True, slots=True)
class StopReceipt(ContractRecord):
    """Separate accepted stop, confirmed cleanup, and uncertain/rejected stop."""

    run_key: RunKey
    status: ResultStatus
    stop_state: StopState
    requested_at: UtcTime | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.COMPLETE:
            if self.stop_state is StopState.UNKNOWN or self.reason_codes:
                raise ValueError("complete stop cannot be unknown or contain failures")
            if self.stop_state is StopState.REQUESTED and self.requested_at is None:
                raise ValueError("new stop request requires requested_at")
            if self.stop_state is StopState.NOT_APPLICABLE and self.requested_at is not None:
                raise ValueError("non-applicable stop cannot claim an accepted request timestamp")
            if self.stop_state is StopState.STOPPED and self.requested_at is None:
                raise ValueError("confirmed stopped run needs the original stop-request time")
        else:
            if self.stop_state is not StopState.UNKNOWN or not self.reason_codes:
                raise ValueError("failed/uncertain stop must be unknown with reasons")
            if self.status is ResultStatus.FAILED and self.requested_at is not None:
                raise ValueError("rejected stop cannot claim a new request timestamp")


class HostPort(Protocol):
    """Authorize each control call without exposing an unreadable run's existence.

    ReadContext is not authorization proof. Recheck it on repeated calls too;
    get_status and stop return the same NOT_FOUND for absent and unreadable runs.
    """

    async def start_run(self, request: StartRunRequest) -> StartRunResult:
        """Confirm admission, distinguish unknown commit and reject without double-enqueue."""
        ...

    async def get_status(self, request: GetRunStatusRequest) -> GetRunStatusResult:
        """Read one versioned authorized snapshot without waiting for transport."""
        ...

    async def stop(self, request: StopRunRequest) -> StopReceipt:
        """Preserve prior cancellation; do not accept a new stop in FINALIZING.

        After read authorization, atomically inspect lifecycle and accepted
        intent. A new FINALIZING stop is NOT_APPLICABLE with no timestamp;
        a prior stop retains its timestamp and REQUESTED until cleanup is
        verified, then STOPPED. Uncertain intent/cleanup remains UNKNOWN.
        No result reopens sealed diagnostics or proves that traffic was recalled.
        """
        ...
