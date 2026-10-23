"""Host public shape, failure semantics, and versioned audit normalization."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from abc2lab_contracts.host import (
    START_REJECTION_REASON_CODES,
    START_UNCERTAINTY_REASON_CODES,
    STATUS_LOOKUP_FAILURE_REASON_CODES,
    STATUS_LOOKUP_PARTIAL_REASON_CODES,
    STOP_REJECTION_REASON_CODES,
    STOP_UNCERTAINTY_REASON_CODES,
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
    assert START_REJECTION_REASON_CODES.isdisjoint(START_UNCERTAINTY_REASON_CODES)
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
            _run(),
            ResultStatus.PARTIAL,
            _snapshot(),
            (ReasonCode.INTERNAL_ERROR,),
            missing_task_refs=("task-unavailable",),
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
    with pytest.raises(ValueError):
        GetRunStatusResult(_run(), ResultStatus.FAILED, None, (ReasonCode.ACCESS_DENIED,))
    with pytest.raises(ValueError):
        GetRunStatusResult(
            _run(),
            ResultStatus.FAILED,
            None,
            (ReasonCode.NOT_FOUND, ReasonCode.ACCESS_DENIED),
        )
    with pytest.raises(ValueError):
        GetRunStatusResult(_run(), ResultStatus.PARTIAL, _snapshot(), (ReasonCode.ACCESS_DENIED,))


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


def test_snapshot_revision_is_positive_and_separate_from_run_revision() -> None:
    for invalid in (0, True, "snapshot"):
        with pytest.raises((TypeError, ValueError)):
            replace(_snapshot(), snapshot_revision=invalid)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        RunStatus(
            run_key=_run(),
            revision=1,
            state=RunState.QUEUED,
            tasks=(),
            send_counts=SendCounts(0, 0, 0),
            audit_completeness=AuditCompleteness.UNKNOWN,
            operations_audit_completeness=AuditCompleteness.UNKNOWN,
            reason_codes=(),
        )  # type: ignore[call-arg]
    same_run_new_task = replace(
        _snapshot(),
        tasks=(TaskSummary("task", 1, TaskKind.COLLECT, None, TaskState.COMPLETE, (), ()),),
        snapshot_revision=2,
    )
    assert same_run_new_task.revision == _snapshot().revision
    assert same_run_new_task.snapshot_revision != _snapshot().snapshot_revision
    audit_update = replace(
        _snapshot(),
        audit_completeness=AuditCompleteness.COMPLETE,
        snapshot_revision=3,
    )
    operations_update = replace(
        _snapshot(),
        operations_audit_completeness=AuditCompleteness.COMPLETE,
        snapshot_revision=4,
    )
    assert audit_update.revision == operations_update.revision == _snapshot().revision
    assert audit_update.snapshot_revision != operations_update.snapshot_revision


def test_same_attempt_ref_with_different_request_is_conflict() -> None:
    attempt = _attempt()
    with pytest.raises(ValueError, match="conflicting attempt"):
        normalize_attempt_summaries((attempt, replace(attempt, request_ref="request-other")))


def test_status_failed_lookup_never_reveals_run_snapshot() -> None:
    result = GetRunStatusResult(_run(), ResultStatus.FAILED, None, (ReasonCode.NOT_FOUND,))
    assert result.run_status is None
    with pytest.raises(ValueError):
        GetRunStatusResult(_run(), ResultStatus.FAILED, None, (ReasonCode.ACCESS_DENIED,))
    # Service boundary rule: callers without read permission MUST use NOT_FOUND,
    # including stop; a constructor cannot prove the service enforced it.


def test_not_found_lookup_cannot_add_other_causes_or_duplicates() -> None:
    for reasons in (
        (ReasonCode.NOT_FOUND, ReasonCode.AUDIT_GAP),
        (ReasonCode.NOT_FOUND, ReasonCode.NOT_FOUND),
    ):
        with pytest.raises(ValueError, match="not_found"):
            GetRunStatusResult(_run(), ResultStatus.FAILED, None, reasons)
    with pytest.raises(ValueError, match="not_found"):
        GetRunStatusResult(_run(), ResultStatus.PARTIAL, _snapshot(), (ReasonCode.NOT_FOUND,))


def test_authorized_snapshot_preserves_a_tasks_actual_access_denial() -> None:
    task = TaskSummary(
        "task", 1, TaskKind.COLLECT, None, TaskState.FAILED, (), (ReasonCode.ACCESS_DENIED,)
    )
    snapshot = replace(_snapshot(), snapshot_revision=2, tasks=(task,))
    result = GetRunStatusResult(_run(), ResultStatus.COMPLETE, snapshot, ())
    assert result.run_status is not None
    assert result.run_status.tasks[0].reason_codes == (ReasonCode.ACCESS_DENIED,)


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
    reason = (
        ReasonCode.QUEUE_FULL
        if status is ResultStatus.FAILED
        else ReasonCode.AUDIT_VERIFICATION_UNKNOWN
    )
    reasons = (reason,) if has_reasons else ()
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


@pytest.mark.parametrize("reason", tuple(ReasonCode))
def test_admission_failure_reason_classes_are_closed(reason: ReasonCode) -> None:
    failed = StartRunResult
    if reason in START_REJECTION_REASON_CODES:
        assert failed(ResultStatus.FAILED, None, (reason,)).run is None
    else:
        with pytest.raises(ValueError):
            failed(ResultStatus.FAILED, None, (reason,))
    if reason in START_UNCERTAINTY_REASON_CODES:
        assert failed(ResultStatus.PARTIAL, None, (reason,)).run is None
    else:
        with pytest.raises(ValueError):
            failed(ResultStatus.PARTIAL, None, (reason,))


def test_start_rejects_access_denied_to_prevent_registration_enumeration() -> None:
    """Start cannot reveal an existing but non-startable registration."""
    assert ReasonCode.ACCESS_DENIED not in START_REJECTION_REASON_CODES
    assert StartRunResult(ResultStatus.FAILED, None, (ReasonCode.NOT_FOUND,)).reason_codes == (
        ReasonCode.NOT_FOUND,
    )
    for reason_codes in (
        (ReasonCode.ACCESS_DENIED,),
        (ReasonCode.NOT_FOUND, ReasonCode.ACCESS_DENIED),
        (ReasonCode.NOT_FOUND, ReasonCode.CONFIGURATION_MISSING),
        (ReasonCode.NOT_FOUND, ReasonCode.IDEMPOTENCY_CONFLICT),
    ):
        with pytest.raises(ValueError):
            StartRunResult(ResultStatus.FAILED, None, reason_codes)


def test_start_partial_cannot_publish_access_denied() -> None:
    """A forbidden registration is not an admission uncertainty reason."""
    with pytest.raises(ValueError):
        StartRunResult(ResultStatus.PARTIAL, None, (ReasonCode.ACCESS_DENIED,))


def test_admission_mixed_reason_classes_fail_closed() -> None:
    with pytest.raises(ValueError):
        StartRunResult(
            ResultStatus.FAILED,
            None,
            (ReasonCode.QUEUE_FULL, ReasonCode.AUDIT_GAP),
        )
    with pytest.raises(ValueError):
        StartRunResult(
            ResultStatus.PARTIAL,
            None,
            (ReasonCode.AUDIT_GAP, ReasonCode.QUEUE_FULL),
        )


def test_admission_reason_sets_are_explicit_and_disjoint() -> None:
    assert START_REJECTION_REASON_CODES == frozenset(
        {
            ReasonCode.CONFIGURATION_MISSING,
            ReasonCode.NOT_FOUND,
            ReasonCode.SCOPE_MISMATCH,
            ReasonCode.IDEMPOTENCY_CONFLICT,
            ReasonCode.QUEUE_FULL,
            ReasonCode.UNSUPPORTED_SCHEMA_VERSION,
            ReasonCode.SOURCE_UNVERIFIED,
        }
    )
    assert START_UNCERTAINTY_REASON_CODES == frozenset(
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
    assert set(START_REJECTION_REASON_CODES) | set(START_UNCERTAINTY_REASON_CODES) <= set(
        ReasonCode
    )
    assert set(START_REJECTION_REASON_CODES).isdisjoint(START_UNCERTAINTY_REASON_CODES)


@pytest.mark.parametrize("status", tuple(ResultStatus))
@pytest.mark.parametrize("has_snapshot", (False, True))
@pytest.mark.parametrize("has_reasons", (False, True))
@pytest.mark.parametrize("has_missing_tasks", (False, True))
def test_status_result_state_matrix(
    status: ResultStatus, has_snapshot: bool, has_reasons: bool, has_missing_tasks: bool
) -> None:
    snapshot = _snapshot() if has_snapshot else None
    reason = ReasonCode.NOT_FOUND if status is ResultStatus.FAILED else ReasonCode.INTERNAL_ERROR
    reasons = (reason,) if has_reasons else ()
    missing = ("task-unavailable",) if has_missing_tasks else ()
    allowed = {
        (ResultStatus.COMPLETE, True, False, False),
        (ResultStatus.PARTIAL, True, True, True),
        (ResultStatus.FAILED, False, True, False),
    }
    if (status, has_snapshot, has_reasons, has_missing_tasks) in allowed:
        assert GetRunStatusResult(_run(), status, snapshot, reasons, missing).run_status == snapshot
    else:
        with pytest.raises(ValueError):
            GetRunStatusResult(_run(), status, snapshot, reasons, missing)


def test_unavailable_snapshot_revision_never_publishes_a_partial_snapshot() -> None:
    for reasons in (
        (ReasonCode.REVISION_UNAVAILABLE,),
        (ReasonCode.REVISION_UNAVAILABLE, ReasonCode.INTERNAL_ERROR),
    ):
        failed = GetRunStatusResult(_run(), ResultStatus.FAILED, None, reasons)
        assert failed.run_status is None
        with pytest.raises(ValueError, match="revision"):
            GetRunStatusResult(_run(), ResultStatus.PARTIAL, _snapshot(), reasons)
        with pytest.raises(ValueError):
            GetRunStatusResult(_run(), ResultStatus.COMPLETE, _snapshot(), reasons)
        with pytest.raises(ValueError):
            GetRunStatusResult(_run(), ResultStatus.FAILED, _snapshot(), reasons)


@pytest.mark.parametrize("status", tuple(ResultStatus))
@pytest.mark.parametrize("stop_state", tuple(StopState))
@pytest.mark.parametrize("has_timestamp", (False, True))
@pytest.mark.parametrize("has_reasons", (False, True))
def test_stop_result_state_matrix(
    status: ResultStatus, stop_state: StopState, has_timestamp: bool, has_reasons: bool
) -> None:
    stamp = _now() if has_timestamp else None
    reason = (
        ReasonCode.ACCESS_DENIED
        if status is ResultStatus.FAILED
        else ReasonCode.AUDIT_VERIFICATION_UNKNOWN
    )
    reasons = (reason,) if has_reasons else ()
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


@pytest.mark.parametrize("reason", tuple(ReasonCode))
def test_status_reason_classes_fail_closed(reason: ReasonCode) -> None:
    if reason in STATUS_LOOKUP_FAILURE_REASON_CODES:
        assert GetRunStatusResult(_run(), ResultStatus.FAILED, None, (reason,)).run_status is None
    else:
        with pytest.raises(ValueError):
            GetRunStatusResult(_run(), ResultStatus.FAILED, None, (reason,))
    if reason in STATUS_LOOKUP_PARTIAL_REASON_CODES:
        result = GetRunStatusResult(
            _run(), ResultStatus.PARTIAL, _snapshot(), (reason,), ("task-missing",)
        )
        assert result.missing_task_refs == ("task-missing",)
    else:
        with pytest.raises(ValueError):
            GetRunStatusResult(
                _run(), ResultStatus.PARTIAL, _snapshot(), (reason,), ("task-missing",)
            )


@pytest.mark.parametrize("reason", tuple(ReasonCode))
def test_stop_reason_classes_fail_closed(reason: ReasonCode) -> None:
    if reason in STOP_REJECTION_REASON_CODES:
        assert (
            StopReceipt(_run(), ResultStatus.FAILED, StopState.UNKNOWN, None, (reason,)).status
            is ResultStatus.FAILED
        )
    else:
        with pytest.raises(ValueError):
            StopReceipt(_run(), ResultStatus.FAILED, StopState.UNKNOWN, None, (reason,))
    if reason in STOP_UNCERTAINTY_REASON_CODES:
        assert (
            StopReceipt(_run(), ResultStatus.PARTIAL, StopState.UNKNOWN, None, (reason,)).status
            is ResultStatus.PARTIAL
        )
    else:
        with pytest.raises(ValueError):
            StopReceipt(_run(), ResultStatus.PARTIAL, StopState.UNKNOWN, None, (reason,))


def test_status_and_stop_reason_allowlists_are_explicit() -> None:
    assert STATUS_LOOKUP_FAILURE_REASON_CODES == frozenset(
        {
            ReasonCode.CONFIGURATION_MISSING,
            ReasonCode.NOT_FOUND,
            ReasonCode.REVISION_UNAVAILABLE,
            ReasonCode.SNAPSHOT_EXPIRED,
            ReasonCode.UNSUPPORTED_SCHEMA_VERSION,
            ReasonCode.SOURCE_UNVERIFIED,
            ReasonCode.INTERNAL_ERROR,
            ReasonCode.DEADLINE_EXCEEDED,
        }
    )
    assert STATUS_LOOKUP_PARTIAL_REASON_CODES == frozenset(
        {ReasonCode.INTERNAL_ERROR, ReasonCode.DEADLINE_EXCEEDED}
    )
    assert STOP_REJECTION_REASON_CODES == frozenset(
        {
            ReasonCode.CONFIGURATION_MISSING,
            ReasonCode.NOT_FOUND,
            ReasonCode.ACCESS_DENIED,
            ReasonCode.SCOPE_MISMATCH,
            ReasonCode.UNSUPPORTED_SCHEMA_VERSION,
            ReasonCode.SOURCE_UNVERIFIED,
        }
    )
    assert STOP_UNCERTAINTY_REASON_CODES == frozenset(
        {
            ReasonCode.AUDIT_COMMIT_FAILED,
            ReasonCode.AUDIT_VERIFICATION_UNKNOWN,
            ReasonCode.AUDIT_GAP,
            ReasonCode.REVISION_UNAVAILABLE,
            ReasonCode.REVISION_CONFLICT,
            ReasonCode.INTERNAL_ERROR,
            ReasonCode.DEADLINE_EXCEEDED,
            ReasonCode.SNAPSHOT_EXPIRED,
            ReasonCode.CLEANUP_TIMEOUT,
        }
    )
    assert STOP_REJECTION_REASON_CODES.isdisjoint(STOP_UNCERTAINTY_REASON_CODES)


@pytest.mark.parametrize(
    "reasons",
    (
        (ReasonCode.AUDIT_GAP, ReasonCode.INTERNAL_ERROR),
        (ReasonCode.INTERNAL_ERROR, ReasonCode.COMPARISON_CANARY_PASSED),
        (ReasonCode.INTERNAL_ERROR, ReasonCode.POLICY_ALLOWS),
    ),
)
def test_partial_lookup_cannot_launder_audit_or_diagnostic_reasons(
    reasons: tuple[ReasonCode, ...],
) -> None:
    with pytest.raises(ValueError):
        GetRunStatusResult(
            _run(), ResultStatus.PARTIAL, _snapshot(), reasons, ("task-unavailable",)
        )


def test_stop_cannot_mix_rejection_and_uncertainty_or_diagnostic_reasons() -> None:
    for reasons in (
        (ReasonCode.ACCESS_DENIED, ReasonCode.AUDIT_VERIFICATION_UNKNOWN),
        (ReasonCode.ACCESS_DENIED, ReasonCode.POLICY_ALLOWS),
        (ReasonCode.CLEANUP_TIMEOUT, ReasonCode.COMPARISON_CANARY_PASSED),
    ):
        for status in (ResultStatus.FAILED, ResultStatus.PARTIAL):
            with pytest.raises(ValueError):
                StopReceipt(_run(), status, StopState.UNKNOWN, None, reasons)


@pytest.mark.parametrize(
    "reasons",
    (
        (ReasonCode.NOT_FOUND, ReasonCode.ACCESS_DENIED),
        (ReasonCode.NOT_FOUND, ReasonCode.NOT_FOUND),
        (ReasonCode.NOT_FOUND, ReasonCode.SOURCE_UNVERIFIED),
        (ReasonCode.NOT_FOUND, ReasonCode.INTERNAL_ERROR),
    ),
)
def test_start_and_stop_not_found_never_leak_additional_reasons(
    reasons: tuple[ReasonCode, ...],
) -> None:
    with pytest.raises(ValueError, match="not_found"):
        StartRunResult(ResultStatus.FAILED, None, reasons)
    with pytest.raises(ValueError, match="not_found"):
        StopReceipt(_run(), ResultStatus.FAILED, StopState.UNKNOWN, None, reasons)


@pytest.mark.parametrize("audit", tuple(AuditCompleteness))
@pytest.mark.parametrize("operations", tuple(AuditCompleteness))
def test_complete_lookup_is_independent_of_audit_verification(
    audit: AuditCompleteness, operations: AuditCompleteness
) -> None:
    snapshot = replace(
        _snapshot(),
        audit_completeness=audit,
        operations_audit_completeness=operations,
        reason_codes=(
            (ReasonCode.AUDIT_GAP,) if AuditCompleteness.UNKNOWN in (audit, operations) else ()
        ),
    )
    result = GetRunStatusResult(_run(), ResultStatus.COMPLETE, snapshot, ())
    assert result.status is ResultStatus.COMPLETE
    assert result.run_status == snapshot
    assert result.reason_codes == result.missing_task_refs == ()


def test_partial_lookup_has_explicit_missing_tasks_and_whole_run_counts() -> None:
    task = TaskSummary("task-returned", 1, TaskKind.OBSERVE, None, TaskState.RUNNING, (), ())
    snapshot = replace(
        _snapshot(),
        state=RunState.RUNNING,
        tasks=(task,),
        snapshot_revision=2,
        send_counts=SendCounts(2, 1, 3),
    )
    result = GetRunStatusResult(
        _run(),
        ResultStatus.PARTIAL,
        snapshot,
        (ReasonCode.INTERNAL_ERROR,),
        missing_task_refs=("task-missing-1", "task-missing-2"),
    )
    assert result.run_status == snapshot
    assert set(result.missing_task_refs) | {item.task_ref for item in snapshot.tasks} == {
        "task-returned",
        "task-missing-1",
        "task-missing-2",
    }
    assert result.run_status.send_counts == SendCounts(2, 1, 3)


@pytest.mark.parametrize("missing_refs", ((), ("task-missing", "task-missing"), ("task-returned",)))
def test_partial_lookup_rejects_ambiguous_or_overlapping_missing_tasks(
    missing_refs: tuple[str, ...],
) -> None:
    task = TaskSummary("task-returned", 1, TaskKind.OBSERVE, None, TaskState.RUNNING, (), ())
    snapshot = replace(_snapshot(), tasks=(task,))
    with pytest.raises(ValueError):
        GetRunStatusResult(
            _run(), ResultStatus.PARTIAL, snapshot, (ReasonCode.INTERNAL_ERROR,), missing_refs
        )


@pytest.mark.parametrize("missing_refs", (("",), ["task-missing"], (None,), "task-missing"))
def test_partial_lookup_rejects_invalid_missing_task_reference_types(missing_refs: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        GetRunStatusResult(
            _run(),
            ResultStatus.PARTIAL,
            _snapshot(),
            (ReasonCode.INTERNAL_ERROR,),
            missing_refs,  # type: ignore[arg-type]
        )


def _attempt_task(task_ref: str, attempt: AttemptSummary) -> TaskSummary:
    return TaskSummary(task_ref, 1, TaskKind.OBSERVE, None, TaskState.COMPLETE, (attempt,), ())


def test_run_status_rejects_cross_task_conflicting_attempt_send_status() -> None:
    sent = replace(_attempt(), send_status=SendStatus.SENT)
    not_sent = replace(sent, send_status=SendStatus.NOT_SENT)
    first = _attempt_task("observe", sent)
    second = _attempt_task("compare", not_sent)
    with pytest.raises(ValueError, match="conflicting attempt_ref"):
        replace(_snapshot(), tasks=(first, second), send_counts=SendCounts(1, 1, 0))


@pytest.mark.parametrize(
    "changed_field",
    ("request_ref", "audit_links", "reason_codes"),
)
def test_run_status_rejects_cross_task_conflicting_attempt_metadata(changed_field: str) -> None:
    first_attempt = replace(_attempt(), send_status=SendStatus.SENT)
    if changed_field == "request_ref":
        second_attempt = replace(first_attempt, request_ref="other-request")
    elif changed_field == "audit_links":
        second_attempt = replace(first_attempt, audit_links=(AuditLink("gateway", "other-event"),))
    else:
        second_attempt = replace(first_attempt, reason_codes=(ReasonCode.AUDIT_GAP,))
    with pytest.raises(ValueError, match="conflicting attempt_ref"):
        replace(
            _snapshot(),
            tasks=(
                _attempt_task("observe", first_attempt),
                _attempt_task("compare", second_attempt),
            ),
            send_counts=SendCounts(1, 0, 0),
        )


def test_run_status_reuses_identical_attempt_only_once_across_tasks() -> None:
    sent = replace(_attempt(), send_status=SendStatus.SENT)
    repeated = (_attempt_task("observe", sent), _attempt_task("compare", sent))
    snapshot = replace(_snapshot(), tasks=repeated, send_counts=SendCounts(1, 0, 0))
    result = GetRunStatusResult(_run(), ResultStatus.COMPLETE, snapshot, ())
    assert result.run_status is snapshot
    # Both task summaries remain visible; reuse does not erase provenance.
    assert snapshot.tasks == repeated
    assert result.run_status.send_counts.sent == 1


@pytest.mark.parametrize(
    ("send_status", "counts"),
    [
        (SendStatus.SENT, SendCounts(0, 0, 0)),
        (SendStatus.NOT_SENT, SendCounts(0, 0, 0)),
        (SendStatus.UNKNOWN, SendCounts(0, 0, 0)),
    ],
)
def test_run_status_rejects_visible_attempts_exceeding_counts(
    send_status: SendStatus, counts: SendCounts
) -> None:
    attempt = replace(_attempt(), send_status=send_status)
    with pytest.raises(ValueError, match="visible attempts exceed"):
        replace(_snapshot(), tasks=(_attempt_task("observe", attempt),), send_counts=counts)


def test_complete_lookup_requires_exact_counts_for_all_distinct_attempts() -> None:
    sent = replace(_attempt(), send_status=SendStatus.SENT)
    task = _attempt_task("observe", sent)
    # RunStatus alone cannot know whether more tasks are missing from the lookup.
    snapshot = replace(_snapshot(), tasks=(task,), send_counts=SendCounts(2, 0, 0))
    with pytest.raises(ValueError, match="complete lookup send_counts"):
        GetRunStatusResult(_run(), ResultStatus.COMPLETE, snapshot, ())
    # No other tasks or attempts are missing: the exact count is accepted.
    matching = replace(snapshot, send_counts=SendCounts(1, 0, 0))
    assert GetRunStatusResult(_run(), ResultStatus.COMPLETE, matching, ()).run_status == matching


def test_partial_lookup_accepts_authoritative_counts_above_visible_lower_bound() -> None:
    sent = replace(_attempt(), send_status=SendStatus.SENT)
    snapshot = replace(
        _snapshot(), tasks=(_attempt_task("observe", sent),), send_counts=SendCounts(2, 1, 1)
    )
    partial = GetRunStatusResult(
        _run(), ResultStatus.PARTIAL, snapshot, (ReasonCode.INTERNAL_ERROR,), ("missing-task",)
    )
    assert partial.run_status is snapshot
    with pytest.raises(ValueError, match="complete lookup send_counts"):
        GetRunStatusResult(_run(), ResultStatus.COMPLETE, snapshot, ())


def test_complete_lookup_counts_multiple_send_classes_and_deduplicates_reuse() -> None:
    sent = replace(_attempt(), attempt_ref="sent", send_status=SendStatus.SENT)
    not_sent = replace(_attempt(), attempt_ref="not-sent", send_status=SendStatus.NOT_SENT)
    unknown = replace(_attempt(), attempt_ref="unknown", send_status=SendStatus.UNKNOWN)
    tasks = (
        _attempt_task("collect", sent),
        TaskSummary("observe", 1, TaskKind.OBSERVE, None, TaskState.COMPLETE, (sent, not_sent), ()),
        _attempt_task("compare", unknown),
    )
    snapshot = replace(_snapshot(), tasks=tasks, send_counts=SendCounts(1, 1, 1))
    assert (
        GetRunStatusResult(_run(), ResultStatus.COMPLETE, snapshot, ()).status
        is ResultStatus.COMPLETE
    )
