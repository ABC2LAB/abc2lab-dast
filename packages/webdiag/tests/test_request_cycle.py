"""run_request의 prepare→evaluate→execute 순서와 실패 분기를 검사한다."""

from datetime import UTC, datetime

import pytest
from abc2lab_contracts.execution import (
    AttemptResult,
    ExecuteRequest,
    ExecutionRequest,
    PolicyAttributes,
    PolicyDecisionResult,
    PolicyIdentityStatus,
    PolicyInput,
    PrepareResult,
    PrivateHttpRequest,
)
from abc2lab_contracts.primitives import (
    AuditLink,
    CaptureStatus,
    Purpose,
    ReasonCode,
    ResultStatus,
    RunKey,
    SendStatus,
    SourceVersion,
)
from abc2lab_contracts.registration import (
    BudgetSnapshot,
    ExecutionProfileSnapshot,
    ScopeSnapshot,
)
from abc2lab_webdiag.core.request_cycle import run_request, to_attempt_summary

_RUN = RunKey(
    organization_ref="org-1", target_ref="target-1", environment_ref="env-1", run_ref="run-1"
)
_SRC = SourceVersion(issuer="issuer-1", source_ref="src-1", revision=1)
_T0 = datetime(2026, 10, 22, 0, 0, 0, tzinfo=UTC)
_T1 = datetime(2026, 10, 22, 1, 0, 0, tzinfo=UTC)


def _policy_input() -> PolicyInput:
    return PolicyInput(
        schema_version="policy_input.v1",
        run_key=_RUN,
        request_ref="req-1",
        binding_id="binding-1",
        binding_issuer="gateway-1",
        expires_at=_T1,
        origin="https://app.example",
        method="GET",
        operation_ref="op-1",
        operation_revision=1,
        purpose=Purpose.OBSERVE,
        policy_attributes=PolicyAttributes(
            registered_path_matches=True,
            parameter_names=(),
            parameters_match_registration=True,
            resource_ref=None,
            resource_binding_ref=None,
            resource_binding_revision=None,
            resource_owner_subject_ref=None,
            provenance=_SRC,
        ),
        account_ref=None,
        session_generation=None,
        identity_ref=None,
        subject_ref=None,
        identity_status=PolicyIdentityStatus.ANONYMOUS,
        owner_identity=None,
        scope=ScopeSnapshot(
            source=_SRC,
            allowed_origins=("https://app.example",),
            allowed_operation_refs=("op-1",),
            valid_from=_T0,
            valid_until=_T1,
        ),
        profile=ExecutionProfileSnapshot(
            source=_SRC,
            allowed_methods=("GET",),
            allowed_purposes=(Purpose.OBSERVE,),
            allow_redirects=False,
            valid_until=_T1,
        ),
        budget=BudgetSnapshot(
            source=_SRC, max_attempts=10, max_duration_ms=1000, max_response_bytes=1048576
        ),
        expected_policy=None,
        cross_confirmation=None,
    )


def _exec_request(request_ref: str = "req-1") -> ExecutionRequest:
    return ExecutionRequest(
        run_key=_RUN,
        request_ref=request_ref,
        operation_ref="op-1",
        operation_revision=1,
        resource_ref=None,
        resource_binding_ref=None,
        resource_binding_revision=None,
        purpose=Purpose.OBSERVE,
        http=PrivateHttpRequest(
            origin="https://app.example",
            method="GET",
            path="/orders/1",
            parameters=(),
            timeout_ms=5000,
        ),
        session=None,
        owner_session=None,
        scope_revision=1,
        profile_revision=1,
        expected_policy=None,
        cross_confirmation=None,
    )


def _not_sent() -> AttemptResult:
    return AttemptResult(
        run_key=_RUN,
        request_ref="req-1",
        attempt_ref="attempt-1",
        decision_ref=None,
        binding_id=None,
        send_status=SendStatus.NOT_SENT,
        capture_status=CaptureStatus.NOT_APPLICABLE,
        capture_ref=None,
        auth_signal=None,
        audit_links=(),
        reason_codes=(ReasonCode.POLICY_BLOCKED,),
    )


def _prepare(status: ResultStatus, *, handle: str | None, with_input: bool) -> PrepareResult:
    return PrepareResult(
        run_key=_RUN,
        status=status,
        prepared_handle=handle,
        policy_input=_policy_input() if with_input else None,
        reason_codes=() if status is ResultStatus.COMPLETE else (ReasonCode.CONFIGURATION_MISSING,),
    )


class _FakeGateway:
    def __init__(self, prepare: PrepareResult, execute: AttemptResult) -> None:
        self._prepare = prepare
        self._execute = execute
        self.prepared: list[ExecutionRequest] = []
        self.executed: list[ExecuteRequest] = []

    async def prepare(self, request: ExecutionRequest) -> PrepareResult:
        self.prepared.append(request)
        return self._prepare

    async def execute(self, request: ExecuteRequest) -> AttemptResult:
        self.executed.append(request)
        return self._execute


class _FakePolicy:
    def __init__(self) -> None:
        self.evaluated: list[PolicyInput] = []

    async def evaluate(self, request: PolicyInput) -> PolicyDecisionResult:
        self.evaluated.append(request)
        return PolicyDecisionResult(
            run_key=_RUN,
            status=ResultStatus.FAILED,
            decision=None,
            reason_codes=(ReasonCode.AUDIT_COMMIT_FAILED,),
        )


@pytest.mark.asyncio
async def test_prepare_failure_skips_execute_and_policy() -> None:
    """prepare 실패 시 execute·evaluate를 호출하지 않고 시도 없이 사유만 남긴다."""
    gateway = _FakeGateway(
        _prepare(ResultStatus.FAILED, handle=None, with_input=False), _not_sent()
    )
    policy = _FakePolicy()
    outcome = await run_request(gateway, policy, _exec_request())
    assert outcome.attempt is None
    assert ReasonCode.CONFIGURATION_MISSING in outcome.reason_codes
    assert gateway.executed == []
    assert policy.evaluated == []


@pytest.mark.asyncio
async def test_prepare_complete_executes_with_forwarded_decision() -> None:
    """prepare 완료 시 policy_input을 평가하고 그 결정으로 execute를 호출한다."""
    gateway = _FakeGateway(
        _prepare(ResultStatus.COMPLETE, handle="handle-1", with_input=True), _not_sent()
    )
    policy = _FakePolicy()
    outcome = await run_request(gateway, policy, _exec_request(request_ref="req-1"))
    assert policy.evaluated[0].binding_id == "binding-1"
    executed = gateway.executed[0]
    assert executed.prepared_handle == "handle-1"
    assert executed.request_ref == "req-1"
    assert executed.decision is None  # 정책 저장 실패여도 execute가 not_sent를 발행
    assert outcome.attempt is not None
    assert outcome.attempt.send_status is SendStatus.NOT_SENT


def test_to_attempt_summary_excludes_capture_and_signal() -> None:
    """공개 요약은 캡처 참조·인증 신호를 포함하지 않고 전송 상태를 보존한다."""
    attempt = AttemptResult(
        run_key=_RUN,
        request_ref="req-1",
        attempt_ref="attempt-1",
        decision_ref="decision-1",
        binding_id="binding-1",
        send_status=SendStatus.SENT,
        capture_status=CaptureStatus.CAPTURED,
        capture_ref="cap-1",
        auth_signal=None,
        audit_links=(AuditLink(producer="gw", event_ref="e1"),),
        reason_codes=(),
    )
    summary = to_attempt_summary(attempt)
    assert summary.attempt_ref == "attempt-1"
    assert summary.send_status is SendStatus.SENT
    assert summary.audit_links == (AuditLink(producer="gw", event_ref="e1"),)
    assert not hasattr(summary, "capture_ref")
