"""IO adapters for gateway; implementations are injected by app."""

from abc2lab_gateway.adapters.budget import BudgetLedger, InMemoryBudgetLedger
from abc2lab_gateway.adapters.execute import (
    ExecuteDependencies,
    ExecuteSettings,
    GatewayExecutor,
    new_attempt_ref,
)
from abc2lab_gateway.adapters.handles import (
    InMemoryPreparedHandleStore,
    PreparedHandleStore,
    PreparedRequest,
    new_prepared_handle,
)
from abc2lab_gateway.adapters.journal import (
    GatewayJournal,
    InMemoryGatewayJournal,
    JournalCommitError,
    attempt_record_binding,
    intent_record_binding,
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
from abc2lab_gateway.adapters.transport import SendCommand, SendOutcome, StubTransport, Transport
from abc2lab_gateway.adapters.vault import InMemoryVaultBinder, VaultBinder

__all__ = [
    "AttemptContext",
    "BudgetLedger",
    "ExecuteDependencies",
    "ExecuteSettings",
    "GatewayExecutor",
    "GatewayJournal",
    "GatewayPreparer",
    "GatewayRegistration",
    "GatewayRegistrationSource",
    "InMemoryBudgetLedger",
    "InMemoryGatewayJournal",
    "InMemoryGatewayRegistrations",
    "InMemoryPreparedHandleStore",
    "InMemoryVaultBinder",
    "JournalCommitError",
    "PrepareError",
    "PreparedHandleStore",
    "PreparedRequest",
    "SendCommand",
    "SendOutcome",
    "StubTransport",
    "Transport",
    "VaultBinder",
    "attempt_record_binding",
    "build_owner_identity",
    "build_policy_input",
    "derive_identity_view",
    "derive_policy_attributes",
    "intent_record_binding",
    "new_attempt_ref",
    "new_binding_id",
    "new_prepared_handle",
    "to_attempt_result",
    "to_contract_reasons",
    "to_decision_outcome",
]
