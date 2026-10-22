"""C4-B Judge reason taxonomy and fail-closed result guards."""

import pytest
from abc2lab_contracts.judge import JudgePolicyReadResult, JudgeResult
from abc2lab_contracts.primitives import ReasonCode, ResultStatus, RunKey
from abc2lab_contracts.reason_codes import (
    CALL_AUDIT_FAILURE_REASON_CODES,
    CALL_AUDIT_REASON_CODES,
    JUDGE_DIAGNOSTIC_REASON_CODES,
)

RUN = RunKey("org", "target", "environment", "run")
DIAGNOSTIC_NAMES = {
    "POLICY_ALLOWS",
    "SHARING_OR_DELEGATION_ALLOWS",
    "EXPECTED_ACCESS_UNKNOWN",
    "SUBJECT_NOT_VERIFIED",
    "SUBJECTS_NOT_DISTINCT",
    "DATA_NO_MATCH",
    "DATA_REFLECTION_PRESENT",
    "DATA_TEMPLATE_PRESENT",
    "DATA_UNVERIFIABLE",
    "EXPECTED_ACCESS_POLICY_MISSING",
    "EXPECTED_ACCESS_POLICY_INVALID",
    "SHARING_OR_DELEGATION_UNKNOWN",
}


def _failed_judge(*reason_codes: ReasonCode) -> JudgeResult:
    return JudgeResult(RUN, ResultStatus.FAILED, None, None, reason_codes)


def _failed_policy_read(*reason_codes: ReasonCode) -> JudgePolicyReadResult:
    return JudgePolicyReadResult(RUN, "case-1", ResultStatus.FAILED, None, reason_codes)


def test_judge_diagnostic_taxonomy_is_exact_and_exhaustive() -> None:
    assert {reason.name for reason in JUDGE_DIAGNOSTIC_REASON_CODES} == DIAGNOSTIC_NAMES
    classified = set(JUDGE_DIAGNOSTIC_REASON_CODES) | set(CALL_AUDIT_REASON_CODES)
    assert classified == set(ReasonCode)
    assert set(JUDGE_DIAGNOSTIC_REASON_CODES).isdisjoint(CALL_AUDIT_REASON_CODES)


def test_failure_whitelist_excludes_positive_canary_and_is_audit_subset() -> None:
    assert CALL_AUDIT_FAILURE_REASON_CODES <= CALL_AUDIT_REASON_CODES
    assert CALL_AUDIT_REASON_CODES - CALL_AUDIT_FAILURE_REASON_CODES == {
        ReasonCode.COMPARISON_CANARY_PASSED
    }


def test_failed_judge_accepts_only_failure_reason_codes() -> None:
    for reason in CALL_AUDIT_FAILURE_REASON_CODES:
        result = _failed_judge(reason)
        assert result.status is ResultStatus.FAILED
    with pytest.raises(ValueError):
        _failed_judge(ReasonCode.COMPARISON_CANARY_PASSED)
    for diagnostic in JUDGE_DIAGNOSTIC_REASON_CODES:
        with pytest.raises(ValueError):
            _failed_judge(diagnostic)


def test_failed_policy_read_accepts_only_failure_reason_codes() -> None:
    for reason in CALL_AUDIT_FAILURE_REASON_CODES:
        result = _failed_policy_read(reason)
        assert result.status is ResultStatus.FAILED
    with pytest.raises(ValueError):
        _failed_policy_read(ReasonCode.COMPARISON_CANARY_PASSED)
    for diagnostic in JUDGE_DIAGNOSTIC_REASON_CODES:
        with pytest.raises(ValueError):
            _failed_policy_read(diagnostic)


@pytest.mark.parametrize(
    "failure_reason",
    [
        ReasonCode.ACCESS_DENIED,
        ReasonCode.SOURCE_UNVERIFIED,
        ReasonCode.AUDIT_COMMIT_FAILED,
    ],
)
def test_failed_results_reject_nonfailure_and_failure_reason_mixes(
    failure_reason: ReasonCode,
) -> None:
    for nonfailure in JUDGE_DIAGNOSTIC_REASON_CODES | {ReasonCode.COMPARISON_CANARY_PASSED}:
        with pytest.raises(ValueError):
            _failed_judge(nonfailure, failure_reason)
        with pytest.raises(ValueError):
            _failed_judge(failure_reason, nonfailure)
        with pytest.raises(ValueError):
            _failed_policy_read(nonfailure, failure_reason)
        with pytest.raises(ValueError):
            _failed_policy_read(failure_reason, nonfailure)


def test_failed_results_reject_empty_reasons() -> None:
    with pytest.raises(ValueError):
        _failed_judge()
    with pytest.raises(ValueError):
        _failed_policy_read()


def test_known_absence_is_exactly_one_reason() -> None:
    missing = JudgePolicyReadResult(
        RUN,
        "case-1",
        ResultStatus.COMPLETE,
        None,
        (ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,),
    )
    assert missing.expected_policy is None
    with pytest.raises(ValueError):
        JudgePolicyReadResult(RUN, "case-1", ResultStatus.COMPLETE, None, ())


@pytest.mark.parametrize("reason", tuple(ReasonCode))
def test_known_absence_rejects_every_extra_reason(reason: ReasonCode) -> None:
    missing = ReasonCode.EXPECTED_ACCESS_POLICY_MISSING
    for reasons in ((missing, reason), (reason, missing)):
        with pytest.raises(ValueError):
            JudgePolicyReadResult(RUN, "case-1", ResultStatus.COMPLETE, None, reasons)
    if reason is not missing:
        with pytest.raises(ValueError):
            JudgePolicyReadResult(RUN, "case-1", ResultStatus.COMPLETE, None, (reason,))


def test_failed_result_cannot_use_known_absence_marker() -> None:
    for factory in (_failed_judge, _failed_policy_read):
        with pytest.raises(ValueError):
            factory(ReasonCode.EXPECTED_ACCESS_POLICY_MISSING)
