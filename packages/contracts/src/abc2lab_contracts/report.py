"""S1 Report public records, audit scope and read-only generation protocol.

Local validation checks immutable structure, not producer provenance, authorized
reads, journal sealing, a persisted report artifact or a reproduced exploit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from abc2lab_contracts._validation import ContractRecord, require_positive
from abc2lab_contracts.host import AuditCompleteness, SendCounts, TaskKind, TaskSummary
from abc2lab_contracts.observation import Observation
from abc2lab_contracts.primitives import (
    AuditLink,
    ReadContext,
    ReasonCode,
    Ref,
    ResultStatus,
    RunKey,
)
from abc2lab_contracts.recipe import RegisteredRequestRecipe
from abc2lab_contracts.verdict import Verdict, VerdictValue
from abc2lab_contracts.webdiag import AccessCompareResult

REPORT_FAILURE_REASON_CODES: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.NOT_FOUND,
        ReasonCode.CONFIGURATION_MISSING,
        ReasonCode.SCOPE_MISMATCH,
        ReasonCode.SOURCE_UNVERIFIED,
        ReasonCode.REVISION_UNAVAILABLE,
        ReasonCode.SNAPSHOT_EXPIRED,
        ReasonCode.AUDIT_COMMIT_FAILED,
        ReasonCode.AUDIT_VERIFICATION_UNKNOWN,
        ReasonCode.INTERNAL_ERROR,
        ReasonCode.DEADLINE_EXCEEDED,
        ReasonCode.CANCELLED,
    }
)

AUDIT_GAP_REASON_CODES: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.AUDIT_GAP,
        ReasonCode.AUDIT_COMMIT_FAILED,
        ReasonCode.AUDIT_VERIFICATION_UNKNOWN,
        ReasonCode.SOURCE_UNVERIFIED,
        ReasonCode.REVISION_CONFLICT,
        ReasonCode.REVISION_UNAVAILABLE,
        ReasonCode.SNAPSHOT_EXPIRED,
        ReasonCode.INTERNAL_ERROR,
        ReasonCode.DEADLINE_EXCEEDED,
    }
)


class PocState(StrEnum):
    """Whether S1 can safely document the original request sequence."""

    DOCUMENTED = "documented"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"


class PocReplayStatus(StrEnum):
    """S1 reports never run the request sequence again."""

    NOT_RUN = "not_run"


class PocAction(StrEnum):
    """Fixed, non-executable presentation actions for the S1 GET comparison."""

    VERIFY_OWNER = "verify_owner"
    VERIFY_EVALUATED = "verify_evaluated"
    READ_OWNER = "read_owner"
    READ_CROSS = "read_cross"


@dataclass(frozen=True, slots=True)
class AuditExpectation(ContractRecord):
    """Host-owned cutoff expectations; unknown terminal sequence is never zero.

    Provider registry completeness, source sealing, snapshot validity and event
    content are verified by the Report service, not by this value object.
    """

    producer: Ref
    first_sequence: int
    last_sequence: int | None
    expected_event_refs: tuple[Ref, ...]
    request_refs: tuple[Ref, ...]
    attempt_refs: tuple[Ref, ...]

    def _validate_invariants(self) -> None:
        if self.first_sequence != 1 or type(self.first_sequence) is not int:
            raise ValueError("audit expectations start at sequence one")
        if self.last_sequence is not None and (
            type(self.last_sequence) is not int or self.last_sequence < 0
        ):
            raise ValueError("terminal sequence must be non-negative or unknown")
        if self.last_sequence == 0 and (
            self.expected_event_refs or self.request_refs or self.attempt_refs
        ):
            raise ValueError("sealed empty journal cannot have expected refs")
        for refs in (self.expected_event_refs, self.request_refs, self.attempt_refs):
            if len(refs) != len(set(refs)):
                raise ValueError("duplicate expected audit reference")


@dataclass(frozen=True, slots=True)
class AuditGap(ContractRecord):
    """One unresolved producer audit requirement, even without a readable event."""

    producer: Ref
    request_ref: Ref | None
    attempt_ref: Ref | None
    event_ref: Ref | None
    reason_code: ReasonCode

    def _validate_invariants(self) -> None:
        if self.reason_code not in AUDIT_GAP_REASON_CODES:
            raise ValueError("audit gap requires an audit/source uncertainty reason")


@dataclass(frozen=True, slots=True)
class CaseLimit(ContractRecord):
    """Preserve pre-verdict partial and failed case evidence without inventing verdicts."""

    case_ref: Ref
    status: ResultStatus
    stored_evidence_refs: tuple[Ref, ...]
    comparison_ref: Ref | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if len(set(self.stored_evidence_refs)) != len(self.stored_evidence_refs):
            raise ValueError("duplicate case Evidence reference")
        if self.status is not ResultStatus.COMPLETE and not self.reason_codes:
            raise ValueError("incomplete case requires reasons")


@dataclass(frozen=True, slots=True)
class PocStep(ContractRecord):
    """One non-executable action linked to stored identity or request Evidence."""

    sequence: int
    action: PocAction
    account_ref: Ref
    identity_ref: Ref | None
    request_recipe: RegisteredRequestRecipe | None
    evidence_ref: Ref | None

    def _validate_invariants(self) -> None:
        require_positive("sequence", self.sequence)
        if self.action in (PocAction.VERIFY_OWNER, PocAction.VERIFY_EVALUATED):
            if self.request_recipe is not None:
                raise ValueError("identity steps cannot carry object GET recipes")


@dataclass(frozen=True, slots=True)
class PocReport(ContractRecord):
    """S1 evidence-backed instructions, explicitly NOT a replay result.

    DOCUMENTED validates the local structure of four steps. The Report service
    must still verify committed identity/evidence/recipe provenance, policy,
    comparison and audit before using that label.
    """

    case_ref: Ref
    verdict_ref: Ref
    state: PocState
    replay_status: PocReplayStatus
    comparison_ref: Ref | None
    steps: tuple[PocStep, ...]
    evidence_refs: tuple[Ref, ...]
    audit_links: tuple[AuditLink, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.replay_status is not PocReplayStatus.NOT_RUN:
            raise ValueError("S1 PoC replay status must remain not_run")
        if len({step.sequence for step in self.steps}) != len(self.steps):
            raise ValueError("duplicate PoC step number")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("duplicate PoC Evidence reference")
        if self.state is not PocState.DOCUMENTED:
            if not self.reason_codes:
                raise ValueError("incomplete/unavailable PoC requires reasons")
            if self.state is PocState.UNAVAILABLE and not any(
                reason in (ReasonCode.RECIPE_UNSUPPORTED, ReasonCode.RECIPE_NOT_EXPORTABLE)
                for reason in self.reason_codes
            ):
                raise ValueError("unavailable PoC must identify recipe support/export limits")
            return
        if self.comparison_ref is None or not self.audit_links:
            raise ValueError("documented PoC requires comparison and audit links")
        actions = (
            PocAction.VERIFY_OWNER,
            PocAction.VERIFY_EVALUATED,
            PocAction.READ_OWNER,
            PocAction.READ_CROSS,
        )
        if tuple(step.action for step in self.steps) != actions or tuple(
            step.sequence for step in self.steps
        ) != (1, 2, 3, 4):
            raise ValueError("documented PoC requires the ordered four-step S1 sequence")
        owner_id, evaluated_id, owner_read, cross_read = self.steps
        if owner_id.account_ref == evaluated_id.account_ref:
            raise ValueError("documented PoC requires distinct account references")
        if owner_read.account_ref != owner_id.account_ref or (
            cross_read.account_ref != evaluated_id.account_ref
        ):
            raise ValueError("PoC identity and read account mismatch")
        if (
            owner_id.identity_ref is None
            or evaluated_id.identity_ref is None
            or owner_id.identity_ref == evaluated_id.identity_ref
        ):
            raise ValueError("documented PoC requires distinct identity references")
        if any(step.evidence_ref is None for step in self.steps):
            raise ValueError("documented PoC requires each step's stored Evidence")
        if any(step.evidence_ref not in self.evidence_refs for step in self.steps):
            raise ValueError("PoC step Evidence must be listed in the report")
        if owner_read.evidence_ref == cross_read.evidence_ref:
            raise ValueError("owner and cross reads require distinct Evidence")
        if owner_read.request_recipe is None or cross_read.request_recipe is None:
            raise ValueError("documented reads require registered request recipes")
        owner_recipe = owner_read.request_recipe
        cross_recipe = cross_read.request_recipe
        if (
            owner_recipe.operation_ref != cross_recipe.operation_ref
            or owner_recipe.resource_ref != cross_recipe.resource_ref
            or owner_recipe.resource_binding_ref != cross_recipe.resource_binding_ref
            or owner_recipe.resource_binding_revision != cross_recipe.resource_binding_revision
        ):
            raise ValueError("owner and cross recipes must target the same registered object")


@dataclass(frozen=True, slots=True)
class ReportInput(ContractRecord):
    """Host diagnostic-cutoff snapshot for read-only report construction.

    Tasks are their last committed *diagnostic* revisions, not later operations
    revisions. Report task lifecycle and post-cutoff changes are excluded.
    ReadContext is only a caller reference; authorization must be rechecked.
    """

    run_key: RunKey
    context: ReadContext
    tasks: tuple[TaskSummary, ...]
    observations: tuple[Observation, ...]
    comparisons: tuple[AccessCompareResult, ...]
    verdicts: tuple[Verdict, ...]
    audit_expectations: tuple[AuditExpectation, ...]

    def _validate_invariants(self) -> None:
        if any(task.kind is TaskKind.REPORT for task in self.tasks):
            raise ValueError("diagnostic cutoff must not include the Report task")
        if len({task.task_ref for task in self.tasks}) != len(self.tasks):
            raise ValueError("duplicate Report input task")
        if any(
            attempt.run_key != self.run_key
            for task in self.tasks
            for attempt in task.attempt_summaries
        ):
            raise ValueError("report input task attempt run mismatch")
        if any(item.run_key != self.run_key for item in self.observations):
            raise ValueError("Report observation run mismatch")
        if any(item.run_key != self.run_key for item in self.comparisons):
            raise ValueError("Report comparison run mismatch")
        if any(item.run_key != self.run_key for item in self.verdicts):
            raise ValueError("Report verdict run mismatch")
        for refs in (
            tuple(item.observation_ref for item in self.observations),
            tuple(item.case_ref for item in self.comparisons),
            tuple(item.verdict_ref for item in self.verdicts),
            tuple(item.producer for item in self.audit_expectations),
        ):
            if len(refs) != len(set(refs)):
                raise ValueError("duplicate report source reference")


@dataclass(frozen=True, slots=True)
class DiagnosisReport(ContractRecord):
    """Immutable redacted results and limitation references, not raw HTTP data."""

    run_key: RunKey
    report_ref: Ref
    verdicts: tuple[Verdict, ...]
    send_counts: SendCounts
    incomplete_task_refs: tuple[Ref, ...]
    audit_completeness: AuditCompleteness
    audit_gaps: tuple[AuditGap, ...]
    evidence_refs: tuple[Ref, ...]
    comparison_refs: tuple[Ref, ...]
    comparison_limits: tuple[CaseLimit, ...]
    pocs: tuple[PocReport, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if any(verdict.run_key != self.run_key for verdict in self.verdicts):
            raise ValueError("report verdict run mismatch")
        if len({verdict.verdict_ref for verdict in self.verdicts}) != len(self.verdicts):
            raise ValueError("duplicate report verdict")
        for refs in (self.incomplete_task_refs, self.evidence_refs, self.comparison_refs):
            if len(refs) != len(set(refs)):
                raise ValueError("duplicate report reference")
        if self.audit_completeness is AuditCompleteness.COMPLETE and self.audit_gaps:
            raise ValueError("complete diagnostic audit cannot contain gaps")
        if self.audit_completeness is AuditCompleteness.UNKNOWN and not self.audit_gaps:
            raise ValueError("unknown diagnostic audit must preserve a producer gap")
        if len({limit.case_ref for limit in self.comparison_limits}) != len(self.comparison_limits):
            raise ValueError("duplicate case limitation")
        if len({poc.verdict_ref for poc in self.pocs}) != len(self.pocs):
            raise ValueError("duplicate PoC verdict reference")
        by_verdict = {verdict.verdict_ref: verdict for verdict in self.verdicts}
        if len(self.pocs) != len(self.verdicts):
            raise ValueError("every verdict requires exactly one PoC state")
        for poc in self.pocs:
            verdict = by_verdict.get(poc.verdict_ref)
            if verdict is None or verdict.case_ref != poc.case_ref:
                raise ValueError("PoC and stored Verdict identity mismatch")
            if poc.state is PocState.DOCUMENTED:
                if verdict.value is not VerdictValue.CONFIRMED:
                    raise ValueError("unconfirmed verdict cannot publish documented PoC")
                if poc.comparison_ref != verdict.comparison_ref:
                    raise ValueError("documented PoC comparison must match Verdict")


@dataclass(frozen=True, slots=True)
class ReportResult(ContractRecord):
    """A persisted report or an explicit failure; partial never drops the report.

    The producer must authorize current access and verify all referenced producer
    records, journal expectations and report artifact commit. A report_ref in a
    dataclass does not attest that these IO checks happened.
    """

    run_key: RunKey
    status: ResultStatus
    report: DiagnosisReport | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.FAILED:
            if self.report is not None or not self.reason_codes:
                raise ValueError("failed report cannot return a report artifact")
            if any(reason not in REPORT_FAILURE_REASON_CODES for reason in self.reason_codes):
                raise ValueError("failed Report call requires failure-class reasons")
            return
        if self.report is None or self.report.run_key != self.run_key:
            raise ValueError("complete/partial result requires same-run report")
        if self.status is ResultStatus.PARTIAL and not self.reason_codes:
            raise ValueError("partial Report result requires reasons")
        if self.status is ResultStatus.COMPLETE:
            if self.reason_codes:
                raise ValueError("complete Report result cannot have partial/failure reasons")
            if (
                self.report.audit_completeness is AuditCompleteness.UNKNOWN
                or self.report.incomplete_task_refs
            ):
                raise ValueError("incomplete diagnostic coverage requires partial Report result")
            verdicts_by_ref = {item.verdict_ref: item for item in self.report.verdicts}
            if any(
                verdicts_by_ref[poc.verdict_ref].value is VerdictValue.CONFIRMED
                and poc.state is not PocState.DOCUMENTED
                for poc in self.report.pocs
            ):
                raise ValueError("confirmed verdict with unfinished PoC requires partial result")


class ReportPort(Protocol):
    """Build from authorized persisted evidence without any target transport.

    Re-authorize each call; verify producer audit sequences, signed bindings and
    immutable evidence/recipes. Host run/task receipt checks attest to the Host
    producer: public TaskSummary alone cannot recompute task.v1 fingerprints.
    Never synthesize a missing request, verdict, policy or PoC step. Return
    PARTIAL with a committed report if diagnostic audit or confirmed PoC is
    incomplete. Propagate cancellation; publish no uncommitted report_ref.
    """

    async def build_report(self, request: ReportInput) -> ReportResult:
        """Read, verify, render and commit a report; never execute requests."""
        ...
