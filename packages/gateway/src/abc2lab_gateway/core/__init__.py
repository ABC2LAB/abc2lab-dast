"""Domain logic for gateway; external IO belongs in adapters."""

from abc2lab_gateway.core.model import (
    AttemptOutcome,
    CaptureStatus,
    DecisionCommit,
    DecisionOutcome,
    GatewayReason,
    PreTransportGate,
    RecheckResult,
    SendStatus,
    TransportObservation,
)
from abc2lab_gateway.core.outcome import (
    classify_attempt,
    classify_pre_transport,
    classify_transport,
)

__all__ = [
    "AttemptOutcome",
    "CaptureStatus",
    "DecisionCommit",
    "DecisionOutcome",
    "GatewayReason",
    "PreTransportGate",
    "RecheckResult",
    "SendStatus",
    "TransportObservation",
    "classify_attempt",
    "classify_pre_transport",
    "classify_transport",
]
