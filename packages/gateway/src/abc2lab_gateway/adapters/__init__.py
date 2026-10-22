"""IO adapters for gateway; implementations are injected by app."""

from abc2lab_gateway.adapters.translation import (
    AttemptContext,
    to_attempt_result,
    to_contract_reasons,
    to_decision_outcome,
)

__all__ = [
    "AttemptContext",
    "to_attempt_result",
    "to_contract_reasons",
    "to_decision_outcome",
]
