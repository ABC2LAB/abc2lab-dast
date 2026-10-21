"""Focused runtime checks for the C2 execution contract."""

from dataclasses import replace

import pytest
from abc2lab_contracts.audit import PolicyOutcome
from abc2lab_contracts.execution import (
    AttemptResult,
    ExecuteRequest,
    ExecutionRequest,
    PolicyDecision,
    PolicyDecisionContent,
    PolicyDecisionResult,
    PolicyInput,
    PrepareResult,
)
from abc2lab_contracts.primitives import CaptureStatus, ResultStatus, SendStatus


def test_policy_input_rejects_wire_version_relabeling(policy_input: PolicyInput) -> None:
    with pytest.raises(ValueError, match="schema version"):
        replace(policy_input, schema_version="policy_input.v2")


def test_policy_decision_content_has_explicit_validity_interval(
    decision_content: PolicyDecisionContent,
) -> None:
    assert decision_content.outcome in (PolicyOutcome.ALLOW, PolicyOutcome.BLOCK)
    with pytest.raises(ValueError, match="validity interval"):
        replace(decision_content, expires_at=decision_content.issued_at)


def test_final_policy_decision_requires_audit_receipt(
    decision_content: PolicyDecisionContent,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        PolicyDecision.from_content(decision_content, None)  # type: ignore[arg-type]


def test_content_type_cannot_be_used_as_final_execute_decision(
    decision_content: PolicyDecisionContent,
) -> None:
    with pytest.raises(TypeError):
        ExecuteRequest(
            decision_content.run_key,
            "request-1",
            "prepared-1",
            decision_content,  # type: ignore[arg-type]
        )


def test_policy_result_requires_matching_complete_output(decision: PolicyDecision) -> None:
    run_key = decision.run_key
    with pytest.raises(ValueError, match="status/output"):
        PolicyDecisionResult(run_key, ResultStatus.COMPLETE, None, ())
    with pytest.raises(ValueError, match="status/output"):
        PolicyDecisionResult(run_key, ResultStatus.FAILED, decision, ())


def test_prepare_result_requires_handle_and_policy_view_pair(policy_input: PolicyInput) -> None:
    run_key = policy_input.run_key
    with pytest.raises(ValueError, match="status/output"):
        PrepareResult(run_key, ResultStatus.COMPLETE, "prepared-1", None, ())
    with pytest.raises(ValueError, match="status/output"):
        PrepareResult(run_key, ResultStatus.FAILED, "prepared-1", policy_input, ())


@pytest.mark.parametrize(
    ("send_status", "capture_status", "capture_ref"),
    [
        (SendStatus.SENT, CaptureStatus.CAPTURED, "capture-1"),
        (SendStatus.SENT, CaptureStatus.UNAVAILABLE, None),
        (SendStatus.NOT_SENT, CaptureStatus.NOT_APPLICABLE, None),
        (SendStatus.UNKNOWN, CaptureStatus.INDETERMINATE, None),
    ],
)
def test_attempt_result_preserves_all_documented_pairs(
    execution_request: ExecutionRequest,
    send_status: SendStatus,
    capture_status: CaptureStatus,
    capture_ref: str | None,
) -> None:
    result = replace(
        AttemptResult(
            execution_request.run_key,
            execution_request.request_ref,
            "attempt-1",
            None,
            None,
            send_status,
            capture_status,
            capture_ref,
            None,
            (),
            (),
        ),
        send_status=send_status,
        capture_status=capture_status,
        capture_ref=capture_ref,
    )
    assert result.send_status is send_status


def test_attempt_result_rejects_capture_reference_for_unavailable_capture(
    execution_request: ExecutionRequest,
) -> None:
    attempt_result = AttemptResult(
        execution_request.run_key,
        execution_request.request_ref,
        "attempt-1",
        None,
        None,
        SendStatus.SENT,
        CaptureStatus.UNAVAILABLE,
        None,
        None,
        (),
        (),
    )
    with pytest.raises(ValueError, match="capture reference"):
        replace(
            attempt_result,
            send_status=SendStatus.SENT,
            capture_status=CaptureStatus.UNAVAILABLE,
            capture_ref="capture-1",
        )
