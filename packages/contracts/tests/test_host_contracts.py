"""Host public shape, failure semantics, and versioned audit normalization."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from abc2lab_contracts.host import (
    AuditCompleteness,
    GetRunStatusRequest,
    GetRunStatusResult,
    HostPort,
    RunHandle,
    RunState,
    RunStatus,
    SendCounts,
    StartRunRequest,
    StartRunResult,
    StopReceipt,
    StopRunRequest,
    StopState,
    TaskKind,
    TaskState,
    TaskSummary,
)
from abc2lab_contracts.host_audit import (
    RunAuditRecord,
    TaskAuditRecord,
    normalize_attempt_summaries,
    normalize_reason_codes,
)
from abc2lab_contracts.primitives import (
    AttemptSummary,
    AuditLink,
    ReadContext,
    ReasonCode,
    ResultStatus,
    RunKey,
    SendStatus,
)


def _run() -> RunKey:
    return RunKey("org", "target", "env", "run")


def _now() -> datetime:
    return datetime(2026, 10, 22, tzinfo=UTC)


def _context() -> ReadContext:
    return ReadContext("caller", "authorization")


def _attempt() -> AttemptSummary:
    return AttemptSummary(_run(), "request-1", "attempt-1", SendStatus.UNKNOWN, (), ())


def _snapshot() -> RunStatus:
    return RunStatus(
        _run(),
        1,
        RunState.QUEUED,
        (),
        SendCounts(0, 0, 0),
        AuditCompleteness.UNKNOWN,
        AuditCompleteness.UNKNOWN,
        (),
    )


def test_start_requires_context_and_separates_confirmation_from_uncertainty() -> None:
    request = StartRunRequest("org", "target", "env", "reg", "submit", _context())
    assert request.submission_ref == "submit"
    with pytest.raises(TypeError):
        replace(request, context=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        replace(request, registration_ref="")
    handle = RunHandle(_run(), _now())
    assert StartRunResult(ResultStatus.COMPLETE, handle, ()).run == handle
    assert StartRunResult(ResultStatus.PARTIAL, None, (ReasonCode.AUDIT_GAP,)).run is None
    assert StartRunResult(ResultStatus.FAILED, None, (ReasonCode.QUEUE_FULL,)).run is None
    for status, run, reasons in (
        (ResultStatus.COMPLETE, None, ()),
        (ResultStatus.PARTIAL, handle, (ReasonCode.AUDIT_GAP,)),
        (ResultStatus.FAILED, handle, (ReasonCode.QUEUE_FULL,)),
        (ResultStatus.PARTIAL, None, ()),
        (ResultStatus.FAILED, None, ()),
    ):
        with pytest.raises(ValueError):
            StartRunResult(status, run, reasons)


def test_status_and_stop_are_explicit_authorized_requests() -> None:
    assert GetRunStatusRequest(_run(), _context()).context.caller_ref == "caller"
    assert StopRunRequest(_run(), _context()).context.authorization_ref == "authorization"
    with pytest.raises(TypeError):
        GetRunStatusRequest(_run(), None)  # type: ignore[arg-type]
    complete = GetRunStatusResult(_run(), ResultStatus.COMPLETE, _snapshot(), ())
    assert complete.run_status is not None
    assert (
        GetRunStatusResult(_run(), ResultStatus.FAILED, None, (ReasonCode.NOT_FOUND,)).run_status
        is None
    )
    assert (
        GetRunStatusResult(
            _run(), ResultStatus.PARTIAL, _snapshot(), (ReasonCode.AUDIT_GAP,)
        ).status
        is ResultStatus.PARTIAL
    )
    with pytest.raises(ValueError):
        GetRunStatusResult(_run(), ResultStatus.FAILED, _snapshot(), (ReasonCode.NOT_FOUND,))
    with pytest.raises(ValueError):
        GetRunStatusResult(_run(), ResultStatus.COMPLETE, _snapshot(), (ReasonCode.AUDIT_GAP,))
    with pytest.raises(ValueError):
        GetRunStatusResult(
            RunKey("else", "target", "env", "run"), ResultStatus.COMPLETE, _snapshot(), ()
        )


def test_stop_ack_does_not_implicitly_complete_cleanup() -> None:
    now = _now()
    receipt = StopReceipt(_run(), ResultStatus.COMPLETE, StopState.REQUESTED, now, ())
    assert receipt.stop_state is StopState.REQUESTED
    receipt = StopReceipt(_run(), ResultStatus.COMPLETE, StopState.STOPPED, now, ())
    assert receipt.requested_at == now
    assert (
        StopReceipt(_run(), ResultStatus.COMPLETE, StopState.NOT_APPLICABLE, None, ()).requested_at
        is None
    )
    assert (
        StopReceipt(
            _run(), ResultStatus.PARTIAL, StopState.UNKNOWN, None, (ReasonCode.AUDIT_GAP,)
        ).status
        is ResultStatus.PARTIAL
    )
    assert (
        StopReceipt(
            _run(), ResultStatus.FAILED, StopState.UNKNOWN, None, (ReasonCode.ACCESS_DENIED,)
        ).status
        is ResultStatus.FAILED
    )
    for status, stop, requested, reasons in (
        (ResultStatus.COMPLETE, StopState.REQUESTED, None, ()),
        (ResultStatus.COMPLETE, StopState.UNKNOWN, None, ()),
        (ResultStatus.PARTIAL, StopState.REQUESTED, now, (ReasonCode.AUDIT_GAP,)),
        (ResultStatus.FAILED, StopState.UNKNOWN, now, (ReasonCode.ACCESS_DENIED,)),
        (ResultStatus.PARTIAL, StopState.UNKNOWN, None, ()),
        (ResultStatus.COMPLETE, StopState.STOPPED, None, ()),
        (ResultStatus.COMPLETE, StopState.NOT_APPLICABLE, now, ()),
    ):
        with pytest.raises(ValueError):
            StopReceipt(_run(), status, stop, requested, reasons)


def test_task_attempts_and_terminal_snapshot_are_bounded_by_consistency() -> None:
    summary = TaskSummary(
        "task",
        1,
        TaskKind.COMPARE,
        "case",
        TaskState.PARTIAL,
        (_attempt(),),
        (ReasonCode.AUDIT_GAP,),
    )
    assert summary.kind is TaskKind.COMPARE
    with pytest.raises(ValueError):
        replace(summary, attempt_summaries=(_attempt(), _attempt()))
    with pytest.raises(ValueError):
        replace(summary, reason_codes=())
    with pytest.raises(ValueError):
        SendCounts(-1, 0, 0)
    with pytest.raises(TypeError):
        SendCounts(True, 0, 0)
    with pytest.raises(ValueError):
        RunStatus(
            _run(),
            2,
            RunState.COMPLETED,
            (replace(summary, state=TaskState.RUNNING),),
            SendCounts(0, 0, 1),
            AuditCompleteness.UNKNOWN,
            AuditCompleteness.UNKNOWN,
            (),
        )
    with pytest.raises(ValueError):
        RunStatus(
            RunKey("other", "target", "env", "run"),
            2,
            RunState.RUNNING,
            (summary,),
            SendCounts(0, 0, 1),
            AuditCompleteness.UNKNOWN,
            AuditCompleteness.UNKNOWN,
            (),
        )


def test_host_audit_rejects_unordered_records_and_conflicting_attempts() -> None:
    later = _now() + timedelta(minutes=1)
    run = RunAuditRecord(_run(), "reg", "submit", 1, RunState.QUEUED, _now(), later, ())
    assert run.revision == 1
    with pytest.raises(ValueError):
        replace(run, updated_at=_now() - timedelta(seconds=1))
    with pytest.raises(ValueError):
        replace(run, revision=0)
    with pytest.raises(ValueError):
        replace(run, reason_codes=(ReasonCode.QUEUE_FULL, ReasonCode.AUDIT_GAP))
    first = replace(_attempt(), audit_links=(AuditLink("gateway", "event-1"),))
    second = replace(_attempt(), request_ref="request-2", attempt_ref="attempt-2")
    normalized = normalize_attempt_summaries((second, first, first))
    assert normalized == (first, second)
    record = TaskAuditRecord(
        _run(), "task", 1, TaskKind.COMPARE, "case", TaskState.QUEUED, normalized, _now(), later, ()
    )
    assert record.attempt_summaries == normalized
    with pytest.raises(ValueError, match="normalized"):
        replace(record, attempt_summaries=(second, first))
    with pytest.raises(ValueError, match="conflicting attempt"):
        normalize_attempt_summaries((first, replace(first, send_status=SendStatus.SENT)))
    assert normalize_reason_codes(
        (ReasonCode.QUEUE_FULL, ReasonCode.AUDIT_GAP, ReasonCode.AUDIT_GAP)
    ) == (ReasonCode.AUDIT_GAP, ReasonCode.QUEUE_FULL)
    with pytest.raises(ValueError):
        replace(record, reason_codes=(ReasonCode.QUEUE_FULL, ReasonCode.AUDIT_GAP))


def test_host_port_exposes_three_async_operations() -> None:
    import inspect

    assert inspect.iscoroutinefunction(HostPort.start_run)
    assert inspect.iscoroutinefunction(HostPort.get_status)
    assert inspect.iscoroutinefunction(HostPort.stop)


def test_finalizing_and_independent_audit_completeness() -> None:
    active = TaskSummary("task", 1, TaskKind.REPORT, None, TaskState.RUNNING, (), ())
    with pytest.raises(ValueError, match="active"):
        replace(_snapshot(), state=RunState.FINALIZING, tasks=(active,))
    finished = replace(active, state=TaskState.PARTIAL, reason_codes=(ReasonCode.AUDIT_GAP,))
    status = replace(
        _snapshot(),
        revision=2,
        state=RunState.COMPLETED,
        tasks=(finished,),
        audit_completeness=AuditCompleteness.UNKNOWN,
        operations_audit_completeness=AuditCompleteness.COMPLETE,
    )
    assert status.state is RunState.COMPLETED
    assert status.audit_completeness is AuditCompleteness.UNKNOWN
    assert status.operations_audit_completeness is AuditCompleteness.COMPLETE
    assert replace(
        status,
        audit_completeness=AuditCompleteness.COMPLETE,
        operations_audit_completeness=AuditCompleteness.UNKNOWN,
    )


def test_status_includes_task_case_and_revision() -> None:
    task = TaskSummary(
        "task",
        3,
        TaskKind.COMPARE,
        "case-A",
        TaskState.PARTIAL,
        (_attempt(),),
        (ReasonCode.AUDIT_GAP,),
    )
    assert task.revision == 3
    assert task.case_ref == "case-A"
    with pytest.raises(ValueError):
        replace(task, revision=0)
    with pytest.raises(ValueError, match="duplicate task attempt"):
        replace(
            task,
            attempt_summaries=(_attempt(), replace(_attempt(), request_ref="different-request")),
        )
    with pytest.raises(ValueError):
        replace(_snapshot(), revision=0)


def test_same_attempt_ref_with_different_request_is_conflict() -> None:
    attempt = _attempt()
    with pytest.raises(ValueError, match="conflicting attempt"):
        normalize_attempt_summaries((attempt, replace(attempt, request_ref="request-other")))


def test_status_failed_lookup_never_reveals_run_snapshot() -> None:
    for reason in (ReasonCode.NOT_FOUND, ReasonCode.ACCESS_DENIED):
        result = GetRunStatusResult(_run(), ResultStatus.FAILED, None, (reason,))
        assert result.run_status is None
    # Service boundary rule: callers without read permission MUST use NOT_FOUND,
    # including stop; a constructor cannot prove the service enforced it.


def test_all_public_requests_require_non_empty_read_context_fields() -> None:
    request = StartRunRequest("org", "target", "env", "reg", "submit", _context())
    for field in ("caller_ref", "authorization_ref"):
        with pytest.raises((TypeError, ValueError)):
            replace(request, context=replace(_context(), **{field: ""}))
    for constructor, args in (
        (GetRunStatusRequest, (_run(), _context())),
        (StopRunRequest, (_run(), _context())),
    ):
        with pytest.raises(TypeError):
            constructor(*args[:-1], context="not-a-read-context")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            constructor(*args[:-1], context=None)  # type: ignore[arg-type]


def test_nested_run_and_attempt_types_are_not_accepted_by_public_snapshots() -> None:
    with pytest.raises(TypeError):
        replace(_snapshot(), run_key="run")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        replace(_snapshot(), send_counts={"sent": 0})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        replace(_snapshot(), tasks=(object(),))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        replace(_attempt(), audit_links=(object(),))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        replace(_attempt(), reason_codes=("audit_gap",))  # type: ignore[arg-type]


def test_finalizing_and_terminal_states_reject_every_active_task_state() -> None:
    for run_state in (
        RunState.FINALIZING,
        RunState.COMPLETED,
        RunState.FAILED,
        RunState.STOPPED,
    ):
        for task_state in (TaskState.QUEUED, TaskState.RUNNING):
            active = TaskSummary("active", 1, TaskKind.REPORT, None, task_state, (), ())
            reasons = (ReasonCode.INTERNAL_ERROR,) if run_state is RunState.FAILED else ()
            with pytest.raises(ValueError, match="active"):
                replace(_snapshot(), state=run_state, tasks=(active,), reason_codes=reasons)


def test_stop_receipt_accepts_the_complete_matrix_and_partial_timestamp() -> None:
    now = _now()
    valid = (
        (ResultStatus.COMPLETE, StopState.REQUESTED, now, ()),
        (ResultStatus.COMPLETE, StopState.STOPPED, now, ()),
        (ResultStatus.COMPLETE, StopState.NOT_APPLICABLE, None, ()),
        (ResultStatus.PARTIAL, StopState.UNKNOWN, now, (ReasonCode.AUDIT_GAP,)),
        (ResultStatus.PARTIAL, StopState.UNKNOWN, None, (ReasonCode.AUDIT_GAP,)),
        (ResultStatus.FAILED, StopState.UNKNOWN, None, (ReasonCode.NOT_FOUND,)),
    )
    for status, stop_state, requested_at, reasons in valid:
        receipt = StopReceipt(_run(), status, stop_state, requested_at, reasons)
        assert receipt.status is status
    invalid = (
        (ResultStatus.COMPLETE, StopState.REQUESTED, None, ()),
        (ResultStatus.COMPLETE, StopState.STOPPED, None, ()),
        (ResultStatus.COMPLETE, StopState.NOT_APPLICABLE, now, ()),
        (ResultStatus.PARTIAL, StopState.UNKNOWN, None, ()),
        (ResultStatus.FAILED, StopState.UNKNOWN, now, (ReasonCode.NOT_FOUND,)),
        (ResultStatus.FAILED, StopState.REQUESTED, None, (ReasonCode.NOT_FOUND,)),
    )
    for status, stop_state, requested_at, reasons in invalid:
        with pytest.raises(ValueError):
            StopReceipt(_run(), status, stop_state, requested_at, reasons)


def test_audit_records_reject_naive_or_backwards_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone"):
        RunAuditRecord(
            _run(),
            "reg",
            "submit",
            1,
            RunState.QUEUED,
            datetime(2026, 1, 1),
            _now(),
            (),
        )
    with pytest.raises(ValueError, match="timezone"):
        TaskAuditRecord(
            _run(),
            "task",
            1,
            TaskKind.COLLECT,
            None,
            TaskState.QUEUED,
            (),
            datetime(2026, 1, 1),
            _now(),
            (),
        )
    with pytest.raises(ValueError, match="precedes"):
        RunAuditRecord(
            _run(),
            "reg",
            "submit",
            1,
            RunState.QUEUED,
            _now(),
            _now() - timedelta(seconds=1),
            (),
        )
    with pytest.raises(ValueError, match="precedes"):
        TaskAuditRecord(
            _run(),
            "task",
            1,
            TaskKind.COLLECT,
            None,
            TaskState.QUEUED,
            (),
            _now(),
            _now() - timedelta(seconds=1),
            (),
        )


def test_attempt_normalization_deduplicates_links_and_rejects_business_conflicts() -> None:
    attempt = replace(
        _attempt(),
        audit_links=(
            AuditLink("z", "event-2"),
            AuditLink("a", "event-1"),
            AuditLink("a", "event-1"),
        ),
        reason_codes=(ReasonCode.QUEUE_FULL, ReasonCode.AUDIT_GAP, ReasonCode.QUEUE_FULL),
    )
    normalized = normalize_attempt_summaries((attempt, attempt))
    assert normalized == (
        replace(
            attempt,
            audit_links=(AuditLink("a", "event-1"), AuditLink("z", "event-2")),
            reason_codes=(ReasonCode.AUDIT_GAP, ReasonCode.QUEUE_FULL),
        ),
    )
    for changed in (
        replace(attempt, audit_links=(AuditLink("other", "event"),)),
        replace(attempt, reason_codes=(ReasonCode.NOT_FOUND,)),
        replace(attempt, send_status=SendStatus.SENT),
        replace(attempt, run_key=RunKey("other", "target", "env", "run")),
    ):
        with pytest.raises(ValueError, match="conflicting attempt"):
            normalize_attempt_summaries((attempt, changed))


def test_attempt_normalization_rejects_tampered_nested_records_before_laundering() -> None:
    tampered_attempt = _attempt()
    object.__setattr__(tampered_attempt, "send_status", "unknown")
    with pytest.raises(TypeError):
        normalize_attempt_summaries((tampered_attempt,))

    tampered_link = AuditLink("gateway", "event-1")
    object.__setattr__(tampered_link, "event_ref", 123)
    tampered_attempt = _attempt()
    object.__setattr__(tampered_attempt, "audit_links", (tampered_link,))
    with pytest.raises(TypeError):
        normalize_attempt_summaries((tampered_attempt,))


def test_read_context_has_no_implicit_default_on_any_public_request() -> None:
    with pytest.raises(TypeError, match="context"):
        StartRunRequest("org", "target", "env", "reg", "submit")  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="context"):
        GetRunStatusRequest(_run())  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="context"):
        StopRunRequest(_run())  # type: ignore[call-arg]


@pytest.mark.parametrize("status", tuple(ResultStatus))
@pytest.mark.parametrize("has_run", (False, True))
@pytest.mark.parametrize("has_reasons", (False, True))
def test_admission_result_state_matrix(
    status: ResultStatus, has_run: bool, has_reasons: bool
) -> None:
    handle = RunHandle(_run(), _now()) if has_run else None
    reasons = (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,) if has_reasons else ()
    allowed = {
        (ResultStatus.COMPLETE, True, False),
        (ResultStatus.PARTIAL, False, True),
        (ResultStatus.FAILED, False, True),
    }
    if (status, has_run, has_reasons) in allowed:
        assert StartRunResult(status, handle, reasons).run == handle
    else:
        with pytest.raises(ValueError):
            StartRunResult(status, handle, reasons)


@pytest.mark.parametrize("status", tuple(ResultStatus))
@pytest.mark.parametrize("has_snapshot", (False, True))
@pytest.mark.parametrize("has_reasons", (False, True))
def test_status_result_state_matrix(
    status: ResultStatus, has_snapshot: bool, has_reasons: bool
) -> None:
    snapshot = _snapshot() if has_snapshot else None
    reasons = (ReasonCode.AUDIT_GAP,) if has_reasons else ()
    allowed = {
        (ResultStatus.COMPLETE, True, False),
        (ResultStatus.PARTIAL, True, True),
        (ResultStatus.FAILED, False, True),
    }
    if (status, has_snapshot, has_reasons) in allowed:
        assert GetRunStatusResult(_run(), status, snapshot, reasons).run_status == snapshot
    else:
        with pytest.raises(ValueError):
            GetRunStatusResult(_run(), status, snapshot, reasons)


@pytest.mark.parametrize("status", tuple(ResultStatus))
@pytest.mark.parametrize("stop_state", tuple(StopState))
@pytest.mark.parametrize("has_timestamp", (False, True))
@pytest.mark.parametrize("has_reasons", (False, True))
def test_stop_result_state_matrix(
    status: ResultStatus, stop_state: StopState, has_timestamp: bool, has_reasons: bool
) -> None:
    stamp = _now() if has_timestamp else None
    reasons = (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,) if has_reasons else ()
    allowed = {
        (ResultStatus.COMPLETE, StopState.REQUESTED, True, False),
        (ResultStatus.COMPLETE, StopState.STOPPED, True, False),
        (ResultStatus.COMPLETE, StopState.NOT_APPLICABLE, False, False),
        (ResultStatus.PARTIAL, StopState.UNKNOWN, False, True),
        (ResultStatus.PARTIAL, StopState.UNKNOWN, True, True),
        (ResultStatus.FAILED, StopState.UNKNOWN, False, True),
    }
    if (status, stop_state, has_timestamp, has_reasons) in allowed:
        assert StopReceipt(_run(), status, stop_state, stamp, reasons).stop_state is stop_state
    else:
        with pytest.raises(ValueError):
            StopReceipt(_run(), status, stop_state, stamp, reasons)
