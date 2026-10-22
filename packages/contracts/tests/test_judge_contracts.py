"""C4-B Judge request, result, policy-reader, and Verdict invariants."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from abc2lab_contracts.audit import AuditEventKind, AuditReceipt, AuditRecordBinding
from abc2lab_contracts.fingerprint import verdict_fingerprint
from abc2lab_contracts.judge import (
    JudgePolicyReadRequest,
    JudgePolicyReadResult,
    JudgeRequest,
    JudgeResult,
)
from abc2lab_contracts.ports import JudgePolicyReader, JudgePort
from abc2lab_contracts.primitives import (
    AuditLink,
    CheckState,
    ReadContext,
    ReasonCode,
    ResultStatus,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.projection import VerdictProjected
from abc2lab_contracts.registration import (
    ExpectedAccess,
    ExpectedAccessPolicySnapshot,
    ResolutionState,
)
from abc2lab_contracts.session import IdentityResult, IdentityStatus
from abc2lab_contracts.verdict import Verdict, VerdictValue

STAMP = datetime(2026, 10, 22, tzinfo=UTC)


def _run() -> RunKey:
    return RunKey("org", "target", "environment", "run")


def _context() -> ReadContext:
    return ReadContext("caller", "authorization")


def _policy(run: RunKey | None = None) -> ExpectedAccessPolicySnapshot:
    current = run or _run()
    return ExpectedAccessPolicySnapshot(
        SourceVersion("registration", "policy", 3),
        "policy-1",
        current.target_ref,
        current.environment_ref,
        "resource-1",
        "operation-1",
        "owner-subject",
        "evaluated-subject",
        ExpectedAccess.DENY,
        ResolutionState.RESOLVED_NONE,
        ResolutionState.RESOLVED_NONE,
        STAMP,
        STAMP + timedelta(hours=1),
    )


def _identity(run: RunKey | None = None) -> IdentityResult:
    return IdentityResult(
        run or _run(),
        "identity-1",
        IdentityStatus.UNKNOWN,
        "session-1",
        "account-1",
        1,
        None,
        None,
        None,
        None,
        None,
        (),
        (),
    )


def _verdict(
    *,
    value: VerdictValue = VerdictValue.UNDECIDABLE,
    policy_check: CheckState = CheckState.UNKNOWN,
    identity_check: CheckState = CheckState.UNKNOWN,
    data_check: CheckState = CheckState.UNKNOWN,
    expected_policy_source: SourceVersion | None = None,
    comparison_ref: str | None = None,
    evidence_refs: tuple[str, ...] = (),
    reasons: tuple[ReasonCode, ...] = (ReasonCode.DATA_UNVERIFIABLE,),
) -> Verdict:
    return Verdict(
        _run(),
        "verdict-1",
        1,
        "case-1",
        value,
        policy_check,
        identity_check,
        data_check,
        expected_policy_source,
        comparison_ref,
        evidence_refs,
        SourceVersion("judge", "oracle", 1),
        AuditLink("judge", "verdict-event"),
        reasons,
    )


def _projected(verdict: Verdict | None = None) -> VerdictProjected:
    current = verdict or _verdict()
    binding = AuditRecordBinding(
        AuditEventKind.VERDICT,
        current.verdict_ref,
        current.revision,
        verdict_fingerprint(current),
        None,
        None,
        None,
    )
    receipt = AuditReceipt(_run(), "judge", "verdict-event", 1, binding, STAMP)
    return VerdictProjected(
        AuditEventKind.VERDICT,
        "verdict-event",
        _run(),
        "judge",
        current.revision,
        receipt,
        current,
    )


def _request(**changes: object) -> JudgeRequest:
    values: dict[str, object] = {
        "run_key": _run(),
        "context": _context(),
        "case_ref": "case-1",
        "submission_ref": "submission-1",
        "expected_policy": None,
        "owner_identity": None,
        "evaluated_identity": None,
        "comparison_ref": None,
    }
    values.update(changes)
    return JudgeRequest(**values)  # type: ignore[arg-type]


def test_judge_request_accepts_optional_evidence_and_requires_context() -> None:
    request = _request()
    assert request.context == _context()
    assert request.expected_policy is None
    with pytest.raises((AttributeError, TypeError)):
        request.case_ref = "other-case"  # type: ignore[misc]
    with pytest.raises(TypeError, match="contract record"):
        _request(context=None)
    with pytest.raises(TypeError):
        _request(context=object())
    with pytest.raises(ValueError, match="non-empty reference"):
        _request(case_ref="")
    with pytest.raises(ValueError, match="non-empty reference"):
        _request(submission_ref="")
    with pytest.raises((TypeError, ValueError)):
        _request(comparison_ref="")
    with pytest.raises(ValueError, match="non-empty reference"):
        ReadContext("", "authorization")
    with pytest.raises(ValueError, match="non-empty reference"):
        ReadContext("caller", "")


def test_judge_request_rejects_wrong_nested_policy_and_policy_reader_request() -> None:
    with pytest.raises(TypeError):
        _request(expected_policy=object())
    with pytest.raises(TypeError):
        JudgePolicyReadRequest(
            _run(),
            _context(),
            "case-1",
            object(),  # type: ignore[arg-type]
        )


def test_judge_request_rejects_policy_and_identity_run_mismatch() -> None:
    other_run = RunKey("org", "other-target", "environment", "run")
    with pytest.raises(ValueError, match="run|target|environment"):
        _request(expected_policy=_policy(other_run))
    assert _request(owner_identity=_identity()).owner_identity is not None
    with pytest.raises(ValueError, match="identity run mismatch"):
        _request(owner_identity=_identity(other_run))
    with pytest.raises(ValueError, match="identity run mismatch"):
        _request(evaluated_identity=_identity(other_run))


def test_judge_result_complete_requires_matching_projection_and_no_failure_reason() -> None:
    verdict = _verdict()
    result = JudgeResult(_run(), ResultStatus.COMPLETE, verdict, _projected(verdict), ())
    assert result.status is ResultStatus.COMPLETE
    with pytest.raises(ValueError):
        JudgeResult(_run(), ResultStatus.COMPLETE, None, _projected(verdict), ())
    with pytest.raises(ValueError):
        JudgeResult(_run(), ResultStatus.COMPLETE, verdict, None, ())
    with pytest.raises(ValueError):
        JudgeResult(
            _run(),
            ResultStatus.COMPLETE,
            verdict,
            _projected(verdict),
            (ReasonCode.DATA_UNVERIFIABLE,),
        )
    other_verdict = replace(verdict, verdict_ref="other-verdict")
    with pytest.raises(ValueError):
        JudgeResult(_run(), ResultStatus.COMPLETE, verdict, _projected(other_verdict), ())
    with pytest.raises(ValueError):
        JudgeResult(
            RunKey("org", "other-target", "environment", "run"),
            ResultStatus.COMPLETE,
            verdict,
            _projected(verdict),
            (),
        )


def test_judge_result_failed_requires_reason_and_publishes_no_artifacts() -> None:
    result = JudgeResult(_run(), ResultStatus.FAILED, None, None, (ReasonCode.SOURCE_UNVERIFIED,))
    assert result.verdict is None
    with pytest.raises(ValueError):
        JudgeResult(_run(), ResultStatus.FAILED, None, None, ())
    with pytest.raises(ValueError):
        JudgeResult(_run(), ResultStatus.FAILED, _verdict(), None, (ReasonCode.SOURCE_UNVERIFIED,))
    with pytest.raises(ValueError):
        JudgeResult(
            _run(), ResultStatus.FAILED, None, _projected(), (ReasonCode.SOURCE_UNVERIFIED,)
        )
    with pytest.raises(ValueError):
        JudgeResult(_run(), ResultStatus.PARTIAL, None, None, (ReasonCode.AUDIT_GAP,))


def test_policy_reader_result_preserves_missing_and_failed_meanings() -> None:
    missing = JudgePolicyReadResult(
        _run(),
        "case-1",
        ResultStatus.COMPLETE,
        None,
        (ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,),
    )
    assert missing.expected_policy is None
    resolved = JudgePolicyReadResult(_run(), "case-1", ResultStatus.COMPLETE, _policy(), ())
    assert resolved.expected_policy is not None
    failed = JudgePolicyReadResult(
        _run(), "case-1", ResultStatus.FAILED, None, (ReasonCode.NOT_FOUND,)
    )
    assert failed.status is ResultStatus.FAILED
    with pytest.raises(ValueError):
        JudgePolicyReadResult(_run(), "case-1", ResultStatus.COMPLETE, None, ())
    with pytest.raises(ValueError):
        JudgePolicyReadResult(
            _run(), "case-1", ResultStatus.COMPLETE, None, (ReasonCode.NOT_FOUND,)
        )
    with pytest.raises(ValueError):
        JudgePolicyReadResult(
            _run(),
            "case-1",
            ResultStatus.COMPLETE,
            _policy(),
            (ReasonCode.EXPECTED_ACCESS_POLICY_INVALID,),
        )
    with pytest.raises(ValueError):
        JudgePolicyReadResult(
            _run(),
            "case-1",
            ResultStatus.COMPLETE,
            _policy(RunKey("org", "other-target", "environment", "run")),
            (),
        )
    with pytest.raises(ValueError):
        JudgePolicyReadResult(
            _run(), "case-1", ResultStatus.FAILED, _policy(), (ReasonCode.NOT_FOUND,)
        )
    with pytest.raises(ValueError):
        JudgePolicyReadResult(_run(), "case-1", ResultStatus.PARTIAL, None, (ReasonCode.AUDIT_GAP,))
    with pytest.raises(ValueError):
        JudgePolicyReadResult(_run(), "case-1", ResultStatus.FAILED, None, ())


def test_suspected_requires_unknown_policy_yes_identity_data_and_supporting_refs() -> None:
    valid = _verdict(
        value=VerdictValue.SUSPECTED,
        policy_check=CheckState.UNKNOWN,
        identity_check=CheckState.YES,
        data_check=CheckState.YES,
        comparison_ref="comparison-1",
        evidence_refs=("evidence-1",),
        reasons=(ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,),
    )
    assert valid.value is VerdictValue.SUSPECTED
    for field, value in (
        ("policy_check", CheckState.NO),
        ("policy_check", CheckState.YES),
        ("identity_check", CheckState.NO),
        ("identity_check", CheckState.UNKNOWN),
        ("data_check", CheckState.NO),
        ("data_check", CheckState.UNKNOWN),
        ("comparison_ref", None),
        ("evidence_refs", ()),
        ("reason_codes", ()),
    ):
        with pytest.raises(ValueError):
            replace(valid, **{field: value})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("policy_check", CheckState.NO),
        ("policy_check", CheckState.UNKNOWN),
        ("identity_check", CheckState.NO),
        ("identity_check", CheckState.UNKNOWN),
        ("data_check", CheckState.NO),
        ("data_check", CheckState.UNKNOWN),
        ("expected_policy_source", None),
        ("comparison_ref", None),
        ("evidence_refs", ()),
    ),
)
def test_confirmed_requires_all_positive_evidence(field: str, value: object) -> None:
    valid = _verdict(
        value=VerdictValue.CONFIRMED,
        policy_check=CheckState.YES,
        identity_check=CheckState.YES,
        data_check=CheckState.YES,
        expected_policy_source=_policy().source,
        comparison_ref="comparison-1",
        evidence_refs=("evidence-1",),
        reasons=(),
    )
    with pytest.raises(ValueError):
        replace(valid, **{field: value})  # type: ignore[arg-type]


def test_allowed_requires_policy_source_no_check_and_allow_reason_only() -> None:
    # These are shape requirements, not sufficient evidence of permission.
    # UNKNOWN A/B distinctness or cross-data exposure does not waive service
    # verification of B's identity and the registered policy (J-ALLOW-01..06).
    for reason in (ReasonCode.POLICY_ALLOWS, ReasonCode.SHARING_OR_DELEGATION_ALLOWS):
        valid = _verdict(
            value=VerdictValue.ALLOWED,
            policy_check=CheckState.NO,
            identity_check=CheckState.UNKNOWN,
            data_check=CheckState.UNKNOWN,
            expected_policy_source=_policy().source,
            reasons=(reason,),
        )
        assert valid.comparison_ref is None
    for field, value in (
        ("policy_check", CheckState.YES),
        ("policy_check", CheckState.UNKNOWN),
        ("expected_policy_source", None),
        ("reason_codes", ()),
        ("reason_codes", (ReasonCode.DATA_UNVERIFIABLE,)),
    ):
        valid = _verdict(
            value=VerdictValue.ALLOWED,
            policy_check=CheckState.NO,
            expected_policy_source=_policy().source,
            reasons=(ReasonCode.POLICY_ALLOWS,),
        )
        with pytest.raises(ValueError):
            replace(valid, **{field: value})  # type: ignore[arg-type]


def test_undecidable_requires_reason() -> None:
    with pytest.raises(ValueError):
        _verdict(reasons=())


def test_judge_reason_codes_include_exact_nine_new_values() -> None:
    expected = {
        "POLICY_ALLOWS": "policy_allows",
        "SHARING_OR_DELEGATION_ALLOWS": "sharing_or_delegation_allows",
        "EXPECTED_ACCESS_UNKNOWN": "expected_access_unknown",
        "SUBJECT_NOT_VERIFIED": "subject_not_verified",
        "SUBJECTS_NOT_DISTINCT": "subjects_not_distinct",
        "DATA_NO_MATCH": "data_no_match",
        "DATA_REFLECTION_PRESENT": "data_reflection_present",
        "DATA_TEMPLATE_PRESENT": "data_template_present",
        "DATA_UNVERIFIABLE": "data_unverifiable",
    }
    for name, value in expected.items():
        reason = getattr(ReasonCode, name)
        assert reason.value == value
    for name in (
        "POLICY_DENY_RESOLVED",
        "SUBJECTS_DISTINCT_VERIFIED",
        "DATA_NONTRIVIAL_MATCH",
    ):
        assert not hasattr(ReasonCode, name)


def test_data_unverifiable_can_be_complete_undecidable_and_projected() -> None:
    verdict = _verdict(reasons=(ReasonCode.DATA_UNVERIFIABLE,))
    result = JudgeResult(_run(), ResultStatus.COMPLETE, verdict, _projected(verdict), ())
    assert result.verdict is verdict


def test_projection_rejects_changed_verdict_fingerprint_or_source() -> None:
    verdict = _verdict()
    projected = _projected(verdict)
    with pytest.raises(ValueError):
        replace(projected, verdict=replace(verdict, reason_codes=(ReasonCode.DATA_NO_MATCH,)))
    with pytest.raises(ValueError):
        replace(projected, event_ref="other-event")
    binding = projected.source_receipt.binding
    for changed in (
        replace(binding, record_fingerprint="0" * 64),
        replace(binding, record_revision=2),
    ):
        with pytest.raises(ValueError):
            replace(projected, source_receipt=replace(projected.source_receipt, binding=changed))
    with pytest.raises(ValueError):
        replace(projected, producer="other-producer")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_revision", 2),
        ("producer", "other-producer"),
        ("event_ref", "other-event"),
        ("record_fingerprint", "0" * 64),
        ("record_revision", 2),
    ],
)
def test_judge_result_revalidates_bypassed_nested_projection(field: str, value: object) -> None:
    verdict = _verdict()
    projected = _projected(verdict)
    nested = projected.source_receipt.binding if field.startswith("record_") else projected
    object.__setattr__(nested, field, value)
    with pytest.raises((TypeError, ValueError)):
        JudgeResult(_run(), ResultStatus.COMPLETE, verdict, projected, ())


@pytest.mark.parametrize(
    "reason", [ReasonCode.POLICY_ALLOWS, ReasonCode.SHARING_OR_DELEGATION_ALLOWS]
)
def test_reason_labels_do_not_prove_policy_provenance(reason: ReasonCode) -> None:
    # Only Judge can check whether an asserted reason actually matches a trusted policy.
    # Constructor acceptance is not permission to publish SUSPECTED for a verified allow.
    verdict = _verdict(
        value=VerdictValue.SUSPECTED,
        policy_check=CheckState.UNKNOWN,
        identity_check=CheckState.YES,
        data_check=CheckState.YES,
        comparison_ref="comparison-1",
        evidence_refs=("evidence-1",),
        reasons=(reason,),
    )
    assert verdict.policy_check is CheckState.UNKNOWN


class _FakeJudge:
    async def judge(self, request: JudgeRequest) -> JudgeResult:
        return JudgeResult(
            request.run_key, ResultStatus.FAILED, None, None, (ReasonCode.NOT_FOUND,)
        )


class _FakePolicyReader:
    async def read_case_policy(self, request: JudgePolicyReadRequest) -> JudgePolicyReadResult:
        return JudgePolicyReadResult(
            request.run_key,
            request.case_ref,
            ResultStatus.COMPLETE,
            _policy(),
            (),
        )


@pytest.mark.asyncio
async def test_judge_protocols_are_async_and_implementable_without_io() -> None:
    judge: JudgePort = _FakeJudge()
    reader: JudgePolicyReader = _FakePolicyReader()
    result, policy = await _call_ports(judge, reader)
    assert result.status is ResultStatus.FAILED
    assert policy.expected_policy == _policy()


async def _call_ports(
    judge: JudgePort, reader: JudgePolicyReader
) -> tuple[JudgeResult, JudgePolicyReadResult]:
    request = _request()
    policy_request = JudgePolicyReadRequest(_run(), _context(), "case-1", None)
    return await judge.judge(request), await reader.read_case_policy(policy_request)
