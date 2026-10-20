"""Execution-only contracts; never serialize these records to Host, LLM, UI or MCP."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from abc2lab_contracts.control import PolicyDecision, PolicyOutcome, RequestBinding, RequestPlan
from abc2lab_contracts.references import ReasonCode, RequestAttemptRef, _validate_token


class SendStatus(StrEnum):
    """Preserve whether transmission happened, independently of response success."""

    SENT = "sent"
    NOT_SENT = "not_sent"
    UNKNOWN = "unknown"


class CaptureAvailability(StrEnum):
    """Describe capture availability without claiming evidence storage or success."""

    CAPTURED = "captured"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureRef:
    """Identify a run-scoped capture in execution storage; not a public EvidenceRef."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        _validate_token(self.value, "capture reference")


@dataclass(frozen=True, slots=True, kw_only=True)
class CapturedObservation:
    """Bind an attempt's send/capture state to a decision and an explicit UTC audit time."""

    attempt_ref: RequestAttemptRef
    binding: RequestBinding
    decision: PolicyDecision
    observed_at: datetime
    send_status: SendStatus
    capture_availability: CaptureAvailability
    capture_ref: CaptureRef | None = field(repr=False)
    reason_code: ReasonCode

    def __post_init__(self) -> None:
        self.decision.validate_binding(RequestPlan(binding=self.binding))
        if self.observed_at.utcoffset() != timedelta(0):
            raise ValueError("observed_at must be timezone-aware UTC")
        if not isinstance(self.send_status, SendStatus):
            raise ValueError("send_status must be a SendStatus")
        if not isinstance(self.capture_availability, CaptureAvailability):
            raise ValueError("capture_availability must be a CaptureAvailability")
        if (
            self.decision.outcome is PolicyOutcome.BLOCK
            and self.send_status is not SendStatus.NOT_SENT
        ):
            raise ValueError("a blocked decision cannot have sent or unknown transmission")
        if self.send_status is SendStatus.SENT:
            expected = (
                CaptureAvailability.CAPTURED
                if self.capture_ref is not None
                else CaptureAvailability.UNAVAILABLE
            )
        elif self.send_status is SendStatus.NOT_SENT:
            expected = CaptureAvailability.NOT_APPLICABLE
        else:
            expected = CaptureAvailability.INDETERMINATE
        if self.capture_availability is not expected:
            raise ValueError("capture availability is inconsistent with transmission and capture")
        if self.send_status is not SendStatus.SENT and self.capture_ref is not None:
            raise ValueError("only a known sent request can have a capture reference")


class GatewayPort(Protocol):
    """Execute only in the trusted realm after rechecking policy, scope, auth and budget."""

    def execute(self, plan: RequestPlan, decision: PolicyDecision) -> CapturedObservation:
        """Reject mismatched bindings before I/O; never automatically retry UNKNOWN.

        The implementation must persist intent and policy audit before transmission,
        check current registry state and atomically consume budget for every request.
        A capture failure after a known send remains SENT with UNAVAILABLE capture.
        """
        ...
