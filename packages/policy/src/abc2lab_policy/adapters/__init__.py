"""IO adapters for policy; implementations are injected by app."""

from abc2lab_policy.adapters.journal import (
    CommittedDecision,
    InMemoryPolicyDecisionJournal,
    JournalCommitError,
    PolicyDecisionJournal,
    decision_record_binding,
)
from abc2lab_policy.adapters.service import (
    InMemoryPolicyRegistrations,
    PolicyRegistration,
    PolicyRegistrationSource,
    PolicyService,
    new_decision_ref,
)
from abc2lab_policy.adapters.translation import (
    build_authorization_context,
    build_evaluation_request,
    source_version_key,
    to_contract_reasons,
    to_policy_outcome,
)
from abc2lab_policy.adapters.view_checks import (
    check_cross_execution,
    check_injected_view_consistency,
)

__all__ = [
    "CommittedDecision",
    "InMemoryPolicyDecisionJournal",
    "InMemoryPolicyRegistrations",
    "JournalCommitError",
    "PolicyDecisionJournal",
    "PolicyRegistration",
    "PolicyRegistrationSource",
    "PolicyService",
    "build_authorization_context",
    "build_evaluation_request",
    "check_cross_execution",
    "check_injected_view_consistency",
    "decision_record_binding",
    "new_decision_ref",
    "source_version_key",
    "to_contract_reasons",
    "to_policy_outcome",
]
