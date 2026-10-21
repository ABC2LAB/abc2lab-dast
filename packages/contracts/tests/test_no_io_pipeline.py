"""실제 I/O 없이 C2 포트를 연결하는 실행 가능한 소비자 예제다.

정해진 결과를 재생하는 로컬 fake다. 실제 정책 판단, intent 내구성,
세션/예산/핸들 보안 검사는 각 서비스 구현과 S1 통합 테스트의 책임이다.
"""

from dataclasses import replace

import pytest
from abc2lab_contracts.audit import (
    AuditEventKind,
    AuditReceipt,
    AuditRecordBinding,
    AuditVerifyRequest,
    AuditVerifyResult,
    PolicyOutcome,
    VerificationState,
)
from abc2lab_contracts.execution import (
    AttemptResult,
    ExecuteRequest,
    ExecutionRequest,
    PolicyDecision,
    PolicyDecisionContent,
    PolicyDecisionResult,
    PolicyInput,
    PrepareResult,
)
from abc2lab_contracts.fingerprint import (
    policy_decision_content_fingerprint,
    policy_decision_fingerprint,
    policy_input_fingerprint,
)
from abc2lab_contracts.ports import AuditVerifier, GatewayPort, PolicyPort
from abc2lab_contracts.primitives import CaptureStatus, ReasonCode, ResultStatus, SendStatus


class _ScriptedPolicy:
    """사전 지정한 결정의 저장 전·후 생성 순서만 재생한다."""

    def __init__(
        self,
        content: PolicyDecisionContent,
        trace: list[str],
        verification: VerificationState,
    ) -> None:
        self.content = content
        self.trace = trace
        self.verification = verification
        self.journal: dict[str, PolicyDecision] = {}

    async def evaluate(self, request: PolicyInput) -> PolicyDecisionResult:
        self.trace.append("evaluate")
        assert policy_input_fingerprint(request) == self.content.evaluated_view_fingerprint
        # 영수증을 꾸며 넣은 최종 객체 없이 먼저 내용의 fingerprint를 계산한다.
        digest = policy_decision_content_fingerprint(self.content)
        binding = AuditRecordBinding(
            event_kind=AuditEventKind.POLICY_DECISION,
            record_ref=self.content.decision_ref,
            record_revision=1,
            record_fingerprint=digest,
            request_ref=request.request_ref,
            attempt_ref=None,
            binding_id=self.content.binding_id,
        )
        receipt = AuditReceipt(
            request.run_key, "policy-demo", "event-decision", 1, binding, self.content.issued_at
        )
        decision = PolicyDecision.from_content(self.content, receipt)
        self.journal[receipt.event_ref] = decision
        self.trace.append("memory_commit")
        return PolicyDecisionResult(request.run_key, ResultStatus.COMPLETE, decision, ())

    async def verify_committed(self, request: AuditVerifyRequest) -> AuditVerifyResult:
        self.trace.append("verify_committed")
        if self.verification is VerificationState.UNKNOWN:
            return AuditVerifyResult(
                request.run_key,
                VerificationState.UNKNOWN,
                (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,),
            )
        stored = self.journal.get(request.receipt.event_ref)
        state = VerificationState.INVALID
        # expected는 호출자가 독립 계산한 값이며 receipt.binding을 복사하지 않는다.
        if (
            stored is not None
            and stored.run_key == request.run_key
            and stored.audit_receipt == request.receipt
            and stored.audit_receipt.binding == request.expected
            and policy_decision_fingerprint(stored) == request.expected.record_fingerprint
        ):
            state = VerificationState.VERIFIED
        return AuditVerifyResult(request.run_key, state, ())


class _ScriptedGateway:
    """포트 연결과 결과 보존만 확인하며 대상 통신 기능은 없다."""

    def __init__(
        self,
        view: PolicyInput,
        verifier: AuditVerifier,
        trace: list[str],
        send_status: SendStatus,
    ) -> None:
        self.view = view
        self.verifier = verifier
        self.trace = trace
        self.send_status = send_status
        self.simulated_transport_entries = 0

    async def prepare(self, request: ExecutionRequest) -> PrepareResult:
        self.trace.append("prepare")
        assert request.run_key == self.view.run_key
        assert request.request_ref == self.view.request_ref
        return PrepareResult(request.run_key, ResultStatus.COMPLETE, "prepared-demo", self.view, ())

    async def execute(self, request: ExecuteRequest) -> AttemptResult:
        self.trace.append("execute")
        decision = request.decision
        status = SendStatus.NOT_SENT
        reasons: tuple[ReasonCode, ...] = (ReasonCode.POLICY_BLOCKED,)
        if decision is not None and decision.outcome is PolicyOutcome.ALLOW:
            expected = AuditRecordBinding(
                event_kind=AuditEventKind.POLICY_DECISION,
                record_ref=decision.decision_ref,
                record_revision=1,
                record_fingerprint=policy_decision_fingerprint(decision),
                request_ref=self.view.request_ref,
                attempt_ref=None,
                binding_id=decision.binding_id,
            )
            verified = await self.verifier.verify_committed(
                AuditVerifyRequest(request.run_key, decision.audit_receipt, expected)
            )
            reasons = (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,)
            if verified.state is VerificationState.VERIFIED:
                self.simulated_transport_entries += 1
                self.trace.append("simulated_transport")
                status = self.send_status
                reasons = (
                    (ReasonCode.SEND_ACKNOWLEDGEMENT_LOST,)
                    if status is SendStatus.UNKNOWN
                    else (ReasonCode.CAPTURE_UNAVAILABLE,)
                )
        captures = {
            SendStatus.SENT: CaptureStatus.UNAVAILABLE,
            SendStatus.NOT_SENT: CaptureStatus.NOT_APPLICABLE,
            SendStatus.UNKNOWN: CaptureStatus.INDETERMINATE,
        }
        return AttemptResult(
            run_key=request.run_key,
            request_ref=request.request_ref,
            attempt_ref="attempt-demo",
            decision_ref=decision.decision_ref if decision is not None else None,
            binding_id=decision.binding_id if decision is not None else None,
            send_status=status,
            capture_status=captures[status],
            capture_ref=None,
            auth_signal=None,
            audit_links=(),
            reason_codes=reasons,
        )


async def _consume_once(
    request: ExecutionRequest, gateway: GatewayPort, policy: PolicyPort
) -> AttemptResult:
    prepared = await gateway.prepare(request)
    assert prepared.policy_input is not None
    assert prepared.prepared_handle is not None
    evaluated = await policy.evaluate(prepared.policy_input)
    return await gateway.execute(
        ExecuteRequest(
            request.run_key, request.request_ref, prepared.prepared_handle, evaluated.decision
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "verification", "scripted_send", "expected_send", "entries"),
    [
        (PolicyOutcome.ALLOW, VerificationState.VERIFIED, SendStatus.SENT, SendStatus.SENT, 1),
        (PolicyOutcome.BLOCK, VerificationState.VERIFIED, SendStatus.SENT, SendStatus.NOT_SENT, 0),
        (PolicyOutcome.ALLOW, VerificationState.UNKNOWN, SendStatus.SENT, SendStatus.NOT_SENT, 0),
        (
            PolicyOutcome.ALLOW,
            VerificationState.VERIFIED,
            SendStatus.UNKNOWN,
            SendStatus.UNKNOWN,
            1,
        ),
    ],
)
async def test_no_io_prepare_evaluate_execute(
    execution_request: ExecutionRequest,
    policy_input: PolicyInput,
    decision_content: PolicyDecisionContent,
    outcome: PolicyOutcome,
    verification: VerificationState,
    scripted_send: SendStatus,
    expected_send: SendStatus,
    entries: int,
) -> None:
    """차단·감사 미확인·전송 불명을 자동 재시도 없이 그대로 보존한다."""
    trace: list[str] = []
    policy = _ScriptedPolicy(replace(decision_content, outcome=outcome), trace, verification)
    gateway = _ScriptedGateway(policy_input, policy, trace, scripted_send)

    result = await _consume_once(execution_request, gateway, policy)

    assert result.send_status is expected_send
    assert result.request_ref == execution_request.request_ref
    assert gateway.simulated_transport_entries == entries
    assert trace[:4] == ["prepare", "evaluate", "memory_commit", "execute"]
    assert trace.count("execute") == 1
    assert trace.count("simulated_transport") == entries
    if verification is VerificationState.UNKNOWN:
        assert ReasonCode.AUDIT_VERIFICATION_UNKNOWN in result.reason_codes
    if expected_send is SendStatus.UNKNOWN:
        assert ReasonCode.SEND_ACKNOWLEDGEMENT_LOST in result.reason_codes


@pytest.mark.asyncio
async def test_receipt_cannot_turn_a_stored_block_into_allow(
    policy_input: PolicyInput, decision_content: PolicyDecisionContent
) -> None:
    """동일 영수증에 allow 필드만 덧씌워도 독립 업무 fingerprint 대조에 실패한다."""
    policy = _ScriptedPolicy(
        replace(decision_content, outcome=PolicyOutcome.BLOCK), [], VerificationState.VERIFIED
    )
    result = await policy.evaluate(policy_input)
    assert result.decision is not None
    forged = replace(result.decision, outcome=PolicyOutcome.ALLOW)
    expected = AuditRecordBinding(
        AuditEventKind.POLICY_DECISION,
        forged.decision_ref,
        1,
        policy_decision_fingerprint(forged),
        policy_input.request_ref,
        None,
        forged.binding_id,
    )
    verified = await policy.verify_committed(
        AuditVerifyRequest(forged.run_key, forged.audit_receipt, expected)
    )
    assert verified.state is VerificationState.INVALID
