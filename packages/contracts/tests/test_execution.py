"""Exercise all send/capture combinations, including partial and indeterminate states."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from itertools import product

import abc2lab_contracts
import pytest
from abc2lab_contracts import (
    PolicyDecision,
    PolicyDecisionRef,
    PolicyOutcome,
    ReasonCode,
    RequestAttemptRef,
    RequestBindingError,
    RequestPlan,
    RunRef,
)
from abc2lab_contracts.execution import (
    CaptureAvailability,
    CapturedObservation,
    CaptureRef,
    SendStatus,
)


@pytest.fixture
def observation(plan: RequestPlan) -> CapturedObservation:
    """Create a known send whose capture was persisted in execution storage."""
    return CapturedObservation(
        attempt_ref=RequestAttemptRef(value="attempt-1"),
        binding=plan.binding,
        decision=PolicyDecision(
            decision_ref=PolicyDecisionRef(value="decision-1"),
            binding=plan.binding,
            outcome=PolicyOutcome.ALLOW,
            reason_code=ReasonCode(value="fixture_allow"),
        ),
        observed_at=datetime(2026, 10, 20, tzinfo=UTC),
        send_status=SendStatus.SENT,
        capture_availability=CaptureAvailability.CAPTURED,
        capture_ref=CaptureRef(value="private-capture-handle"),
        reason_code=ReasonCode(value="capture_stored"),
    )


@pytest.mark.parametrize(
    ("outcome", "send_status", "availability", "has_capture"),
    list(product(PolicyOutcome, SendStatus, CaptureAvailability, (False, True))),
)
def test_send_capture_state_matrix(
    observation: CapturedObservation,
    outcome: PolicyOutcome,
    send_status: SendStatus,
    availability: CaptureAvailability,
    has_capture: bool,
) -> None:
    is_valid = (
        send_status is SendStatus.NOT_SENT
        and availability is CaptureAvailability.NOT_APPLICABLE
        and not has_capture
    ) or (
        outcome is PolicyOutcome.ALLOW
        and (
            (
                send_status is SendStatus.UNKNOWN
                and availability is CaptureAvailability.INDETERMINATE
                and not has_capture
            )
            or (
                send_status is SendStatus.SENT
                and availability is CaptureAvailability.CAPTURED
                and has_capture
            )
            or (
                send_status is SendStatus.SENT
                and availability is CaptureAvailability.UNAVAILABLE
                and not has_capture
            )
        )
    )
    capture_ref = observation.capture_ref if has_capture else None
    decision = replace(observation.decision, outcome=outcome)
    if is_valid:
        result = replace(
            observation,
            decision=decision,
            send_status=send_status,
            capture_availability=availability,
            capture_ref=capture_ref,
        )
        assert result.send_status is send_status
    else:
        with pytest.raises(ValueError):
            replace(
                observation,
                decision=decision,
                send_status=send_status,
                capture_availability=availability,
                capture_ref=capture_ref,
            )


def test_capture_failure_preserves_known_send(observation: CapturedObservation) -> None:
    partial = replace(
        observation,
        capture_availability=CaptureAvailability.UNAVAILABLE,
        capture_ref=None,
        reason_code=ReasonCode(value="capture_storage_failed"),
    )
    assert partial.send_status is SendStatus.SENT
    assert partial.capture_ref is None
    assert partial.capture_availability is not CaptureAvailability.CAPTURED


def test_observation_rejects_different_decision_binding(observation: CapturedObservation) -> None:
    context = replace(observation.binding.context, run_ref=RunRef(value="another-run"))
    with pytest.raises(RequestBindingError):
        replace(observation, binding=replace(observation.binding, context=context))


@pytest.mark.parametrize(
    "observed_at",
    [datetime(2026, 10, 20), datetime(2026, 10, 20, tzinfo=timezone(timedelta(hours=9)))],
)
def test_audit_time_requires_explicit_utc(
    observation: CapturedObservation,
    observed_at: datetime,
) -> None:
    with pytest.raises(ValueError, match="observed_at must be timezone-aware UTC"):
        replace(observation, observed_at=observed_at)


def test_capture_handle_is_hidden_from_repr(observation: CapturedObservation) -> None:
    assert observation.capture_ref is not None
    assert "private-capture-handle" not in repr(observation)
    assert "private-capture-handle" not in repr(observation.capture_ref)


def test_execution_contracts_are_not_root_exports() -> None:
    for name in ("CaptureRef", "CapturedObservation", "GatewayPort"):
        assert name not in abc2lab_contracts.__all__
        assert not hasattr(abc2lab_contracts, name)
