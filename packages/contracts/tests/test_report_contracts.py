"""Report public contracts: immutable shape, uncertainty and PoC/result separation."""

from dataclasses import FrozenInstanceError, replace
from inspect import iscoroutinefunction

import pytest
from abc2lab_contracts.host import AuditCompleteness, SendCounts, TaskKind, TaskState, TaskSummary
from abc2lab_contracts.ports import ReportPort as ReexportedReportPort
from abc2lab_contracts.primitives import (
    AttemptSummary,
    AuditLink,
    CheckState,
    ReadContext,
    ReasonCode,
    ResultStatus,
    RunKey,
    SendStatus,
    SourceVersion,
)
from abc2lab_contracts.recipe import RegisteredRequestRecipe
from abc2lab_contracts.report import (
    AuditExpectation,
    AuditGap,
    CaseLimit,
    DiagnosisReport,
    PocAction,
    PocReplayStatus,
    PocReport,
    PocState,
    PocStep,
    ReportInput,
    ReportPort,
    ReportResult,
)
from abc2lab_contracts.verdict import Verdict, VerdictValue


def _run() -> RunKey:
    return RunKey("org", "target", "env", "run")


def _source() -> SourceVersion:
    return SourceVersion("issuer", "source", 1)


def _verdict(value: VerdictValue = VerdictValue.CONFIRMED) -> Verdict:
    return Verdict(
        run_key=_run(),
        verdict_ref="verdict",
        revision=1,
        case_ref="case",
        value=value,
        policy_check=(CheckState.YES if value is VerdictValue.CONFIRMED else CheckState.UNKNOWN),
        identity_check=CheckState.YES,
        data_check=CheckState.YES,
        expected_policy_source=(_source() if value is VerdictValue.CONFIRMED else None),
        comparison_ref="comparison",
        evidence_refs=("owner-evidence", "cross-evidence"),
        oracle_version=_source(),
        source_event=AuditLink("judge", "verdict-event"),
        reason_codes=(
            () if value is VerdictValue.CONFIRMED else (ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,)
        ),
    )


def _recipe() -> RegisteredRequestRecipe:
    return RegisteredRequestRecipe(
        schema_version="poc.v0.1",
        operation_ref="read-order",
        operation_revision=1,
        resource_ref="order",
        resource_binding_ref="order-binding",
        resource_binding_revision=1,
        method="GET",
        origin_placeholder="${REGISTERED_ORIGIN}",
        path_template="/orders/${RESOURCE_ID}",
        parameters=(),
        authentication="fresh_registered_session",
        source=_source(),
    )


def _poc() -> PocReport:
    return PocReport(
        case_ref="case",
        verdict_ref="verdict",
        state=PocState.DOCUMENTED,
        replay_status=PocReplayStatus.NOT_RUN,
        comparison_ref="comparison",
        steps=(
            PocStep(1, PocAction.VERIFY_OWNER, "account-a", "identity-a", None, "id-evidence-a"),
            PocStep(
                2, PocAction.VERIFY_EVALUATED, "account-b", "identity-b", None, "id-evidence-b"
            ),
            PocStep(3, PocAction.READ_OWNER, "account-a", None, _recipe(), "owner-evidence"),
            PocStep(4, PocAction.READ_CROSS, "account-b", None, _recipe(), "cross-evidence"),
        ),
        evidence_refs=(
            "id-evidence-a",
            "id-evidence-b",
            "owner-evidence",
            "cross-evidence",
        ),
        audit_links=(AuditLink("evidence", "event"),),
        reason_codes=(),
    )


def _report(
    *,
    verdict: Verdict | None = None,
    poc: PocReport | None = None,
    completeness: AuditCompleteness = AuditCompleteness.COMPLETE,
    gaps: tuple[AuditGap, ...] = (),
    incomplete_tasks: tuple[str, ...] = (),
) -> DiagnosisReport:
    return DiagnosisReport(
        run_key=_run(),
        report_ref="report-committed",
        verdicts=((verdict or _verdict()),),
        send_counts=SendCounts(2, 1, 1),
        incomplete_task_refs=incomplete_tasks,
        audit_completeness=completeness,
        audit_gaps=gaps,
        evidence_refs=("owner-evidence", "cross-evidence"),
        comparison_refs=("comparison",),
        comparison_limits=(),
        pocs=((poc or _poc()),),
        reason_codes=(),
    )


def test_report_port_is_async_and_reexported() -> None:
    assert ReportPort is ReexportedReportPort
    assert iscoroutinefunction(ReportPort.build_report)


def test_report_input_has_explicit_authorization_and_cutoff_scope() -> None:
    expectation = AuditExpectation("host", 1, None, ("run-event",), (), ())
    request = ReportInput(_run(), ReadContext("caller", "auth"), (), (), (), (), (expectation,))
    assert request.audit_expectations[0].last_sequence is None
    assert AuditExpectation("empty-host", 1, 0, (), (), ()).last_sequence == 0
    with pytest.raises((TypeError, ValueError)):
        replace(request, context=None)  # type: ignore[arg-type]
    with pytest.raises(FrozenInstanceError):
        request.tasks = ()  # type: ignore[misc]

    report_task = TaskSummary("task-report", 1, TaskKind.REPORT, None, TaskState.COMPLETE, (), ())
    with pytest.raises(ValueError, match="Report task"):
        replace(request, tasks=(report_task,))
    foreign_attempt = AttemptSummary(
        RunKey("other", "target", "env", "run"),
        "request",
        "attempt",
        SendStatus.UNKNOWN,
        (),
        (),
    )
    task = TaskSummary(
        "task-compare", 1, TaskKind.COMPARE, "case", TaskState.COMPLETE, (foreign_attempt,), ()
    )
    with pytest.raises(ValueError, match="run mismatch"):
        replace(request, tasks=(task,))
    duplicate_task = TaskSummary(
        "task-compare", 1, TaskKind.COMPARE, "case", TaskState.COMPLETE, (), ()
    )
    with pytest.raises(ValueError, match="duplicate Report input task"):
        replace(request, tasks=(duplicate_task, duplicate_task))
    with pytest.raises(ValueError, match="duplicate report source reference"):
        replace(request, audit_expectations=(expectation, expectation))


def test_audit_expectation_distinguishes_zero_from_unknown_and_preserves_refs() -> None:
    assert AuditExpectation("host", 1, None, ("event",), ("request",), ("attempt",))
    for first, last, events, requests, attempts in (
        (0, None, (), (), ()),
        (True, None, (), (), ()),
        (1, -1, (), (), ()),
        (1, 0, ("event",), (), ()),
        (1, 0, (), ("request",), ()),
        (1, 0, (), (), ("attempt",)),
        (1, None, ("same", "same"), (), ()),
    ):
        with pytest.raises((ValueError, TypeError)):
            AuditExpectation("host", first, last, events, requests, attempts)
    with pytest.raises(ValueError):
        AuditGap("host", None, None, None, ReasonCode.DATA_NO_MATCH)


def test_poc_documented_requires_four_real_reference_steps_and_never_replays() -> None:
    poc = _poc()
    assert poc.state is PocState.DOCUMENTED
    assert poc.replay_status is PocReplayStatus.NOT_RUN
    with pytest.raises(ValueError, match="ordered four-step"):
        replace(poc, steps=poc.steps[:3])
    with pytest.raises(ValueError, match="distinct account"):
        replace(
            poc,
            steps=(poc.steps[0], replace(poc.steps[1], account_ref="account-a"), *poc.steps[2:]),
        )
    with pytest.raises(ValueError, match="distinct Evidence"):
        replace(poc, steps=(*poc.steps[:3], replace(poc.steps[3], evidence_ref="owner-evidence")))
    with pytest.raises(ValueError, match="registered request recipes"):
        replace(poc, steps=(*poc.steps[:3], replace(poc.steps[3], request_recipe=None)))
    with pytest.raises(ValueError, match="same registered object"):
        replace(
            poc,
            steps=(
                *poc.steps[:3],
                replace(
                    poc.steps[3], request_recipe=replace(_recipe(), resource_ref="other-order")
                ),
            ),
        )
    with pytest.raises(ValueError, match="identity steps"):
        replace(poc.steps[0], request_recipe=_recipe())
    with pytest.raises(ValueError, match="requires reasons"):
        replace(poc, state=PocState.INCOMPLETE)
    with pytest.raises(ValueError, match="support/export"):
        replace(poc, state=PocState.UNAVAILABLE, reason_codes=(ReasonCode.POC_EVIDENCE_INCOMPLETE,))


def test_complete_and_partial_report_preserve_verdict_and_poc_separately() -> None:
    complete = _report()
    assert ReportResult(_run(), ResultStatus.COMPLETE, complete, ()).report is complete
    incomplete = replace(
        _poc(),
        state=PocState.INCOMPLETE,
        reason_codes=(ReasonCode.POC_EVIDENCE_INCOMPLETE,),
    )
    partial = _report(poc=incomplete)
    with pytest.raises(ValueError, match="unfinished PoC"):
        ReportResult(_run(), ResultStatus.COMPLETE, partial, ())
    assert (
        ReportResult(
            _run(), ResultStatus.PARTIAL, partial, (ReasonCode.POC_EVIDENCE_INCOMPLETE,)
        ).report
        is partial
    )
    # An accurately described SUSPECTED verdict is a complete report even though
    # its PoC is incomplete: the lack of a confirmed vulnerability is not a failure.
    suspected = _report(
        verdict=_verdict(VerdictValue.SUSPECTED),
        poc=replace(
            incomplete,
            reason_codes=(ReasonCode.POC_VERDICT_UNCONFIRMED,),
        ),
    )
    assert (
        ReportResult(_run(), ResultStatus.COMPLETE, suspected, ()).status is ResultStatus.COMPLETE
    )
    with pytest.raises(ValueError, match="unconfirmed verdict"):
        _report(verdict=_verdict(VerdictValue.SUSPECTED))


def test_audit_gaps_force_partial_but_keep_report_and_unknown_transport() -> None:
    gap = AuditGap("gateway", "request", "attempt", None, ReasonCode.AUDIT_GAP)
    partial = _report(completeness=AuditCompleteness.UNKNOWN, gaps=(gap,))
    assert partial.send_counts.unknown == 1
    with pytest.raises(ValueError, match="incomplete diagnostic coverage"):
        ReportResult(_run(), ResultStatus.COMPLETE, partial, ())
    assert (
        ReportResult(_run(), ResultStatus.PARTIAL, partial, (ReasonCode.AUDIT_GAP,)).report
        is partial
    )
    with pytest.raises(ValueError, match="preserve a producer gap"):
        replace(partial, audit_gaps=())
    with pytest.raises(ValueError, match="cannot contain gaps"):
        replace(partial, audit_completeness=AuditCompleteness.COMPLETE)
    with pytest.raises(ValueError, match="incomplete diagnostic coverage"):
        ReportResult(_run(), ResultStatus.COMPLETE, _report(incomplete_tasks=("task-failed",)), ())


def test_report_failures_never_publish_uncommitted_artifacts() -> None:
    assert ReportResult(_run(), ResultStatus.FAILED, None, (ReasonCode.NOT_FOUND,)).report is None
    with pytest.raises(ValueError, match="cannot return a report"):
        ReportResult(_run(), ResultStatus.FAILED, _report(), (ReasonCode.NOT_FOUND,))
    with pytest.raises(ValueError, match="failure-class"):
        ReportResult(_run(), ResultStatus.FAILED, None, (ReasonCode.ACCESS_DENIED,))
    with pytest.raises(ValueError, match="requires same-run report"):
        ReportResult(_run(), ResultStatus.PARTIAL, None, (ReasonCode.AUDIT_GAP,))
    with pytest.raises(ValueError, match="requires reasons"):
        ReportResult(_run(), ResultStatus.PARTIAL, _report(), ())
    with pytest.raises(ValueError, match="cannot have"):
        ReportResult(_run(), ResultStatus.COMPLETE, _report(), (ReasonCode.AUDIT_GAP,))


def test_case_limit_retains_evidence_from_failed_comparison() -> None:
    limit = CaseLimit(
        "case", ResultStatus.PARTIAL, ("stored-a",), None, (ReasonCode.COMPARISON_INCOMPLETE,)
    )
    assert limit.stored_evidence_refs == ("stored-a",)
    with pytest.raises(ValueError, match="requires reasons"):
        replace(limit, reason_codes=())
