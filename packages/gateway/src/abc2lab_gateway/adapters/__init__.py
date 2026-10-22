"""IO adapters for gateway; implementations are injected by app."""

from abc2lab_gateway.adapters.handles import (
    InMemoryPreparedHandleStore,
    PreparedHandleStore,
    PreparedRequest,
    new_prepared_handle,
)
from abc2lab_gateway.adapters.prepare import (
    build_owner_identity,
    build_policy_input,
    derive_identity_view,
    derive_policy_attributes,
)
from abc2lab_gateway.adapters.registration import (
    GatewayRegistration,
    GatewayRegistrationSource,
    InMemoryGatewayRegistrations,
)
from abc2lab_gateway.adapters.service import (
    GatewayPreparer,
    PrepareError,
    new_binding_id,
)
from abc2lab_gateway.adapters.translation import (
    AttemptContext,
    to_attempt_result,
    to_contract_reasons,
    to_decision_outcome,
)

__all__ = [
    "AttemptContext",
    "GatewayPreparer",
    "GatewayRegistration",
    "GatewayRegistrationSource",
    "InMemoryGatewayRegistrations",
    "InMemoryPreparedHandleStore",
    "PrepareError",
    "PreparedHandleStore",
    "PreparedRequest",
    "build_owner_identity",
    "build_policy_input",
    "derive_identity_view",
    "derive_policy_attributes",
    "new_binding_id",
    "new_prepared_handle",
    "to_attempt_result",
    "to_contract_reasons",
    "to_decision_outcome",
]
