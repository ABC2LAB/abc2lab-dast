"""IO adapters for judge; implementations are injected by app."""

from abc2lab_judge.adapters.attestation import (
    DEFAULT_AUDIT_MAX_PAGES,
    DEFAULT_AUDIT_PAGE_LIMIT,
    AuditSource,
    CallFailure,
)
from abc2lab_judge.adapters.idempotency import InMemorySubmissionStore
from abc2lab_judge.adapters.journal import (
    CommittedVerdict,
    InMemoryVerdictJournal,
    JournalCommitError,
    VerdictJournal,
    verdict_record_binding,
)
from abc2lab_judge.adapters.ports import JudgeReadAuthorizer
from abc2lab_judge.adapters.service import (
    JudgeDependencies,
    JudgeService,
    JudgeSettings,
    VerdictPublisher,
    new_event_ref,
)
from abc2lab_judge.adapters.translation import (
    VerdictContext,
    to_check_state,
    to_contract_reasons,
    to_verdict,
    to_verdict_value,
)

__all__ = [
    "DEFAULT_AUDIT_MAX_PAGES",
    "DEFAULT_AUDIT_PAGE_LIMIT",
    "AuditSource",
    "CallFailure",
    "CommittedVerdict",
    "InMemorySubmissionStore",
    "JudgeDependencies",
    "JudgeReadAuthorizer",
    "JudgeService",
    "JudgeSettings",
    "InMemoryVerdictJournal",
    "JournalCommitError",
    "VerdictContext",
    "VerdictJournal",
    "VerdictPublisher",
    "new_event_ref",
    "to_check_state",
    "to_contract_reasons",
    "to_verdict",
    "to_verdict_value",
    "verdict_record_binding",
]
