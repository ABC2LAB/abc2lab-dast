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
    """Request admission for an app-registered target, never raw credentials."""

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
    """COMPLETE admits; PARTIAL is uncertain; FAILED is a confirmed rejection."""

    status: ResultStatus
    run: RunHandle | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.COMPLETE:
            if self.run is None or self.reason_codes:
                raise ValueError("complete admission requires a run and no failure reasons")
        elif self.run is not None or not self.reason_codes:
            raise ValueError("unconfirmed or rejected admission cannot publish a run")


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
    """Retain public attempts and reasons for one Host task."""

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
    """Present one bounded, consistent Host snapshot, not a proof of cleanup."""

    run_key: RunKey
    revision: Revision
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
    """Keep lookup failure distinct from a valid run snapshot."""

    run_key: RunKey
    status: ResultStatus
    run_status: RunStatus | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
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
                raise ValueError("no stop request was accepted for a completed/failed run")
            if self.stop_state is StopState.STOPPED and self.requested_at is None:
                raise ValueError("confirmed stopped run needs the original stop-request time")
        else:
            if self.stop_state is not StopState.UNKNOWN or not self.reason_codes:
                raise ValueError("failed/uncertain stop must be unknown with reasons")
            if self.status is ResultStatus.FAILED and self.requested_at is not None:
                raise ValueError("rejected stop cannot claim a new request timestamp")


class HostPort(Protocol):
    """Async public control boundary; each operation independently authorizes context."""

    async def start_run(self, request: StartRunRequest) -> StartRunResult:
        """Confirm admission, distinguish unknown commit and reject without double-enqueue."""
        ...

    async def get_status(self, request: GetRunStatusRequest) -> GetRunStatusResult:
        """Read an authorized snapshot without waiting for target work semaphores."""
        ...

    async def stop(self, request: StopRunRequest) -> StopReceipt:
        """Publish cancel intent before responding; never fabricate completed cleanup."""
        ...
