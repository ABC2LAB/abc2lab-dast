"""`JudgeService`(JudgePort 제공자) 테스트. 로컬 fake만 쓰고 네트워크·DB 없이 실행한다."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import pytest
from abc2lab_contracts.audit import (
    AuditEvent,
    AuditEventKind,
    AuditPage,
    AuditReadRequest,
    AuditReceipt,
    AuditRecordBinding,
    AuditVerifyRequest,
    AuditVerifyResult,
    VerificationState,
)
from abc2lab_contracts.evidence import (
    ArtifactKind,
    ComparisonPayload,
    ComparisonSignals,
    EvidenceReadRequest,
    EvidenceReadResult,
    EvidenceSummary,
    RedactedBundle,
    StoredComparison,
    StoreOutcome,
    StoreReceipt,
)
from abc2lab_contracts.fingerprint import (
    comparison_fingerprint,
    evidence_fingerprint,
    identity_content_fingerprint,
)
from abc2lab_contracts.judge import (
    JudgePolicyReadRequest,
    JudgePolicyReadResult,
    JudgeRequest,
    JudgeResult,
)
from abc2lab_contracts.primitives import (
    AuditLink,
    CheckState,
    ReadContext,
    ReasonCode,
    Ref,
    ResponseClass,
    ResultStatus,
    RunKey,
    SendStatus,
    SourceVersion,
)
from abc2lab_contracts.reason_codes import CALL_AUDIT_FAILURE_REASON_CODES
from abc2lab_contracts.registration import (
    ComparisonRules,
    ExpectedAccess,
    ExpectedAccessPolicySnapshot,
    ResolutionState,
)
from abc2lab_contracts.session import IdentityContent, IdentityResult, IdentityStatus
from abc2lab_contracts.verdict import Verdict, VerdictValue
from abc2lab_judge.adapters import (
    AuditSource,
    InMemoryVerdictJournal,
    JudgeDependencies,
    JudgeService,
    JudgeSettings,
)

T = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
OWNER_AT = T - timedelta(minutes=10)
CROSS_AT = T - timedelta(minutes=5)
RUN = RunKey("org-1", "target-1", "env-1", "run-1")
CTX = ReadContext("caller-1", "authz-1")
RULES = ComparisonRules(SourceVersion("judge", "rules", 1), "normalizer-1", "oracle-1", "canary-1")
ORACLE_VERSION = SourceVersion("judge", "idor-oracle", 2)
ATTEMPT_FP = "0123456789abcdef" * 4
OTHER_FP = "fedcba9876543210" * 4
ATTESTATION_LOGGER = "abc2lab_judge.adapters.attestation"

# ---------------------------------------------------------------- fakes


class FakeAuthorizer:
    def __init__(self) -> None:
        self.allowed = True
        self.calls = 0

    async def authorize(self, run_key: RunKey, context: ReadContext, case_ref: Ref) -> bool:
        self.calls += 1
        return self.allowed


class FakePolicyReader:
    def __init__(
        self, policy: ExpectedAccessPolicySnapshot | None, failure: tuple[ReasonCode, ...] | None
    ) -> None:
        self.policy = policy
        self.failure = failure
        self.requests: list[JudgePolicyReadRequest] = []

    async def read_case_policy(self, request: JudgePolicyReadRequest) -> JudgePolicyReadResult:
        self.requests.append(request)
        run, case = request.run_key, request.case_ref
        if self.failure is not None:
            return JudgePolicyReadResult(run, case, ResultStatus.FAILED, None, self.failure)
        if self.policy is None:
            missing = (ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,)
            return JudgePolicyReadResult(run, case, ResultStatus.COMPLETE, None, missing)
        return JudgePolicyReadResult(run, case, ResultStatus.COMPLETE, self.policy, ())


class FakeEvidence:
    def __init__(
        self, comparisons: dict[str, StoredComparison], evidence: dict[str, EvidenceSummary]
    ) -> None:
        self.comparisons = comparisons
        self.evidence = evidence
        self.requests: list[EvidenceReadRequest] = []
        self.gate: asyncio.Event | None = None

    async def store_evidence(self, request: RedactedBundle) -> StoreOutcome:
        raise AssertionError("judge must not write Evidence")

    async def evidence_read_summary(self, request: EvidenceReadRequest) -> EvidenceReadResult:
        self.requests.append(request)
        if self.gate is not None:
            await self.gate.wait()
        evidence = tuple(
            self.evidence[ref] for ref in request.evidence_refs if ref in self.evidence
        )
        comparisons = tuple(
            self.comparisons[ref] for ref in request.comparison_refs if ref in self.comparisons
        )
        return EvidenceReadResult(request.run_key, ResultStatus.COMPLETE, evidence, comparisons, ())


class FakeAuditReader:
    def __init__(self, producer: Ref, events: list[AuditEvent], page_size: int) -> None:
        self.producer = producer
        self.events = events
        self.page_size = page_size
        self.failure: tuple[ReasonCode, ...] | None = None

    async def read_audit(self, request: AuditReadRequest) -> AuditPage:
        if self.failure is not None:
            return AuditPage(
                request.run_key,
                ResultStatus.FAILED,
                self.producer,
                (),
                None,
                None,
                None,
                None,
                None,
                self.failure,
            )
        start = int(request.cursor) if request.cursor is not None else 0
        end = start + self.page_size
        next_cursor = str(end) if end < len(self.events) else None
        last = self.events[-1].receipt.sequence if self.events else 0
        return AuditPage(
            request.run_key,
            ResultStatus.COMPLETE,
            self.producer,
            tuple(self.events[start:end]),
            next_cursor,
            "snapshot-1",
            1 if self.events else None,
            last,
            None if self.events else 0,
            (),
        )


class FakeVerifier:
    """요청 binding이 실제 receipt와 같아야 VERIFIED. event_ref별로 상태를 바꿀 수 있다."""

    def __init__(self) -> None:
        self.states: dict[str, VerificationState] = {}
        self.requests: list[AuditVerifyRequest] = []

    async def verify_committed(self, request: AuditVerifyRequest) -> AuditVerifyResult:
        self.requests.append(request)
        if request.receipt.binding != request.expected:
            return AuditVerifyResult(request.run_key, VerificationState.INVALID, ())
        state = self.states.get(request.receipt.event_ref, VerificationState.VERIFIED)
        return AuditVerifyResult(request.run_key, state, ())


class StaleRevisionJournal(InMemoryVerdictJournal):
    """동시 선점을 흉내 내려고 최신 revision을 항상 0으로 보고하는 journal."""

    async def latest_revision(self, run_key: RunKey, verdict_ref: Ref) -> int:
        return 0


# ---------------------------------------------------------------- records


def policy_snapshot(
    *,
    access: ExpectedAccess = ExpectedAccess.DENY,
    valid_from: datetime = T - timedelta(hours=2),
    valid_until: datetime = T + timedelta(hours=2),
    policy_ref: str = "policy-1",
    owner_subject: str = "subject-a",
) -> ExpectedAccessPolicySnapshot:
    return ExpectedAccessPolicySnapshot(
        SourceVersion("registration", "policy", 3),
        policy_ref,
        RUN.target_ref,
        RUN.environment_ref,
        "resource-1",
        "operation-1",
        owner_subject,
        "subject-b",
        access,
        ResolutionState.RESOLVED_NONE,
        ResolutionState.RESOLVED_NONE,
        valid_from,
        valid_until,
    )


def identity(
    ref: str,
    subject: str,
    account: str,
    generation: int,
    *,
    valid_until: datetime = T + timedelta(hours=1),
) -> IdentityResult:
    verified_at = T - timedelta(hours=1)
    content = IdentityContent(
        RUN,
        ref,
        IdentityStatus.VERIFIED,
        f"session-{ref}",
        account,
        generation,
        subject,
        f"evidence-{ref}",
        verified_at,
        valid_until,
        (),
        (),
    )
    binding = AuditRecordBinding(
        AuditEventKind.IDENTITY, ref, 1, identity_content_fingerprint(content), None, None, None
    )
    receipt = AuditReceipt(RUN, "webdiag", f"identity-event-{ref}", 1, binding, verified_at)
    return IdentityResult.from_content(content, receipt)


def owner_identity(*, valid_until: datetime = T + timedelta(hours=1)) -> IdentityResult:
    return identity("identity-a", "subject-a", "account-a", 3, valid_until=valid_until)


def evaluated_identity(*, valid_until: datetime = T + timedelta(hours=1)) -> IdentityResult:
    return identity("identity-b", "subject-b", "account-b", 5, valid_until=valid_until)


def all_yes_signals() -> ComparisonSignals:
    yes = CheckState.YES
    return ComparisonSignals(yes, yes, yes, yes, yes, yes, yes)


def summary(side: str, who: IdentityResult, observed_at: datetime) -> EvidenceSummary:
    return EvidenceSummary(
        RUN,
        f"evidence-{side}",
        f"attempt-{side}",
        "operation-1",
        "resource-1",
        who.account_ref,
        who.generation,
        who.identity_ref,
        ResponseClass.NORMAL,
        200,
        observed_at,
        SourceVersion("evidence", "redaction", 1),
        AuditLink("evidence", f"evidence-event-{side}"),
        None,
        (ReasonCode.RECIPE_MISSING,),
    )


def stored(
    payload: ComparisonPayload, owner: EvidenceSummary, cross: EvidenceSummary
) -> StoredComparison:
    source = SourceVersion("evidence", "store", 1)
    return StoredComparison(
        payload,
        (
            StoreReceipt(
                RUN,
                "sub-owner",
                owner.evidence_ref,
                ArtifactKind.EVIDENCE,
                source,
                OWNER_AT,
                evidence_fingerprint(owner),
            ),
            StoreReceipt(
                RUN,
                "sub-cross",
                cross.evidence_ref,
                ArtifactKind.EVIDENCE,
                source,
                CROSS_AT,
                evidence_fingerprint(cross),
            ),
            StoreReceipt(
                RUN,
                "sub-comparison",
                payload.comparison_ref,
                ArtifactKind.COMPARISON,
                source,
                CROSS_AT,
                comparison_fingerprint(payload),
            ),
        ),
    )


def event(
    receipt: AuditReceipt,
    *,
    links: tuple[AuditLink, ...] = (),
    case_ref: str | None = None,
    account: str | None = None,
    generation: int | None = None,
    evidence_refs: tuple[str, ...] = (),
    send: SendStatus | None = None,
    reasons: tuple[ReasonCode, ...] = (),
) -> AuditEvent:
    return AuditEvent(
        receipt,
        links,
        None,
        None,
        case_ref,
        account,
        generation,
        evidence_refs,
        (),
        receipt.committed_at,
        receipt.committed_at,
        "instance-1",
        0,
        None,
        send,
        reasons,
    )


def evidence_event(item: EvidenceSummary, sequence: int, linked: bool) -> AuditEvent:
    binding = AuditRecordBinding(
        AuditEventKind.EVIDENCE,
        item.evidence_ref,
        1,
        evidence_fingerprint(item),
        None,
        item.attempt_ref,
        None,
    )
    receipt = AuditReceipt(
        RUN,
        item.source_event.producer,
        item.source_event.event_ref,
        sequence,
        binding,
        item.observed_at,
    )
    links = (AuditLink("gateway", f"attempt-event-{item.attempt_ref}"),) if linked else ()
    return event(
        receipt,
        links=links,
        account=item.account_ref,
        generation=item.session_generation,
        evidence_refs=(item.evidence_ref,),
    )


def comparison_event(
    payload: ComparisonPayload, owner: EvidenceSummary, cross: EvidenceSummary, sequence: int
) -> AuditEvent:
    binding = AuditRecordBinding(
        AuditEventKind.COMPARISON,
        payload.comparison_ref,
        1,
        comparison_fingerprint(payload),
        None,
        None,
        None,
    )
    receipt = AuditReceipt(RUN, "evidence", "comparison-event-1", sequence, binding, CROSS_AT)
    return event(
        receipt,
        links=(owner.source_event, cross.source_event),
        case_ref=payload.case_ref,
        evidence_refs=(owner.evidence_ref, cross.evidence_ref),
        reasons=(ReasonCode.COMPARISON_CANARY_PASSED,),
    )


def attempt_event(
    attempt_ref: str,
    who: IdentityResult,
    sequence: int,
    *,
    revision: int = 1,
    send: SendStatus = SendStatus.SENT,
    fingerprint: str = ATTEMPT_FP,
) -> AuditEvent:
    binding = AuditRecordBinding(
        AuditEventKind.ATTEMPT,
        attempt_ref,
        revision,
        fingerprint,
        f"request-{attempt_ref}",
        attempt_ref,
        None,
    )
    receipt = AuditReceipt(
        RUN, "gateway", f"attempt-event-{attempt_ref}", sequence, binding, OWNER_AT
    )
    return event(receipt, account=who.account_ref, generation=who.generation, send=send)


# ---------------------------------------------------------------- scenario


@dataclass
class Harness:
    service: JudgeService
    journal: InMemoryVerdictJournal
    authorizer: FakeAuthorizer
    policy_reader: FakePolicyReader
    evidence: FakeEvidence
    evidence_reader: FakeAuditReader
    gateway_reader: FakeAuditReader
    evidence_verifier: FakeVerifier
    gateway_verifier: FakeVerifier
    webdiag_verifier: FakeVerifier
    request: JudgeRequest


@dataclass
class Scenario:
    policy: ExpectedAccessPolicySnapshot | None = field(default_factory=policy_snapshot)
    policy_failure: tuple[ReasonCode, ...] | None = None
    hint: ExpectedAccessPolicySnapshot | None = None
    owner: IdentityResult | None = field(default_factory=owner_identity)
    evaluated: IdentityResult | None = field(default_factory=evaluated_identity)
    request_owner: IdentityResult | None = None
    signals: ComparisonSignals = field(default_factory=all_yes_signals)
    rules: ComparisonRules = RULES
    with_comparison: bool = True
    link_attempts: bool = True
    cross_send: SendStatus = SendStatus.SENT
    extra_gateway_events: list[AuditEvent] = field(default_factory=list)
    page_size: int = 100
    max_pages: int = 20
    journal_type: type[InMemoryVerdictJournal] = InMemoryVerdictJournal
    submission_ref: str = "submission-1"

    def build(self) -> Harness:
        comparisons: dict[str, StoredComparison] = {}
        evidence_by_ref: dict[str, EvidenceSummary] = {}
        evidence_events: list[AuditEvent] = []
        gateway_events: list[AuditEvent] = []
        if self.with_comparison:
            assert self.owner is not None and self.evaluated is not None
            owner = summary("owner", self.owner, OWNER_AT)
            cross = summary("cross", self.evaluated, CROSS_AT)
            payload = ComparisonPayload(
                RUN,
                "comparison-1",
                "case-1",
                "resource-1",
                "operation-1",
                owner.evidence_ref,
                cross.evidence_ref,
                _ref(owner.identity_ref),
                _ref(cross.identity_ref),
                self.signals,
                self.rules,
            )
            comparisons[payload.comparison_ref] = stored(payload, owner, cross)
            evidence_by_ref = {owner.evidence_ref: owner, cross.evidence_ref: cross}
            evidence_events = [
                evidence_event(owner, 1, self.link_attempts),
                evidence_event(cross, 2, self.link_attempts),
                comparison_event(payload, owner, cross, 3),
            ]
            gateway_events = [
                attempt_event(owner.attempt_ref, self.owner, 1),
                attempt_event(cross.attempt_ref, self.evaluated, 2, send=self.cross_send),
                *self.extra_gateway_events,
            ]
        authorizer = FakeAuthorizer()
        policy_reader = FakePolicyReader(self.policy, self.policy_failure)
        evidence = FakeEvidence(comparisons, evidence_by_ref)
        evidence_reader = FakeAuditReader("evidence", evidence_events, self.page_size)
        gateway_reader = FakeAuditReader("gateway", gateway_events, self.page_size)
        verifiers = FakeVerifier(), FakeVerifier(), FakeVerifier()
        journal = self.journal_type("judge", clock=lambda: T + timedelta(seconds=1))
        service = JudgeService(
            JudgeDependencies(
                authorizer=authorizer,
                policy_reader=policy_reader,
                evidence=evidence,
                evidence_audit=AuditSource("evidence", evidence_reader, verifiers[0]),
                gateway_audit=AuditSource("gateway", gateway_reader, verifiers[1]),
                webdiag_verifier=verifiers[2],
                journal=journal,
                clock=lambda: T,
            ),
            JudgeSettings(
                producer="judge",
                webdiag_producer="webdiag",
                oracle_version=ORACLE_VERSION,
                comparison_rules=RULES,
                audit_max_pages=self.max_pages,
            ),
        )
        request = JudgeRequest(
            RUN,
            CTX,
            "case-1",
            self.submission_ref,
            self.hint,
            self.request_owner or self.owner,
            self.evaluated,
            "comparison-1" if self.with_comparison else None,
        )
        return Harness(
            service,
            journal,
            authorizer,
            policy_reader,
            evidence,
            evidence_reader,
            gateway_reader,
            verifiers[0],
            verifiers[1],
            verifiers[2],
            request,
        )


def _ref(value: str | None) -> str:
    assert value is not None
    return value


def assert_complete(result: JudgeResult) -> Verdict:
    assert result.status is ResultStatus.COMPLETE
    assert result.reason_codes == ()
    assert result.verdict is not None and result.projection_event is not None
    assert result.projection_event.verdict == result.verdict
    return result.verdict


def assert_failed(result: JudgeResult, *expected: ReasonCode) -> None:
    assert result.status is ResultStatus.FAILED
    assert result.verdict is None and result.projection_event is None
    # 호출 실패에는 진단 사유가 섞이지 않는다.
    assert set(result.reason_codes) <= CALL_AUDIT_FAILURE_REASON_CODES
    for reason in expected:
        assert reason in result.reason_codes


# ---------------------------------------------------------------- 판정 성공(COMPLETE)


@pytest.mark.asyncio
async def test_verified_sources_confirm_and_keep_occurred_at() -> None:
    harness = Scenario().build()
    verdict = assert_complete(await harness.service.judge(harness.request))
    assert verdict.value is VerdictValue.CONFIRMED
    assert verdict.comparison_ref == "comparison-1"
    assert verdict.evidence_refs == ("evidence-owner", "evidence-cross")
    committed = harness.journal.committed(RUN)
    assert len(committed) == 1
    # Judge 감사 시각은 신뢰 시계 값이며 근거 관찰·commit 시각과 섞지 않는다.
    assert committed[0].occurred_at == T
    assert committed[0].receipt.committed_at != T


@pytest.mark.asyncio
async def test_comparison_is_read_from_evidence_port_not_request() -> None:
    harness = Scenario().build()
    await harness.service.judge(harness.request)
    assert harness.evidence.requests[0].comparison_refs == ("comparison-1",)
    assert harness.evidence.requests[1].evidence_refs == ("evidence-owner", "evidence-cross")


@pytest.mark.asyncio
async def test_suspected_from_unknown_policy_with_cross_evidence() -> None:
    harness = Scenario(policy=policy_snapshot(access=ExpectedAccess.UNKNOWN)).build()
    verdict = assert_complete(await harness.service.judge(harness.request))
    assert verdict.value is VerdictValue.SUSPECTED
    assert verdict.comparison_ref == "comparison-1" and verdict.evidence_refs


@pytest.mark.asyncio
async def test_allowed_without_comparison_uses_trusted_time() -> None:
    scenario = Scenario(
        policy=policy_snapshot(access=ExpectedAccess.ALLOW), owner=None, with_comparison=False
    )
    harness = scenario.build()
    verdict = assert_complete(await harness.service.judge(harness.request))
    assert verdict.value is VerdictValue.ALLOWED
    assert verdict.expected_policy_source is not None
    assert harness.journal.committed(RUN)[0].occurred_at == T
    assert harness.evidence.requests == []


@pytest.mark.asyncio
async def test_allowed_needs_b_valid_at_trusted_time() -> None:
    scenario = Scenario(
        policy=policy_snapshot(access=ExpectedAccess.ALLOW),
        owner=None,
        evaluated=evaluated_identity(valid_until=T - timedelta(minutes=1)),
        with_comparison=False,
    )
    harness = scenario.build()
    verdict = assert_complete(await harness.service.judge(harness.request))
    assert verdict.value is VerdictValue.UNDECIDABLE
    assert ReasonCode.SUBJECT_NOT_VERIFIED in verdict.reason_codes


# ---------------------------------------------------------------- 시점 규칙(동찬님 조건 3)


@pytest.mark.asyncio
async def test_owner_identity_not_covering_cross_time_keeps_uncertainty() -> None:
    # A 신원은 owner 시점엔 유효했지만 cross 시점 전에 끝났다 → 기준선 보장 불가 → 확정하지 않는다.
    harness = Scenario(owner=owner_identity(valid_until=OWNER_AT + timedelta(minutes=1))).build()
    verdict = assert_complete(await harness.service.judge(harness.request))
    assert verdict.value is VerdictValue.UNDECIDABLE
    assert ReasonCode.DATA_UNVERIFIABLE in verdict.reason_codes


@pytest.mark.asyncio
async def test_policy_registered_after_cross_is_not_applied_retroactively() -> None:
    scenario = Scenario(policy=policy_snapshot(valid_from=CROSS_AT + timedelta(minutes=1)))
    harness = scenario.build()
    verdict = assert_complete(await harness.service.judge(harness.request))
    assert verdict.value is VerdictValue.UNDECIDABLE
    assert ReasonCode.EXPECTED_ACCESS_POLICY_INVALID in verdict.reason_codes


@pytest.mark.asyncio
async def test_policy_validity_at_cross_time_unconfirmable() -> None:
    scenario = Scenario(policy=policy_snapshot(valid_until=CROSS_AT))
    harness = scenario.build()
    verdict = assert_complete(await harness.service.judge(harness.request))
    assert verdict.value is VerdictValue.UNDECIDABLE
    assert ReasonCode.EXPECTED_ACCESS_POLICY_INVALID in verdict.reason_codes


@pytest.mark.asyncio
async def test_evaluated_identity_expired_at_cross_time() -> None:
    scenario = Scenario(evaluated=evaluated_identity(valid_until=CROSS_AT - timedelta(minutes=1)))
    harness = scenario.build()
    verdict = assert_complete(await harness.service.judge(harness.request))
    assert verdict.value is VerdictValue.UNDECIDABLE
    assert ReasonCode.SUBJECT_NOT_VERIFIED in verdict.reason_codes


# ---------------------------------------------------------------- 정책: 부재 vs 실패, 힌트


@pytest.mark.asyncio
async def test_known_policy_absence_is_complete_undecidable() -> None:
    harness = Scenario(policy=None).build()
    verdict = assert_complete(await harness.service.judge(harness.request))
    assert verdict.value is VerdictValue.UNDECIDABLE
    assert ReasonCode.EXPECTED_ACCESS_POLICY_MISSING in verdict.reason_codes


@pytest.mark.asyncio
async def test_policy_read_failure_is_call_failure_not_absence() -> None:
    harness = Scenario(policy_failure=(ReasonCode.NOT_FOUND,)).build()
    result = await harness.service.judge(harness.request)
    assert_failed(result, ReasonCode.NOT_FOUND)
    assert harness.journal.committed(RUN) == ()


@pytest.mark.asyncio
async def test_forged_hint_fails_the_call() -> None:
    scenario = Scenario(
        hint=policy_snapshot(access=ExpectedAccess.ALLOW),
        policy_failure=(ReasonCode.SOURCE_UNVERIFIED,),
    )
    harness = scenario.build()
    assert_failed(await harness.service.judge(harness.request), ReasonCode.SOURCE_UNVERIFIED)
    assert harness.policy_reader.requests[0].expected_policy == scenario.hint
    assert harness.journal.committed(RUN) == ()


@pytest.mark.asyncio
async def test_authentic_hint_differing_from_canonical_holds_a_deny_case() -> None:
    # 정본은 명시 DENY + 강한 교차 근거지만, 다른 정책 힌트가 왔으므로 정책 무효로 보류한다.
    scenario = Scenario(hint=policy_snapshot(access=ExpectedAccess.ALLOW, policy_ref="policy-x"))
    harness = scenario.build()
    verdict = assert_complete(await harness.service.judge(harness.request))
    assert verdict.value is VerdictValue.UNDECIDABLE
    assert ReasonCode.EXPECTED_ACCESS_POLICY_INVALID in verdict.reason_codes
    assert verdict.expected_policy_source is None


# ---------------------------------------------------------------- 감사 검증 실패


@pytest.mark.parametrize(
    ("which", "event_ref"),
    [
        ("evidence", "comparison-event-1"),
        ("evidence", "evidence-event-owner"),
        ("webdiag", "identity-event-identity-b"),
        ("gateway", "attempt-event-attempt-cross"),
    ],
)
@pytest.mark.parametrize(
    ("state", "reason", "not_reason"),
    [
        (VerificationState.INVALID, ReasonCode.SOURCE_UNVERIFIED, None),
        (
            VerificationState.UNKNOWN,
            ReasonCode.AUDIT_VERIFICATION_UNKNOWN,
            ReasonCode.SOURCE_UNVERIFIED,
        ),
    ],
)
@pytest.mark.asyncio
async def test_audit_verification_failure_fails_without_commit(
    which: str,
    event_ref: str,
    state: VerificationState,
    reason: ReasonCode,
    not_reason: ReasonCode | None,
) -> None:
    harness = Scenario().build()
    verifier = {
        "evidence": harness.evidence_verifier,
        "webdiag": harness.webdiag_verifier,
        "gateway": harness.gateway_verifier,
    }[which]
    verifier.states[event_ref] = state
    result = await harness.service.judge(harness.request)
    assert_failed(result, reason)
    if not_reason is not None:
        assert not_reason not in result.reason_codes
    # 입력 관문이 하나라도 실패하면 commit은 0건이다.
    assert harness.journal.committed(RUN) == ()


@pytest.mark.asyncio
async def test_tampered_stored_comparison_fails() -> None:
    harness = Scenario().build()
    original = harness.evidence.comparisons["comparison-1"]
    payload = replace(
        original.payload,
        signals=replace(original.payload.signals, reflection_excluded=CheckState.NO),
    )
    owner = harness.evidence.evidence["evidence-owner"]
    cross = harness.evidence.evidence["evidence-cross"]
    harness.evidence.comparisons["comparison-1"] = stored(payload, owner, cross)
    assert_failed(await harness.service.judge(harness.request), ReasonCode.SOURCE_UNVERIFIED)


@pytest.mark.asyncio
async def test_unregistered_comparison_rules_fail() -> None:
    other = ComparisonRules(SourceVersion("judge", "rules", 9), "n", "o", "c")
    harness = Scenario(rules=other).build()
    assert_failed(await harness.service.judge(harness.request), ReasonCode.SOURCE_UNVERIFIED)


@pytest.mark.asyncio
async def test_policy_subject_mismatch_fails() -> None:
    harness = Scenario(policy=policy_snapshot(owner_subject="subject-z")).build()
    assert_failed(await harness.service.judge(harness.request), ReasonCode.IDENTITY_MISMATCH)


@pytest.mark.asyncio
async def test_supplied_identity_not_linked_to_comparison_fails() -> None:
    other_owner = identity("identity-c", "subject-a", "account-a", 3)
    harness = Scenario(request_owner=other_owner).build()
    assert_failed(await harness.service.judge(harness.request), ReasonCode.IDENTITY_MISMATCH)


@pytest.mark.asyncio
async def test_subject_signal_contradicting_identities_fails() -> None:
    signals = replace(all_yes_signals(), distinct_verified_subjects=CheckState.NO)
    harness = Scenario(signals=signals).build()
    assert_failed(await harness.service.judge(harness.request), ReasonCode.SOURCE_UNVERIFIED)


# ---------------------------------------------------------------- Gateway ATTEMPT


@pytest.mark.asyncio
async def test_confirmed_not_sent_with_response_is_binding_mismatch() -> None:
    harness = Scenario(cross_send=SendStatus.NOT_SENT).build()
    result = await harness.service.judge(harness.request)
    assert_failed(result, ReasonCode.SOURCE_UNVERIFIED)
    assert ReasonCode.AUDIT_VERIFICATION_UNKNOWN not in result.reason_codes


@pytest.mark.asyncio
async def test_unknown_send_is_unknown_not_tampering(caplog: pytest.LogCaptureFixture) -> None:
    harness = Scenario(cross_send=SendStatus.UNKNOWN).build()
    with caplog.at_level(logging.INFO, logger=ATTESTATION_LOGGER):
        result = await harness.service.judge(harness.request)
    assert_failed(result, ReasonCode.AUDIT_VERIFICATION_UNKNOWN)
    assert ReasonCode.SOURCE_UNVERIFIED not in result.reason_codes
    # 검증된 기록의 unknown은 인프라 장애처럼 WARNING으로 남기지 않는다.
    records = [record for record in caplog.records if record.name == ATTESTATION_LOGGER]
    assert records and all(record.levelno == logging.INFO for record in records)


@pytest.mark.asyncio
async def test_infrastructure_unknown_is_logged_as_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness = Scenario().build()
    harness.gateway_verifier.states["attempt-event-attempt-cross"] = VerificationState.UNKNOWN
    with caplog.at_level(logging.INFO, logger=ATTESTATION_LOGGER):
        assert_failed(
            await harness.service.judge(harness.request), ReasonCode.AUDIT_VERIFICATION_UNKNOWN
        )
    assert any(
        record.name == ATTESTATION_LOGGER and record.levelno == logging.WARNING
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_latest_attempt_revision_is_adopted() -> None:
    # revision 1은 unknown, revision 2에서 sent로 확정됐다. 최고 revision을 채택한다.
    later = attempt_event(
        "attempt-cross", evaluated_identity(), 3, revision=2, fingerprint=OTHER_FP
    )
    harness = Scenario(cross_send=SendStatus.UNKNOWN, extra_gateway_events=[later]).build()
    assert_complete(await harness.service.judge(harness.request))


@pytest.mark.parametrize(
    "extra",
    [
        # 같은 revision에 다른 내용 → 충돌.
        attempt_event("attempt-cross", evaluated_identity(), 3, fingerprint=OTHER_FP),
        # revision 2 없이 3 → 이력 공백.
        attempt_event("attempt-cross", evaluated_identity(), 3, revision=3),
    ],
)
@pytest.mark.asyncio
async def test_inconsistent_attempt_history_is_unknown(extra: AuditEvent) -> None:
    harness = Scenario(extra_gateway_events=[extra]).build()
    result = await harness.service.judge(harness.request)
    assert_failed(result, ReasonCode.AUDIT_VERIFICATION_UNKNOWN)
    assert result.verdict is None


@pytest.mark.asyncio
async def test_gateway_audit_read_failure_is_unknown() -> None:
    harness = Scenario().build()
    harness.gateway_reader.failure = (ReasonCode.SNAPSHOT_EXPIRED,)
    result = await harness.service.judge(harness.request)
    assert_failed(result, ReasonCode.AUDIT_VERIFICATION_UNKNOWN, ReasonCode.SNAPSHOT_EXPIRED)


@pytest.mark.asyncio
async def test_audit_snapshot_over_page_limit_is_unknown() -> None:
    harness = Scenario(page_size=1, max_pages=1).build()
    assert_failed(
        await harness.service.judge(harness.request), ReasonCode.AUDIT_VERIFICATION_UNKNOWN
    )


@pytest.mark.asyncio
async def test_evidence_not_causally_linked_to_attempt_fails() -> None:
    harness = Scenario(link_attempts=False).build()
    assert_failed(await harness.service.judge(harness.request), ReasonCode.SOURCE_UNVERIFIED)


# ---------------------------------------------------------------- 인가·멱등·revision


@pytest.mark.asyncio
async def test_authorization_denied_fails_before_any_read() -> None:
    harness = Scenario().build()
    harness.authorizer.allowed = False
    assert_failed(await harness.service.judge(harness.request), ReasonCode.ACCESS_DENIED)
    assert harness.policy_reader.requests == []
    assert harness.journal.committed(RUN) == ()


@pytest.mark.asyncio
async def test_same_submission_returns_same_result_and_reauthorizes() -> None:
    harness = Scenario().build()
    first = await harness.service.judge(harness.request)
    second = await harness.service.judge(harness.request)
    assert first == second
    assert len(harness.journal.committed(RUN)) == 1
    assert harness.authorizer.calls == 2
    harness.authorizer.allowed = False
    # 캐시된 결과도 재인가 없이 내주지 않는다.
    assert_failed(await harness.service.judge(harness.request), ReasonCode.ACCESS_DENIED)


@pytest.mark.asyncio
async def test_same_submission_with_new_input_conflicts() -> None:
    harness = Scenario().build()
    assert_complete(await harness.service.judge(harness.request))
    changed = replace(harness.request, comparison_ref=None)
    assert_failed(await harness.service.judge(changed), ReasonCode.IDEMPOTENCY_CONFLICT)
    assert len(harness.journal.committed(RUN)) == 1


@pytest.mark.asyncio
async def test_new_submission_for_same_case_is_new_revision() -> None:
    harness = Scenario().build()
    first = assert_complete(await harness.service.judge(harness.request))
    second_request = replace(harness.request, submission_ref="submission-2")
    second = assert_complete(await harness.service.judge(second_request))
    assert second.verdict_ref == first.verdict_ref
    assert "run-1" in first.verdict_ref
    assert (first.revision, second.revision) == (1, 2)


@pytest.mark.asyncio
async def test_concurrent_revision_claim_is_revision_conflict() -> None:
    harness = Scenario(journal_type=StaleRevisionJournal).build()
    assert_complete(await harness.service.judge(harness.request))
    second_request = replace(harness.request, submission_ref="submission-2")
    result = await harness.service.judge(second_request)
    assert_failed(result, ReasonCode.REVISION_CONFLICT)


@pytest.mark.asyncio
async def test_concurrent_same_submission_commits_once() -> None:
    harness = Scenario().build()
    harness.evidence.gate = asyncio.Event()
    first = asyncio.create_task(harness.service.judge(harness.request))
    second = asyncio.create_task(harness.service.judge(harness.request))
    await asyncio.sleep(0)
    harness.evidence.gate.set()
    results = await asyncio.gather(first, second)
    assert results[0] == results[1]
    assert len(harness.journal.committed(RUN)) == 1


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_cancel_running_judgment() -> None:
    harness = Scenario().build()
    harness.evidence.gate = asyncio.Event()
    holder = asyncio.create_task(harness.service.judge(harness.request))
    await asyncio.sleep(0)
    waiter = asyncio.create_task(harness.service.judge(harness.request))
    await asyncio.sleep(0)
    waiter.cancel()
    harness.evidence.gate.set()
    assert_complete(await holder)
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert len(harness.journal.committed(RUN)) == 1


@pytest.mark.asyncio
async def test_cancelled_holder_leaves_no_cached_result() -> None:
    harness = Scenario().build()
    harness.evidence.gate = asyncio.Event()
    holder = asyncio.create_task(harness.service.judge(harness.request))
    await asyncio.sleep(0)
    holder.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder
    harness.evidence.gate.set()
    assert_complete(await harness.service.judge(harness.request))
    assert len(harness.journal.committed(RUN)) == 1
