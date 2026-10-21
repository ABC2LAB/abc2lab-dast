"""Domain logic for judge; external IO belongs in adapters."""

from abc2lab_judge.core.model import (
    CaseInput,
    CheckOutcome,
    CheckState,
    ComparisonFacts,
    ExpectedAccess,
    JudgeReason,
    OracleVerdict,
    PolicyAssertion,
    ResolutionState,
    SubjectContext,
    SubjectStatus,
    VerdictValue,
)
from abc2lab_judge.core.oracle import (
    check_data,
    check_expected_policy,
    check_identity,
    evaluate_case,
)

__all__ = [
    "CaseInput",
    "CheckOutcome",
    "CheckState",
    "ComparisonFacts",
    "ExpectedAccess",
    "JudgeReason",
    "OracleVerdict",
    "PolicyAssertion",
    "ResolutionState",
    "SubjectContext",
    "SubjectStatus",
    "VerdictValue",
    "check_data",
    "check_expected_policy",
    "check_identity",
    "evaluate_case",
]
