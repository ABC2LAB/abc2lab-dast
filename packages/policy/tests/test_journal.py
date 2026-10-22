"""정책 결정 메모리 journal의 단위 테스트. 네트워크·DB 없이 실행한다."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from abc2lab_contracts.audit import (
    AuditEventKind,
    AuditRecordBinding,
    AuditVerifyRequest,
    PolicyOutcome,
    VerificationState,
)
from abc2lab_contracts.execution import PolicyDecision, PolicyDecisionContent
from abc2lab_contracts.fingerprint import policy_decision_content_fingerprint
from abc2lab_contracts.ports import AuditVerifier
from abc2lab_contracts.primitives import ReasonCode, Ref, RunKey, SourceVersion
from abc2lab_policy.adapters import (
    InMemoryPolicyDecisionJournal,
    JournalCommitError,
    PolicyDecisionJournal,
)

type GatewayExpected = Callable[[PolicyDecision, Ref], AuditRecordBinding]


@pytest.fixture
def content(now: datetime, run_key: RunKey, source: SourceVersion) -> PolicyDecisionContent:
    return PolicyDecisionContent(
        run_key=run_key,
        decision_ref="decision-1",
        binding_id="binding-1",
        evaluated_view_fingerprint="a" * 64,
        outcome=PolicyOutcome.ALLOW,
        policy_version=source,
        issued_at=now,
        expires_at=now + timedelta(minutes=10),
        reason_codes=(),
    )


@pytest.fixture
def journal(now: datetime) -> InMemoryPolicyDecisionJournal:
    return InMemoryPolicyDecisionJournal("policy", clock=lambda: now)


def test_journal_serves_both_policy_and_audit_ports(
    journal: InMemoryPolicyDecisionJournal,
) -> None:
    policy_journal: PolicyDecisionJournal = journal
    verifier: AuditVerifier = journal
    assert policy_journal is verifier


@pytest.mark.asyncio
async def test_append_issues_receipt_bound_to_content(
    journal: InMemoryPolicyDecisionJournal, content: PolicyDecisionContent, now: datetime
) -> None:
    receipt = await journal.append(content, "request-1")
    assert receipt.run_key == content.run_key
    assert receipt.producer == "policy"
    assert receipt.sequence == 1
    assert receipt.committed_at == now
    assert receipt.binding == AuditRecordBinding(
        event_kind=AuditEventKind.POLICY_DECISION,
        record_ref="decision-1",
        record_revision=1,
        record_fingerprint=policy_decision_content_fingerprint(content),
        request_ref="request-1",
        attempt_ref=None,
        binding_id="binding-1",
    )


@pytest.mark.asyncio
async def test_sequence_starts_at_one_and_increments_per_run(
    journal: InMemoryPolicyDecisionJournal, content: PolicyDecisionContent, run_key: RunKey
) -> None:
    first = await journal.append(content, "request-1")
    second = await journal.append(replace(content, decision_ref="decision-2"), "request-2")
    other_run = await journal.append(
        replace(content, run_key=replace(run_key, run_ref="run-2")), "request-1"
    )
    assert (first.sequence, second.sequence, other_run.sequence) == (1, 2, 1)
    assert [entry.receipt for entry in journal.committed(run_key)] == [first, second]


@pytest.mark.asyncio
async def test_same_content_recommit_returns_existing_receipt(
    journal: InMemoryPolicyDecisionJournal, content: PolicyDecisionContent, run_key: RunKey
) -> None:
    first = await journal.append(content, "request-1")
    again = await journal.append(content, "request-1")
    assert again == first
    assert len(journal.committed(run_key)) == 1


@pytest.mark.asyncio
async def test_conflicting_recommit_is_idempotency_conflict(
    journal: InMemoryPolicyDecisionJournal, content: PolicyDecisionContent, run_key: RunKey
) -> None:
    await journal.append(content, "request-1")
    with pytest.raises(JournalCommitError) as raised:
        await journal.append(replace(content, outcome=PolicyOutcome.BLOCK), "request-1")
    assert raised.value.reason_code is ReasonCode.IDEMPOTENCY_CONFLICT
    assert len(journal.committed(run_key)) == 1


@pytest.mark.asyncio
async def test_gateway_style_expected_is_verified(
    journal: InMemoryPolicyDecisionJournal,
    content: PolicyDecisionContent,
    gateway_expected: GatewayExpected,
) -> None:
    receipt = await journal.append(content, "request-1")
    decision = PolicyDecision.from_content(content, receipt)
    result = await journal.verify_committed(
        AuditVerifyRequest(decision.run_key, receipt, gateway_expected(decision, "request-1"))
    )
    assert result.state is VerificationState.VERIFIED


@pytest.mark.asyncio
async def test_forged_allow_over_stored_block_is_invalid(
    journal: InMemoryPolicyDecisionJournal,
    content: PolicyDecisionContent,
    gateway_expected: GatewayExpected,
) -> None:
    # S1-16: 실제 block 기록의 영수증에 allow만 덧씌워도 독립 fingerprint 대조에 실패한다.
    block = replace(content, outcome=PolicyOutcome.BLOCK, reason_codes=(ReasonCode.POLICY_BLOCKED,))
    receipt = await journal.append(block, "request-1")
    forged = replace(
        PolicyDecision.from_content(block, receipt), outcome=PolicyOutcome.ALLOW, reason_codes=()
    )
    result = await journal.verify_committed(
        AuditVerifyRequest(forged.run_key, receipt, gateway_expected(forged, "request-1"))
    )
    assert result.state is VerificationState.INVALID
    assert result.reason_codes == (ReasonCode.SOURCE_UNVERIFIED,)


@pytest.mark.asyncio
async def test_receipt_for_uncommitted_event_is_invalid(
    journal: InMemoryPolicyDecisionJournal,
    content: PolicyDecisionContent,
    gateway_expected: GatewayExpected,
) -> None:
    receipt = replace(await journal.append(content, "request-1"), event_ref="policy:run-1:99")
    decision = PolicyDecision.from_content(content, receipt)
    result = await journal.verify_committed(
        AuditVerifyRequest(decision.run_key, receipt, gateway_expected(decision, "request-1"))
    )
    assert result.state is VerificationState.INVALID


@pytest.mark.asyncio
async def test_verification_for_other_run_is_invalid(
    journal: InMemoryPolicyDecisionJournal,
    content: PolicyDecisionContent,
    run_key: RunKey,
    gateway_expected: GatewayExpected,
) -> None:
    receipt = await journal.append(content, "request-1")
    decision = PolicyDecision.from_content(content, receipt)
    result = await journal.verify_committed(
        AuditVerifyRequest(
            replace(run_key, run_ref="run-2"), receipt, gateway_expected(decision, "request-1")
        )
    )
    assert result.state is VerificationState.INVALID


@pytest.mark.asyncio
async def test_expected_bound_to_other_request_is_invalid(
    journal: InMemoryPolicyDecisionJournal,
    content: PolicyDecisionContent,
    gateway_expected: GatewayExpected,
) -> None:
    receipt = await journal.append(content, "request-1")
    decision = PolicyDecision.from_content(content, receipt)
    result = await journal.verify_committed(
        AuditVerifyRequest(decision.run_key, receipt, gateway_expected(decision, "request-2"))
    )
    assert result.state is VerificationState.INVALID
