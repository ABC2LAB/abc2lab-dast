"""Host/Knowledge contract example for one explicitly linked observation fixture.

This scripted memory example is not Knowledge's candidate merge/query algorithm,
a durable journal, an authorization system, or a transport implementation.
"""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from abc2lab_contracts.audit import (
    AuditEventKind,
    AuditReceipt,
    AuditRecordBinding,
    AuditVerifyRequest,
    AuditVerifyResult,
    VerificationState,
)
from abc2lab_contracts.evidence import (
    EvidenceReadRequest,
    EvidenceReadResult,
    EvidenceSummary,
    RedactedBundle,
    StoreOutcome,
)
from abc2lab_contracts.fingerprint import observation_fingerprint
from abc2lab_contracts.knowledge import (
    Candidate,
    CandidateAck,
    CandidateHint,
    CandidateSubmission,
    CaseReadRequest,
    CaseReadResult,
    DiscoveryKind,
    ProjectionAck,
    ProjectionDisposition,
    ProjectionSubmission,
)
from abc2lab_contracts.observation import Observation
from abc2lab_contracts.ports import AuditVerifier, EvidencePort, KnowledgePort
from abc2lab_contracts.primitives import (
    AuditLink,
    ReadContext,
    ReasonCode,
    ResponseClass,
    ResultStatus,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.projection import ObservationProjected

STAMP = datetime(2026, 10, 21, tzinfo=UTC)
RUN = RunKey("org", "target", "environment", "run")
CONTEXT = ReadContext("host", "registered-host-reader")
SOURCE = SourceVersion("app", "registered-seed", 1)


def _observation() -> Observation:
    return Observation(
        RUN,
        "observation",
        "candidate",
        "resource",
        "operation",
        "account",
        1,
        "identity",
        ResponseClass.NORMAL,
        "evidence",
        AuditLink("webdiag", "event"),
        STAMP,
        (),
    )


def _event(observation: Observation) -> ObservationProjected:
    binding = _binding(observation)
    receipt = AuditReceipt(RUN, "webdiag", "event", 7, binding, STAMP)
    return ObservationProjected(
        AuditEventKind.OBSERVATION, "event", RUN, "webdiag", 1, receipt, observation
    )


def _binding(observation: Observation) -> AuditRecordBinding:
    # Derive expected content from business fields, never copy receipt.binding.
    return AuditRecordBinding(
        AuditEventKind.OBSERVATION,
        observation.observation_ref,
        1,
        observation_fingerprint(observation),
        None,
        None,
        None,
    )


class _ProducerJournal:
    def __init__(self, committed: AuditReceipt) -> None:
        self.committed = committed
        self.state = VerificationState.VERIFIED
        self.is_cancelled = False

    async def verify_committed(self, request: AuditVerifyRequest) -> AuditVerifyResult:
        if self.is_cancelled:
            import asyncio

            raise asyncio.CancelledError
        state = self.state
        if state is VerificationState.VERIFIED and (
            request.run_key != self.committed.run_key
            or request.receipt != self.committed
            or request.expected != self.committed.binding
        ):
            state = VerificationState.INVALID
        reasons = {
            VerificationState.VERIFIED: (),
            VerificationState.UNKNOWN: (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,),
            VerificationState.INVALID: (ReasonCode.SOURCE_UNVERIFIED,),
        }
        return AuditVerifyResult(request.run_key, state, reasons[state])


class _EvidenceReader:
    def __init__(self) -> None:
        self.is_available = True
        self.read_count = 0
        self.evidence = EvidenceSummary(
            RUN,
            "evidence",
            "attempt",
            "operation",
            "resource",
            "account",
            1,
            "identity",
            ResponseClass.NORMAL,
            200,
            STAMP,
            SOURCE,
            AuditLink("evidence", "evidence-event"),
            None,
            (ReasonCode.RECIPE_UNSUPPORTED,),
        )

    async def store_evidence(self, request: RedactedBundle) -> StoreOutcome:
        raise AssertionError("Knowledge does not write Evidence in this example")

    async def evidence_read_summary(self, request: EvidenceReadRequest) -> EvidenceReadResult:
        self.read_count += 1
        if request.run_key != RUN or request.context != CONTEXT:
            return EvidenceReadResult(
                request.run_key, ResultStatus.FAILED, (), (), (ReasonCode.ACCESS_DENIED,)
            )
        if not self.is_available or request.evidence_refs != (self.evidence.evidence_ref,):
            return EvidenceReadResult(RUN, ResultStatus.FAILED, (), (), (ReasonCode.NOT_FOUND,))
        return EvidenceReadResult(RUN, ResultStatus.COMPLETE, (self.evidence,), (), ())


class _KnowledgeExample:
    """Only replay one registered hint and its explicitly linked Observation."""

    def __init__(self, verifier: AuditVerifier, evidence: EvidencePort) -> None:
        self.verifier = verifier
        self.evidence = evidence
        self.revision = 1
        self.hint = CandidateHint(
            "operation", "resource", DiscoveryKind.REGISTERED_SEED, SOURCE, (), ()
        )
        self.candidates: tuple[Candidate, ...] = ()
        self.submissions: dict[str, tuple[CandidateSubmission, CandidateAck]] = {}
        self.applied: tuple[ObservationProjected, int] | None = None

    async def register_candidates(self, request: CandidateSubmission) -> CandidateAck:
        if request.run_key != RUN:
            return CandidateAck(
                request.run_key, ResultStatus.FAILED, (), None, (ReasonCode.ACCESS_DENIED,)
            )
        prior = self.submissions.get(request.submission_ref)
        if prior is not None:
            if request == prior[0]:
                return prior[1]
            return CandidateAck(
                RUN, ResultStatus.FAILED, (), None, (ReasonCode.IDEMPOTENCY_CONFLICT,)
            )
        if request.hints != (self.hint,):
            return CandidateAck(RUN, ResultStatus.FAILED, (), None, (ReasonCode.SOURCE_UNVERIFIED,))
        if not self.candidates:
            self.candidates = (
                Candidate(RUN, "candidate", 1, "operation", "resource", SOURCE, (), ()),
            )
            self.revision += 1
        result = CandidateAck(RUN, ResultStatus.COMPLETE, self.candidates, self.revision, ())
        self.submissions[request.submission_ref] = (request, result)
        return result

    async def project(self, request: ProjectionSubmission) -> ProjectionAck:
        event = request.source_event
        if (
            request.run_key != RUN
            or type(event) is not ObservationProjected
            or event.producer != "webdiag"
        ):
            return self._not_applied(request.run_key, ReasonCode.SOURCE_UNVERIFIED)
        if self.applied is not None:
            if event == self.applied[0]:
                return ProjectionAck(
                    RUN, ResultStatus.COMPLETE, ProjectionDisposition.DUPLICATE, self.applied[1], ()
                )
            return self._not_applied(RUN, ReasonCode.IDEMPOTENCY_CONFLICT)
        checked = await self.verifier.verify_committed(
            AuditVerifyRequest(RUN, event.source_receipt, _binding(event.observation))
        )
        if checked.state is not VerificationState.VERIFIED:
            return self._not_applied(
                RUN, checked.reason_codes[0], checked.state is VerificationState.UNKNOWN
            )
        observed = event.observation
        if not self.candidates or observed.candidate_ref != self.candidates[0].candidate_ref:
            return self._not_applied(RUN, ReasonCode.NOT_FOUND)
        summary = await self.evidence.evidence_read_summary(
            EvidenceReadRequest(RUN, CONTEXT, (observed.evidence_ref,), ())
        )
        if summary.status is not ResultStatus.COMPLETE or len(summary.evidence) != 1:
            return self._not_applied(RUN, ReasonCode.NOT_FOUND)
        evidence = summary.evidence[0]
        if (
            evidence.operation_ref,
            evidence.resource_ref,
            evidence.account_ref,
            evidence.identity_ref,
        ) != (
            observed.operation_ref,
            observed.resource_ref,
            observed.account_ref,
            observed.identity_ref,
        ):
            return self._not_applied(RUN, ReasonCode.CAPTURE_BINDING_MISMATCH)
        self.revision += 1
        self.applied = (event, self.revision)
        return ProjectionAck(
            RUN, ResultStatus.COMPLETE, ProjectionDisposition.APPLIED, self.revision, ()
        )

    async def get_case_view(self, request: CaseReadRequest) -> CaseReadResult:
        if request.run_key != RUN or request.context != CONTEXT:
            return self._failed_read(request.run_key, ReasonCode.ACCESS_DENIED)
        if request.at_revision is not None and request.at_revision != self.revision:
            return self._failed_read(RUN, ReasonCode.REVISION_UNAVAILABLE)
        if request.candidate_refs != ("candidate",) or not self.candidates:
            return self._failed_read(RUN, ReasonCode.NOT_FOUND)
        # The fixture explicitly links this one event to this candidate; no graph inference.
        events = () if self.applied is None else (self.applied[0],)
        remaining = max(0, request.limit - len(self.candidates))
        truncated = len(self.candidates) + len(events) > request.limit
        return CaseReadResult(
            RUN,
            ResultStatus.PARTIAL if truncated else ResultStatus.COMPLETE,
            self.candidates[: request.limit],
            events[:remaining],
            self.revision,
            truncated,
            (ReasonCode.RESULT_LIMIT_EXCEEDED,) if truncated else (),
        )

    @staticmethod
    def _not_applied(run_key: RunKey, reason: ReasonCode, deferred: bool = False) -> ProjectionAck:
        return ProjectionAck(
            run_key,
            ResultStatus.PARTIAL if deferred else ResultStatus.FAILED,
            ProjectionDisposition.DEFERRED if deferred else ProjectionDisposition.REJECTED,
            None,
            (reason,),
        )

    @staticmethod
    def _failed_read(run_key: RunKey, reason: ReasonCode) -> CaseReadResult:
        return CaseReadResult(run_key, ResultStatus.FAILED, (), (), None, False, (reason,))


@pytest.fixture
def example() -> tuple[_KnowledgeExample, _ProducerJournal, _EvidenceReader]:
    journal = _ProducerJournal(_event(_observation()).source_receipt)
    evidence = _EvidenceReader()
    return _KnowledgeExample(journal, evidence), journal, evidence


async def _register(port: KnowledgePort) -> CandidateAck:
    hint = CandidateHint("operation", "resource", DiscoveryKind.REGISTERED_SEED, SOURCE, (), ())
    return await port.register_candidates(CandidateSubmission(RUN, "submission", (hint,)))


@pytest.mark.asyncio
async def test_host_registers_reads_projects_and_reads_original_event(
    example: tuple[_KnowledgeExample, _ProducerJournal, _EvidenceReader],
) -> None:
    knowledge, _, evidence = example
    port: KnowledgePort = knowledge
    accepted = await _register(port)
    selected = await port.get_case_view(
        CaseReadRequest(RUN, CONTEXT, ("candidate",), accepted.knowledge_revision, 100)
    )
    assert selected.candidates == accepted.candidates
    assert selected.candidates[0].revision == 1
    event = _event(_observation())
    applied = await port.project(ProjectionSubmission(RUN, event))
    view = await port.get_case_view(
        CaseReadRequest(RUN, CONTEXT, ("candidate",), applied.knowledge_revision, 100)
    )
    assert applied.disposition is ProjectionDisposition.APPLIED
    assert view.events[0] is event
    assert view.events[0].producer == "webdiag"
    assert evidence.read_count == 1


@pytest.mark.asyncio
async def test_candidate_submission_retry_preserves_ids_and_rejects_conflicts(
    example: tuple[_KnowledgeExample, _ProducerJournal, _EvidenceReader],
) -> None:
    knowledge, _, _ = example
    first = await _register(knowledge)
    assert await _register(knowledge) is first
    conflict = await knowledge.register_candidates(CandidateSubmission(RUN, "submission", ()))
    assert conflict.reason_codes == (ReasonCode.IDEMPOTENCY_CONFLICT,)
    assert knowledge.candidates == first.candidates
    assert knowledge.revision == first.knowledge_revision


@pytest.mark.asyncio
async def test_unknown_projection_is_deferred_then_same_event_applies_once(
    example: tuple[_KnowledgeExample, _ProducerJournal, _EvidenceReader],
) -> None:
    knowledge, journal, _ = example
    await _register(knowledge)
    request = ProjectionSubmission(RUN, _event(_observation()))
    before = knowledge.revision
    journal.state = VerificationState.UNKNOWN
    deferred = await knowledge.project(request)
    assert deferred.disposition is ProjectionDisposition.DEFERRED
    assert deferred.knowledge_revision is None and knowledge.revision == before
    assert knowledge.applied is None
    journal.state = VerificationState.VERIFIED
    applied = await knowledge.project(request)
    duplicate = await knowledge.project(request)
    assert duplicate.disposition is ProjectionDisposition.DUPLICATE
    assert duplicate.knowledge_revision == applied.knowledge_revision == knowledge.revision


@pytest.mark.asyncio
async def test_shape_valid_forgery_is_rejected_by_actual_producer_lookup(
    example: tuple[_KnowledgeExample, _ProducerJournal, _EvidenceReader],
) -> None:
    knowledge, _, evidence = example
    await _register(knowledge)
    # Both business payload and receipt digest are forged consistently; constructor accepts them.
    forged = _event(replace(_observation(), evidence_ref="uncommitted-evidence"))
    result = await knowledge.project(ProjectionSubmission(RUN, forged))
    assert result.disposition is ProjectionDisposition.REJECTED
    assert result.reason_codes == (ReasonCode.SOURCE_UNVERIFIED,)
    assert knowledge.applied is None and evidence.read_count == 0


@pytest.mark.asyncio
async def test_missing_evidence_prevents_graph_application(
    example: tuple[_KnowledgeExample, _ProducerJournal, _EvidenceReader],
) -> None:
    knowledge, _, evidence = example
    await _register(knowledge)
    evidence.is_available = False
    revision = knowledge.revision
    result = await knowledge.project(ProjectionSubmission(RUN, _event(_observation())))
    assert result.disposition is ProjectionDisposition.REJECTED
    assert knowledge.applied is None and knowledge.revision == revision


@pytest.mark.asyncio
async def test_stale_and_denied_reads_do_not_return_current_snapshot_or_data(
    example: tuple[_KnowledgeExample, _ProducerJournal, _EvidenceReader],
) -> None:
    knowledge, _, _ = example
    before = await _register(knowledge)
    await knowledge.project(ProjectionSubmission(RUN, _event(_observation())))
    stale = await knowledge.get_case_view(
        CaseReadRequest(RUN, CONTEXT, ("candidate",), before.knowledge_revision, 100)
    )
    assert stale.reason_codes == (ReasonCode.REVISION_UNAVAILABLE,)
    denied = await knowledge.get_case_view(
        CaseReadRequest(RUN, ReadContext("other", "untrusted"), ("candidate",), None, 100)
    )
    assert denied.reason_codes == (ReasonCode.ACCESS_DENIED,)
    for result in (stale, denied):
        assert not result.candidates and not result.events and result.knowledge_revision is None
    limited = await knowledge.get_case_view(CaseReadRequest(RUN, CONTEXT, ("candidate",), None, 1))
    assert limited.status is ResultStatus.PARTIAL and limited.truncated
    assert len(limited.candidates) + len(limited.events) == 1
    assert limited.reason_codes == (ReasonCode.RESULT_LIMIT_EXCEEDED,)


@pytest.mark.asyncio
async def test_cancelled_verification_propagates_without_graph_mutation(
    example: tuple[_KnowledgeExample, _ProducerJournal, _EvidenceReader],
) -> None:
    import asyncio

    knowledge, journal, _ = example
    await _register(knowledge)
    journal.is_cancelled = True
    revision = knowledge.revision
    with pytest.raises(asyncio.CancelledError):
        await knowledge.project(ProjectionSubmission(RUN, _event(_observation())))
    assert knowledge.applied is None and knowledge.revision == revision
