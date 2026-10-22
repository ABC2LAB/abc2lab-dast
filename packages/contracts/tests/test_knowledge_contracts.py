"""C4 Knowledge request/result invariants."""

import pytest
from abc2lab_contracts.knowledge import (
    MAX_CASE_READ_LIMIT,
    Candidate,
    CandidateAck,
    CaseReadRequest,
    CaseReadResult,
    ProjectionAck,
    ProjectionDisposition,
    ProjectionSubmission,
)
from abc2lab_contracts.primitives import (
    AuditLink,
    ReadContext,
    ReasonCode,
    ResultStatus,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.projection import ProjectionEvent


def _run() -> RunKey:
    return RunKey("org", "target", "environment", "run")


def _candidate(run_key: RunKey, reference: str = "candidate-1") -> Candidate:
    return Candidate(
        run_key,
        reference,
        2,
        "operation-1",
        "resource-1",
        SourceVersion("registration", "candidate", 2),
        ("evidence-1",),
        (),
    )


def test_candidate_ack_preserves_partial_candidates_and_requires_reason() -> None:
    run_key = _run()
    candidate = _candidate(run_key)
    result = CandidateAck(
        run_key,
        ResultStatus.PARTIAL,
        (candidate,),
        7,
        (ReasonCode.REVISION_CONFLICT,),
    )
    assert result.candidates == (candidate,)
    with pytest.raises(ValueError, match="partial registration requires"):
        CandidateAck(run_key, ResultStatus.PARTIAL, (), 7, (ReasonCode.REVISION_CONFLICT,))
    with pytest.raises(ValueError, match="incomplete candidate registration requires"):
        CandidateAck(run_key, ResultStatus.PARTIAL, (candidate,), 7, ())


def test_candidate_ack_rejects_failed_output_and_cross_run_or_duplicate_candidates() -> None:
    run_key = _run()
    candidate = _candidate(run_key)
    with pytest.raises(ValueError, match="failed candidate registration"):
        CandidateAck(run_key, ResultStatus.FAILED, (candidate,), None, (ReasonCode.INTERNAL_ERROR,))
    with pytest.raises(ValueError, match="duplicate candidate ref"):
        CandidateAck(run_key, ResultStatus.COMPLETE, (candidate, candidate), 7, ())
    with pytest.raises(ValueError, match="candidate run mismatch"):
        CandidateAck(
            run_key,
            ResultStatus.COMPLETE,
            (_candidate(RunKey("org", "target", "environment", "other")),),
            7,
            (),
        )


@pytest.mark.parametrize("limit", [0, MAX_CASE_READ_LIMIT + 1])
def test_case_read_limit_is_bounded_to_one_through_one_hundred(limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 100"):
        CaseReadRequest(_run(), ReadContext("caller", "authorization"), (), None, limit)


@pytest.mark.parametrize("limit", [1, MAX_CASE_READ_LIMIT])
def test_case_read_accepts_bounded_limit_endpoints(limit: int) -> None:
    request = CaseReadRequest(_run(), ReadContext("caller", "authorization"), (), None, limit)
    assert request.limit == limit


def test_knowledge_records_are_frozen_and_closed_typed_tuples() -> None:
    candidate = _candidate(_run())
    with pytest.raises((AttributeError, TypeError)):
        candidate.candidate_ref = "forged"  # type: ignore[misc]
    with pytest.raises(TypeError, match="must be a tuple"):
        Candidate(_run(), "candidate-1", 2, "operation-1", None, SourceVersion("a", "b", 1), [], ())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="incompatible enum"):
        CandidateAck(_run(), "complete", (candidate,), 1, ())  # type: ignore[arg-type]


def test_projection_submission_accepts_only_closed_projection_event() -> None:
    event = _projection_stub(_run(), AuditLink("producer", "event-1"))
    assert ProjectionSubmission(_run(), event).source_event is event
    with pytest.raises(TypeError, match="contract record|incompatible type"):
        ProjectionSubmission(_run(), {})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="contract record|incompatible type"):
        ProjectionSubmission(_run(), "observation")  # type: ignore[arg-type]


def test_case_read_result_rejects_failed_or_truncated_inconsistent_snapshots() -> None:
    run_key = _run()
    candidate = _candidate(run_key)
    with pytest.raises(ValueError, match="failed case read cannot"):
        CaseReadResult(
            run_key, ResultStatus.FAILED, (candidate,), (), None, False, (ReasonCode.NOT_FOUND,)
        )
    with pytest.raises(ValueError, match="truncated case read must be partial"):
        CaseReadResult(run_key, ResultStatus.COMPLETE, (candidate,), (), 3, True, ())
    with pytest.raises(ValueError, match="successful case read requires"):
        CaseReadResult(run_key, ResultStatus.COMPLETE, (), (), None, False, ())


def test_case_read_result_rejects_duplicate_events_and_run_mismatch() -> None:
    run_key = _run()
    event = AuditLink("producer", "event-1")
    projected = _projection_stub(run_key, event)
    with pytest.raises(ValueError, match="duplicate case read event"):
        CaseReadResult(run_key, ResultStatus.COMPLETE, (), (projected, projected), 3, False, ())
    other = _projection_stub(RunKey("org", "target", "environment", "other"), event)
    with pytest.raises(ValueError, match="case read event run mismatch"):
        CaseReadResult(run_key, ResultStatus.COMPLETE, (), (other,), 3, False, ())


def test_projection_ack_maps_disposition_to_status_and_requires_reason_for_noncomplete() -> None:
    run_key = _run()
    assert (
        ProjectionAck(run_key, ResultStatus.COMPLETE, ProjectionDisposition.DUPLICATE, 8, ()).status
        is ResultStatus.COMPLETE
    )
    with pytest.raises(ValueError, match="disposition/status mismatch"):
        ProjectionAck(run_key, ResultStatus.COMPLETE, ProjectionDisposition.DEFERRED, 8, ())
    with pytest.raises(ValueError, match="only applied/duplicate"):
        ProjectionAck(
            run_key,
            ResultStatus.PARTIAL,
            ProjectionDisposition.DEFERRED,
            8,
            (ReasonCode.SOURCE_UNVERIFIED,),
        )
    with pytest.raises(ValueError, match="incomplete projection requires"):
        ProjectionAck(run_key, ResultStatus.FAILED, ProjectionDisposition.REJECTED, None, ())


def _projection_stub(run_key: RunKey, link: AuditLink) -> ProjectionEvent:
    """Return a valid minimal event without importing private implementation details."""
    from datetime import UTC, datetime

    from abc2lab_contracts.audit import AuditEventKind, AuditReceipt, AuditRecordBinding
    from abc2lab_contracts.fingerprint import observation_fingerprint
    from abc2lab_contracts.observation import Observation
    from abc2lab_contracts.primitives import ResponseClass
    from abc2lab_contracts.projection import ObservationProjected

    observation = Observation(
        run_key,
        "observation-1",
        "candidate-1",
        "resource-1",
        "operation-1",
        "account-1",
        1,
        "identity-1",
        ResponseClass.NORMAL,
        "evidence-1",
        link,
        datetime(2026, 10, 21, tzinfo=UTC),
        (),
    )
    binding = AuditRecordBinding(
        AuditEventKind.OBSERVATION,
        observation.observation_ref,
        1,
        observation_fingerprint(observation),
        None,
        None,
        None,
    )
    receipt = AuditReceipt(
        run_key, link.producer, link.event_ref, 5, binding, datetime(2026, 10, 21, tzinfo=UTC)
    )
    return ObservationProjected(
        AuditEventKind.OBSERVATION, link.event_ref, run_key, link.producer, 1, receipt, observation
    )
