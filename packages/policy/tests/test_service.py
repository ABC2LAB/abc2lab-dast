"""`PolicyService`(PolicyPort 구현)의 단위 테스트. 네트워크·DB 없이 실행한다."""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from itertools import count

import pytest
from abc2lab_contracts.audit import (
    AuditReceipt,
    AuditRecordBinding,
    AuditVerifyRequest,
    AuditVerifyResult,
    PolicyOutcome,
    VerificationState,
)
from abc2lab_contracts.execution import (
    PolicyDecision,
    PolicyDecisionContent,
    PolicyIdentityStatus,
    PolicyInput,
)
from abc2lab_contracts.fingerprint import policy_decision_fingerprint, policy_input_fingerprint
from abc2lab_contracts.ports import PolicyPort
from abc2lab_contracts.primitives import ReasonCode, Ref, ResultStatus, RunKey
from abc2lab_contracts.registration import CrossExecutionConfirmation
from abc2lab_policy.adapters import (
    InMemoryPolicyDecisionJournal,
    InMemoryPolicyRegistrations,
    JournalCommitError,
    PolicyRegistration,
    PolicyService,
)

type GatewayExpected = Callable[[PolicyDecision, Ref], AuditRecordBinding]


class _FailingJournal(InMemoryPolicyDecisionJournal):
    """commit을 확인하지 못하는 journal."""

    async def append(self, content: PolicyDecisionContent, request_ref: Ref) -> AuditReceipt:
        raise JournalCommitError("store unavailable")


class _InvalidVerificationJournal(InMemoryPolicyDecisionJournal):
    """저장 기록이 손상돼 검증이 INVALID를 돌려주는 journal(저장소 내부는 건드리지 않는다)."""

    async def verify_committed(self, request: AuditVerifyRequest) -> AuditVerifyResult:
        return AuditVerifyResult(
            request.run_key, VerificationState.INVALID, (ReasonCode.SOURCE_UNVERIFIED,)
        )


class _UnknownVerificationJournal(InMemoryPolicyDecisionJournal):
    """저장 기록을 조회할 수 없는 journal."""

    async def verify_committed(self, request: AuditVerifyRequest) -> AuditVerifyResult:
        return AuditVerifyResult(
            request.run_key, VerificationState.UNKNOWN, (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,)
        )


class _ForeignReceiptJournal(InMemoryPolicyDecisionJournal):
    """다른 요청의 binding을 담은 영수증을 돌려주고 검증도 무조건 통과시키는 journal."""

    async def append(self, content: PolicyDecisionContent, request_ref: Ref) -> AuditReceipt:
        receipt = await super().append(content, request_ref)
        return replace(receipt, binding=replace(receipt.binding, request_ref="other-request"))

    async def verify_committed(self, request: AuditVerifyRequest) -> AuditVerifyResult:
        return AuditVerifyResult(request.run_key, VerificationState.VERIFIED, ())


class _CancelledJournal(InMemoryPolicyDecisionJournal):
    """commit 중 작업이 취소되는 journal."""

    async def append(self, content: PolicyDecisionContent, request_ref: Ref) -> AuditReceipt:
        raise asyncio.CancelledError


def _service(
    registration: PolicyRegistration,
    run_key: RunKey,
    journal: InMemoryPolicyDecisionJournal,
    now: datetime,
) -> tuple[PolicyService, InMemoryPolicyRegistrations]:
    """고정 시계와 결정적 참조로 서비스를 만든다."""
    registrations = InMemoryPolicyRegistrations()
    registrations.register(run_key, registration)
    refs = count(1)
    service = PolicyService(
        registrations,
        journal,
        clock=lambda: now,
        decision_ref_factory=lambda: f"decision-{next(refs)}",
    )
    return service, registrations


def _journal(now: datetime) -> InMemoryPolicyDecisionJournal:
    return InMemoryPolicyDecisionJournal("policy", clock=lambda: now)


def test_service_satisfies_policy_port(
    registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    service, _ = _service(registration, run_key, _journal(now), now)
    port: PolicyPort = service
    assert port is service


@pytest.mark.asyncio
async def test_allow_is_committed_and_verifiable_by_gateway(
    policy_input: PolicyInput,
    registration: PolicyRegistration,
    run_key: RunKey,
    now: datetime,
    gateway_expected: GatewayExpected,
) -> None:
    journal = _journal(now)
    service, _ = _service(registration, run_key, journal, now)

    result = await service.evaluate(policy_input)

    assert result.status is ResultStatus.COMPLETE
    assert result.reason_codes == ()
    decision = result.decision
    assert decision is not None
    assert decision.outcome is PolicyOutcome.ALLOW
    assert decision.reason_codes == ()
    assert decision.binding_id == policy_input.binding_id
    assert decision.evaluated_view_fingerprint == policy_input_fingerprint(policy_input)
    # 다른 모듈(Gateway)이 받은 결정만으로 독립 계산한 expected가 같은 journal에서 검증된다.
    verified = await journal.verify_committed(
        AuditVerifyRequest(
            run_key, decision.audit_receipt, gateway_expected(decision, policy_input.request_ref)
        )
    )
    assert verified.state is VerificationState.VERIFIED
    assert len(journal.committed(run_key)) == 1


@pytest.mark.asyncio
async def test_allow_decision_expires_with_view(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    service, _ = _service(registration, run_key, _journal(now), now)
    decision = (await service.evaluate(policy_input)).decision
    assert decision is not None
    assert decision.issued_at == now
    # view 만료(10분)가 구성 만료(1시간)보다 이르므로 결정은 view보다 오래 유효하지 않다.
    assert decision.expires_at == policy_input.expires_at


@pytest.mark.asyncio
async def test_block_is_committed_as_complete_decision(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    journal = _journal(now)
    service, _ = _service(replace(registration, is_revoked=True), run_key, journal, now)

    result = await service.evaluate(policy_input)

    assert result.status is ResultStatus.COMPLETE
    assert result.decision is not None
    assert result.decision.outcome is PolicyOutcome.BLOCK
    assert result.decision.reason_codes == (ReasonCode.POLICY_BLOCKED,)
    assert len(journal.committed(run_key)) == 1


@pytest.mark.asyncio
async def test_expired_view_block_keeps_increasing_interval(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    service, _ = _service(registration, run_key, _journal(now), now)
    decision = (await service.evaluate(replace(policy_input, expires_at=now))).decision
    assert decision is not None
    assert decision.outcome is PolicyOutcome.BLOCK
    assert decision.reason_codes == (ReasonCode.SNAPSHOT_EXPIRED,)
    assert decision.issued_at < decision.expires_at <= now + timedelta(seconds=1)


@pytest.mark.asyncio
async def test_missing_registration_fails_without_commit(
    policy_input: PolicyInput, run_key: RunKey, now: datetime
) -> None:
    journal = _journal(now)
    service = PolicyService(InMemoryPolicyRegistrations(), journal, clock=lambda: now)

    result = await service.evaluate(policy_input)

    assert result.status is ResultStatus.FAILED
    assert result.decision is None
    assert result.reason_codes == (ReasonCode.CONFIGURATION_MISSING,)
    assert journal.committed(run_key) == ()


@pytest.mark.asyncio
async def test_store_failure_returns_no_decision(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    service, _ = _service(registration, run_key, _FailingJournal("policy"), now)

    result = await service.evaluate(policy_input)

    assert result.status is ResultStatus.FAILED
    assert result.decision is None
    assert result.reason_codes == (ReasonCode.AUDIT_COMMIT_FAILED,)


@pytest.mark.asyncio
async def test_invalid_verification_returns_no_decision(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    # 평가는 allow지만 저장 기록이 검증에서 INVALID면 allow를 발급하지 않는다.
    service, _ = _service(registration, run_key, _InvalidVerificationJournal("policy"), now)

    result = await service.evaluate(policy_input)

    assert result.status is ResultStatus.FAILED
    assert result.decision is None
    assert result.reason_codes == (ReasonCode.AUDIT_COMMIT_FAILED, ReasonCode.SOURCE_UNVERIFIED)


@pytest.mark.asyncio
async def test_unknown_verification_returns_no_decision(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    service, _ = _service(registration, run_key, _UnknownVerificationJournal("policy"), now)

    result = await service.evaluate(policy_input)

    assert result.status is ResultStatus.FAILED
    assert result.decision is None
    assert result.reason_codes == (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,)


@pytest.mark.asyncio
async def test_foreign_receipt_is_rejected_even_if_verifier_passes(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    # 검증기가 잘못 통과시켜도, 영수증 binding이 이 결정에서 계산한 값과 다르면 발급하지 않는다.
    service, _ = _service(registration, run_key, _ForeignReceiptJournal("policy"), now)

    result = await service.evaluate(policy_input)

    assert result.status is ResultStatus.FAILED
    assert result.decision is None
    assert result.reason_codes == (ReasonCode.AUDIT_COMMIT_FAILED,)


@pytest.mark.asyncio
async def test_cancellation_during_commit_propagates(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    service, _ = _service(registration, run_key, _CancelledJournal("policy"), now)
    with pytest.raises(asyncio.CancelledError):
        await service.evaluate(policy_input)


@pytest.mark.asyncio
async def test_reevaluation_commits_a_fresh_decision(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    journal = _journal(now)
    service, _ = _service(registration, run_key, journal, now)

    first = (await service.evaluate(policy_input)).decision
    second = (await service.evaluate(policy_input)).decision

    assert first is not None and second is not None
    assert first.decision_ref != second.decision_ref
    assert first.outcome is second.outcome is PolicyOutcome.ALLOW
    assert first.evaluated_view_fingerprint == second.evaluated_view_fingerprint
    assert [entry.receipt.sequence for entry in journal.committed(run_key)] == [1, 2]


@pytest.mark.asyncio
async def test_reevaluation_after_revocation_does_not_reuse_allow(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    service, registrations = _service(registration, run_key, _journal(now), now)

    first = (await service.evaluate(policy_input)).decision
    registrations.register(run_key, replace(registration, is_revoked=True))
    second = (await service.evaluate(policy_input)).decision

    assert first is not None and second is not None
    assert first.outcome is PolicyOutcome.ALLOW
    assert second.outcome is PolicyOutcome.BLOCK
    assert second.reason_codes == (ReasonCode.POLICY_BLOCKED,)


@pytest.mark.asyncio
async def test_decision_fingerprint_is_deterministic(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    decisions: list[PolicyDecision] = []
    for _ in range(2):
        service, _ = _service(registration, run_key, _journal(now), now)
        decision = (await service.evaluate(policy_input)).decision
        assert decision is not None
        decisions.append(decision)

    first, second = decisions
    assert first == second
    assert policy_decision_fingerprint(first) == policy_decision_fingerprint(second)
    # 커밋된 결정의 fingerprint는 commit 전 내용 fingerprint(영수증 binding)와 같다.
    assert policy_decision_fingerprint(first) == first.audit_receipt.binding.record_fingerprint


@pytest.mark.asyncio
async def test_cross_execution_allow_is_committed_and_verifiable(
    cross_policy_input: PolicyInput,
    cross_registration: PolicyRegistration,
    run_key: RunKey,
    now: datetime,
    gateway_expected: GatewayExpected,
) -> None:
    journal = _journal(now)
    service, _ = _service(cross_registration, run_key, journal, now)

    result = await service.evaluate(cross_policy_input)

    assert result.status is ResultStatus.COMPLETE
    decision = result.decision
    assert decision is not None
    assert decision.outcome is PolicyOutcome.ALLOW
    assert decision.reason_codes == ()
    verified = await journal.verify_committed(
        AuditVerifyRequest(
            run_key,
            decision.audit_receipt,
            gateway_expected(decision, cross_policy_input.request_ref),
        )
    )
    assert verified.state is VerificationState.VERIFIED


@pytest.mark.asyncio
async def test_view_scope_mismatch_is_blocked(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    # view의 scope가 주입 원본과 다르면(코어는 주입 원본으로 허용해도) block을 commit한다.
    tampered = replace(
        policy_input, scope=replace(policy_input.scope, allowed_origins=("https://evil.test",))
    )
    service, _ = _service(registration, run_key, _journal(now), now)

    result = await service.evaluate(tampered)

    assert result.status is ResultStatus.COMPLETE
    assert result.decision is not None
    assert result.decision.outcome is PolicyOutcome.BLOCK
    assert result.decision.reason_codes == (ReasonCode.POLICY_VIEW_MISMATCH,)


@pytest.mark.asyncio
async def test_cross_forged_confirmation_is_blocked(
    cross_policy_input: PolicyInput,
    cross_registration: PolicyRegistration,
    cross_confirmation: CrossExecutionConfirmation,
    run_key: RunKey,
    now: datetime,
) -> None:
    # 등록되지 않은(위조) 확인을 붙이면 commit·검증된 allow 대신 block을 commit한다.
    forged = replace(cross_confirmation, evaluated_account_ref="acct-c")
    request = replace(cross_policy_input, cross_confirmation=forged)
    service, _ = _service(cross_registration, run_key, _journal(now), now)

    result = await service.evaluate(request)

    assert result.status is ResultStatus.COMPLETE
    assert result.decision is not None
    assert result.decision.outcome is PolicyOutcome.BLOCK
    assert result.decision.reason_codes == (
        ReasonCode.CROSS_CONFIRMATION_MISSING,
        ReasonCode.POLICY_VIEW_MISMATCH,
    )


@pytest.mark.asyncio
async def test_view_mismatch_reason_survives_core_block(
    policy_input: PolicyInput, registration: PolicyRegistration, run_key: RunKey, now: datetime
) -> None:
    # scope 변조 + 코어도 block(미검증 신원)이면 변조 사유가 결정 reason에 남는다.
    tampered = replace(
        policy_input,
        scope=replace(policy_input.scope, allowed_origins=("https://evil.test",)),
        identity_status=PolicyIdentityStatus.UNKNOWN,
    )
    service, _ = _service(registration, run_key, _journal(now), now)

    result = await service.evaluate(tampered)

    assert result.status is ResultStatus.COMPLETE
    assert result.decision is not None
    assert result.decision.outcome is PolicyOutcome.BLOCK
    assert ReasonCode.POLICY_VIEW_MISMATCH in result.decision.reason_codes
    assert ReasonCode.IDENTITY_UNKNOWN in result.decision.reason_codes


@pytest.mark.asyncio
async def test_cross_decision_expiry_capped_by_confirmation(
    cross_policy_input: PolicyInput,
    cross_registration: PolicyRegistration,
    cross_confirmation: CrossExecutionConfirmation,
    run_key: RunKey,
    now: datetime,
) -> None:
    # 확인이 view보다 먼저 만료되면 결정 만료 = 확인 만료.
    short_confirmation = replace(cross_confirmation, valid_until=now + timedelta(minutes=5))
    request = replace(cross_policy_input, cross_confirmation=short_confirmation)
    registration = replace(cross_registration, cross_confirmations=(short_confirmation,))
    service, _ = _service(registration, run_key, _journal(now), now)

    result = await service.evaluate(request)

    assert result.status is ResultStatus.COMPLETE
    assert result.decision is not None
    assert result.decision.outcome is PolicyOutcome.ALLOW
    assert result.decision.expires_at == short_confirmation.valid_until
