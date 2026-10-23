"""`GatewayExecutor`(GatewayPort.execute) 테스트. 로컬 fake만 쓰고 네트워크·DB 없이 실행한다.

실제 prepare로 핸들·view를 만들고, execute가 §10 ①~⑤를 거치는지·관문이 막으면 전송·예산에
진입하지 않는지·전송 상태를 보존하는지를 검증한다.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from abc2lab_contracts.audit import (
    AuditEventKind,
    AuditReceipt,
    AuditRecordBinding,
    AuditVerifyRequest,
    AuditVerifyResult,
    PolicyOutcome,
    RequestIntentRecord,
    VerificationState,
)
from abc2lab_contracts.capture import (
    CaptureRequest,
    CaptureResult,
    ExecutedRequestView,
    RawResponse,
)
from abc2lab_contracts.execution import (
    ExecuteRequest,
    ExecutionRequest,
    PolicyDecision,
    PrivateHttpRequest,
)
from abc2lab_contracts.fingerprint import policy_input_fingerprint
from abc2lab_contracts.primitives import (
    CaptureStatus,
    CloseResult,
    ParameterLocation,
    Purpose,
    ReasonCode,
    Ref,
    RequestParameter,
    ResultStatus,
    RunKey,
    SendStatus,
    SourceVersion,
)
from abc2lab_contracts.registration import OperationRegistration
from abc2lab_contracts.session import (
    AuthSignal,
    AuthSignalKind,
    AuthSignalState,
    SessionBinding,
    SessionBindingResult,
    SessionHandle,
)
from abc2lab_gateway.adapters import (
    ExecuteDependencies,
    ExecuteSettings,
    GatewayExecutor,
    GatewayPreparer,
    GatewayRegistration,
    InMemoryBudgetLedger,
    InMemoryGatewayJournal,
    InMemoryGatewayRegistrations,
    InMemoryPreparedHandleStore,
    InMemoryVaultBinder,
    JournalCommitError,
    SendOutcome,
    StubAuthSignalExtractor,
    StubTransport,
)
from abc2lab_gateway.adapters.handles import PreparedRequest
from abc2lab_gateway.adapters.journal import InMemoryGatewayJournal as _Journal
from abc2lab_gateway.core.model import TransportObservation

_ORIGIN = "https://api.example.test"


# ---------------------------------------------------------------- fakes


class FakeDecisionVerifier:
    """정책 결정 commit 검증 fake. 설정한 상태를 돌려주고 요청을 기록한다."""

    def __init__(self, state: VerificationState = VerificationState.VERIFIED) -> None:
        self.state = state
        self.requests: list[AuditVerifyRequest] = []

    async def verify_committed(self, request: AuditVerifyRequest) -> AuditVerifyResult:
        self.requests.append(request)
        return AuditVerifyResult(request.run_key, self.state, ())


class CountingBudget:
    """예산 fake. 호출 binding_id를 기록하고 설정한 허용 여부를 돌려준다."""

    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow
        self.calls: list[Ref] = []

    def try_consume(self, run_key: RunKey, binding_id: Ref, max_attempts: int) -> bool:
        self.calls.append(binding_id)
        return self.allow


class FakeCapture:
    """LocalCapturePort fake. 성공/실패를 설정하고 인계 요청을 기록한다."""

    def __init__(self, *, status: ResultStatus = ResultStatus.COMPLETE) -> None:
        self.status = status
        self.requests: list[CaptureRequest] = []

    def capture(self, request: CaptureRequest) -> CaptureResult:
        self.requests.append(request)
        if self.status is ResultStatus.COMPLETE:
            return CaptureResult(request.run_key, ResultStatus.COMPLETE, "capture-1", ())
        return CaptureResult(
            request.run_key, ResultStatus.FAILED, None, (ReasonCode.CAPTURE_UNAVAILABLE,)
        )

    def release_captures(self, request: object) -> CloseResult:  # pragma: no cover - unused
        raise AssertionError("execute does not release captures")


class FailingIntentJournal(InMemoryGatewayJournal):
    """intent commit이 항상 실패하는 journal(② 실패 경로 검증용)."""

    async def append_intent(self, record: RequestIntentRecord) -> AuditReceipt:
        raise JournalCommitError("intent commit failed")


# ---------------------------------------------------------------- helpers


def captured_send(run_key: RunKey, now: datetime) -> SendOutcome:
    """SENT_CAPTURED 관찰과 원문·실제 전송 view를 담은 전송 결과."""
    view = ExecutedRequestView(
        run_key=run_key,
        request_ref="request-1",
        attempt_ref="attempt-fixed",
        operation_ref="op-get-order",
        operation_revision=2,
        resource_ref="res-order-1001",
        resource_binding_ref="rb-order-1",
        resource_binding_revision=4,
        account_ref="acct-eval",
        session_generation=2,
        purpose=Purpose.OBSERVE,
        method="GET",
        actual_origin=_ORIGIN,
        actual_path="/orders/1001",
        actual_parameters=(RequestParameter("order_id", ParameterLocation.PATH, "1001"),),
    )
    response = RawResponse(status_code=200, headers=(), body=b"{}")
    return SendOutcome(TransportObservation.SENT_CAPTURED, response, view)


def make_decision(
    prepared: PreparedRequest,
    now: datetime,
    *,
    outcome: PolicyOutcome = PolicyOutcome.ALLOW,
    binding_id: Ref | None = None,
    view_fingerprint: str | None = None,
) -> PolicyDecision:
    """준비된 view와 맞는(또는 어긋나는) 정책 결정을 만든다. 영수증 binding은 fake 검증만 받는다."""
    binding = binding_id if binding_id is not None else prepared.binding_id
    view = (
        view_fingerprint
        if view_fingerprint is not None
        else policy_input_fingerprint(prepared.policy_input)
    )
    receipt = AuditReceipt(
        run_key=prepared.run_key,
        producer="policy",
        event_ref="policy:run-1:decision-1",
        sequence=1,
        binding=AuditRecordBinding(
            AuditEventKind.POLICY_DECISION, "decision-1", 1, "a" * 64, "request-1", None, binding
        ),
        committed_at=now,
    )
    return PolicyDecision(
        run_key=prepared.run_key,
        decision_ref="decision-1",
        binding_id=binding,
        evaluated_view_fingerprint=view,
        outcome=outcome,
        policy_version=SourceVersion(issuer="policy", source_ref="default-deny", revision=1),
        issued_at=now,
        expires_at=now + timedelta(minutes=10),
        audit_receipt=receipt,
        reason_codes=(),
    )


def build_executor(
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    now: datetime,
    *,
    verifier: FakeDecisionVerifier | None = None,
    journal: InMemoryGatewayJournal | None = None,
    budget: CountingBudget | None = None,
    vault: InMemoryVaultBinder | None = None,
    transport: StubTransport | None = None,
    capture: FakeCapture | None = None,
    auth_extractor: StubAuthSignalExtractor | None = None,
) -> GatewayExecutor:
    """fake 의존을 묶어 executor를 만든다. attempt_ref는 고정한다."""
    deps = ExecuteDependencies(
        handles=handles,
        sessions=sessions,  # type: ignore[arg-type]
        decision_verifier=verifier or FakeDecisionVerifier(),
        journal=journal or _Journal("gateway", clock=lambda: now),
        budget=budget or CountingBudget(),
        vault=vault or InMemoryVaultBinder(),
        transport=transport or StubTransport(captured_send(_RUN, now)),
        capture=capture or FakeCapture(),
        auth_extractor=auth_extractor or StubAuthSignalExtractor(),
        clock=lambda: now,
    )
    return GatewayExecutor(
        deps, ExecuteSettings("gateway"), attempt_ref_factory=lambda producer, run: "attempt-fixed"
    )


_RUN = RunKey(
    organization_ref="org-1", target_ref="target-1", environment_ref="env-1", run_ref="run-1"
)
_SESSION_HANDLE = SessionHandle(
    session_ref="sess-eval",
    run_key=_RUN,
    account_ref="acct-eval",
    generation=2,
    expires_at=datetime(2026, 10, 22, 12, 30, tzinfo=UTC),
)


async def prepared_handle(
    preparer: GatewayPreparer, request: ExecutionRequest
) -> tuple[Ref, PreparedRequest]:
    """prepare를 수행해 핸들과 그 view를 돌려준다(COMPLETE 전제)."""
    result = await preparer.prepare(request)
    assert result.status is ResultStatus.COMPLETE
    assert result.prepared_handle is not None and result.policy_input is not None
    prepared = PreparedRequest(
        run_key=request.run_key,
        request_ref=request.request_ref,
        binding_id=result.policy_input.binding_id,
        policy_input=result.policy_input,
        request=request,
        expires_at=result.policy_input.expires_at,
    )
    return result.prepared_handle, prepared


# ---------------------------------------------------------------- 행복 경로


@pytest.mark.asyncio
async def test_allow_decision_sends_captures_and_records(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    now: datetime,
) -> None:
    handle, prepared = await prepared_handle(preparer, execution_request)
    decision = make_decision(prepared, now)
    transport = StubTransport(captured_send(execution_request.run_key, now))
    capture = FakeCapture()
    executor = build_executor(handles, sessions, now, transport=transport, capture=capture)
    result = await executor.execute(
        ExecuteRequest(execution_request.run_key, "request-1", handle, decision)
    )
    assert result.send_status is SendStatus.SENT
    assert result.capture_status is CaptureStatus.CAPTURED
    assert result.capture_ref == "capture-1"
    assert result.decision_ref == "decision-1" and result.binding_id == "binding-fixed"
    assert result.reason_codes == ()
    assert len(transport.commands) == 1 and len(capture.requests) == 1


# ---------------------------------------------------------------- ① 결정 게이트


@pytest.mark.asyncio
async def test_missing_decision_is_not_sent_without_intent_or_budget(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    now: datetime,
) -> None:
    handle, _ = await prepared_handle(preparer, execution_request)
    transport, budget, journal = (
        StubTransport(captured_send(execution_request.run_key, now)),
        CountingBudget(),
        _Journal("gateway", clock=lambda: now),
    )
    executor = build_executor(
        handles, sessions, now, transport=transport, budget=budget, journal=journal
    )
    result = await executor.execute(
        ExecuteRequest(execution_request.run_key, "request-1", handle, None)
    )
    assert result.send_status is SendStatus.NOT_SENT
    assert result.reason_codes == (ReasonCode.POLICY_BLOCKED,)
    assert transport.commands == [] and budget.calls == []
    # intent는 없고 attempt 레코드만 남는다(sequence 1 하나).
    assert journal.committed_count(execution_request.run_key) == 1


@pytest.mark.asyncio
async def test_block_decision_is_not_sent(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    now: datetime,
) -> None:
    handle, prepared = await prepared_handle(preparer, execution_request)
    decision = make_decision(prepared, now, outcome=PolicyOutcome.BLOCK)
    transport, budget = (
        StubTransport(captured_send(execution_request.run_key, now)),
        CountingBudget(),
    )
    executor = build_executor(handles, sessions, now, transport=transport, budget=budget)
    result = await executor.execute(
        ExecuteRequest(execution_request.run_key, "request-1", handle, decision)
    )
    assert result.send_status is SendStatus.NOT_SENT
    assert result.reason_codes == (ReasonCode.POLICY_BLOCKED,)
    assert transport.commands == [] and budget.calls == []


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        (VerificationState.INVALID, ReasonCode.SOURCE_UNVERIFIED),
        (VerificationState.UNKNOWN, ReasonCode.AUDIT_VERIFICATION_UNKNOWN),
    ],
)
@pytest.mark.asyncio
async def test_unverified_decision_commit_blocks(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    now: datetime,
    state: VerificationState,
    reason: ReasonCode,
) -> None:
    handle, prepared = await prepared_handle(preparer, execution_request)
    decision = make_decision(prepared, now)
    transport, budget = (
        StubTransport(captured_send(execution_request.run_key, now)),
        CountingBudget(),
    )
    executor = build_executor(
        handles,
        sessions,
        now,
        verifier=FakeDecisionVerifier(state),
        transport=transport,
        budget=budget,
    )
    result = await executor.execute(
        ExecuteRequest(execution_request.run_key, "request-1", handle, decision)
    )
    assert result.send_status is SendStatus.NOT_SENT
    assert reason in result.reason_codes
    assert transport.commands == [] and budget.calls == []


@pytest.mark.parametrize("field", ["binding_id", "view_fingerprint"])
@pytest.mark.asyncio
async def test_decision_for_other_view_is_binding_mismatch(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    now: datetime,
    field: str,
) -> None:
    handle, prepared = await prepared_handle(preparer, execution_request)
    kwargs = {field: "b" * 64 if field == "view_fingerprint" else "binding-other"}
    decision = make_decision(prepared, now, **kwargs)  # type: ignore[arg-type]
    verifier, transport, budget = (
        FakeDecisionVerifier(),
        StubTransport(captured_send(execution_request.run_key, now)),
        CountingBudget(),
    )
    executor = build_executor(
        handles, sessions, now, verifier=verifier, transport=transport, budget=budget
    )
    result = await executor.execute(
        ExecuteRequest(execution_request.run_key, "request-1", handle, decision)
    )
    assert result.send_status is SendStatus.NOT_SENT
    assert ReasonCode.POLICY_VIEW_MISMATCH in result.reason_codes
    # binding/view가 안 맞으면 commit 검증도 하지 않고 바로 막는다.
    assert verifier.requests == [] and transport.commands == [] and budget.calls == []


# ---------------------------------------------------------------- ② intent 게이팅


@pytest.mark.asyncio
async def test_intent_commit_failure_blocks_before_transport(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    now: datetime,
) -> None:
    handle, prepared = await prepared_handle(preparer, execution_request)
    decision = make_decision(prepared, now)
    transport, budget = (
        StubTransport(captured_send(execution_request.run_key, now)),
        CountingBudget(),
    )
    executor = build_executor(
        handles,
        sessions,
        now,
        journal=FailingIntentJournal("gateway", clock=lambda: now),
        transport=transport,
        budget=budget,
    )
    result = await executor.execute(
        ExecuteRequest(execution_request.run_key, "request-1", handle, decision)
    )
    assert result.send_status is SendStatus.NOT_SENT
    assert ReasonCode.AUDIT_COMMIT_FAILED in result.reason_codes
    # ② 실패면 임계 구역·예산·transport에 진입하지 않는다.
    assert transport.commands == [] and budget.calls == []


# ---------------------------------------------------------------- ③④ 임계 구역


@pytest.mark.asyncio
async def test_generation_change_blocks_in_critical_section(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    confirmed_binding: SessionBinding,
    now: datetime,
) -> None:
    handle, prepared = await prepared_handle(preparer, execution_request)
    decision = make_decision(prepared, now)
    # prepare 뒤 세션 generation이 바뀌었다: 재검사가 잡아야 한다.
    changed = _change_generation(confirmed_binding, 99)
    reader = _StaticSessions({(execution_request.run_key, changed.session.session_ref): changed})
    transport, budget = (
        StubTransport(captured_send(execution_request.run_key, now)),
        CountingBudget(),
    )
    executor = build_executor(handles, reader, now, transport=transport, budget=budget)
    result = await executor.execute(
        ExecuteRequest(execution_request.run_key, "request-1", handle, decision)
    )
    assert result.send_status is SendStatus.NOT_SENT
    assert ReasonCode.SESSION_GENERATION_CHANGED in result.reason_codes
    assert transport.commands == []
    # 재검사 실패면 예산을 깎지 않는다.
    assert budget.calls == []


@pytest.mark.asyncio
async def test_budget_exhausted_blocks_without_transport(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    now: datetime,
) -> None:
    handle, prepared = await prepared_handle(preparer, execution_request)
    decision = make_decision(prepared, now)
    transport = StubTransport(captured_send(execution_request.run_key, now))
    executor = build_executor(
        handles, sessions, now, budget=CountingBudget(allow=False), transport=transport
    )
    result = await executor.execute(
        ExecuteRequest(execution_request.run_key, "request-1", handle, decision)
    )
    assert result.send_status is SendStatus.NOT_SENT
    assert ReasonCode.BUDGET_EXHAUSTED in result.reason_codes
    # 예산이 막으면 transport에 진입하지 않는다(예산 차감이 전송 뒤가 아님).
    assert transport.commands == []


# ---------------------------------------------------------------- 핸들


@pytest.mark.parametrize("variant", ["missing", "consumed", "request_mismatch"])
@pytest.mark.asyncio
async def test_invalid_handle_is_not_sent(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    now: datetime,
    variant: str,
) -> None:
    handle, prepared = await prepared_handle(preparer, execution_request)
    decision = make_decision(prepared, now)
    transport, budget = (
        StubTransport(captured_send(execution_request.run_key, now)),
        CountingBudget(),
    )
    executor = build_executor(handles, sessions, now, transport=transport, budget=budget)
    if variant == "missing":
        used_handle, used_request = "gateway-prepared-absent", "request-1"
    elif variant == "consumed":
        await executor.execute(
            ExecuteRequest(execution_request.run_key, "request-1", handle, decision)
        )
        transport.commands.clear()
        used_handle, used_request = handle, "request-1"
    else:
        used_handle, used_request = handle, "request-other"
    result = await executor.execute(
        ExecuteRequest(execution_request.run_key, used_request, used_handle, decision)
    )
    assert result.send_status is SendStatus.NOT_SENT
    assert ReasonCode.PREPARED_HANDLE_INVALID in result.reason_codes
    assert transport.commands == []


# ---------------------------------------------------------------- transport·capture


@pytest.mark.parametrize(
    ("observation", "send_status", "capture_status", "reason"),
    [
        (
            TransportObservation.SENT_CAPTURE_UNAVAILABLE,
            SendStatus.SENT,
            CaptureStatus.UNAVAILABLE,
            ReasonCode.CAPTURE_UNAVAILABLE,
        ),
        (
            TransportObservation.SENT_RESPONSE_OVERLIMIT,
            SendStatus.SENT,
            CaptureStatus.UNAVAILABLE,
            ReasonCode.RESPONSE_LIMIT_EXCEEDED,
        ),
        (
            TransportObservation.SEND_UNCONFIRMED,
            SendStatus.UNKNOWN,
            CaptureStatus.INDETERMINATE,
            ReasonCode.SEND_ACKNOWLEDGEMENT_LOST,
        ),
    ],
)
@pytest.mark.asyncio
async def test_transport_observations_preserve_send_state(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    now: datetime,
    observation: TransportObservation,
    send_status: SendStatus,
    capture_status: CaptureStatus,
    reason: ReasonCode,
) -> None:
    handle, prepared = await prepared_handle(preparer, execution_request)
    decision = make_decision(prepared, now)
    executor = build_executor(
        handles, sessions, now, transport=StubTransport(SendOutcome(observation))
    )
    result = await executor.execute(
        ExecuteRequest(execution_request.run_key, "request-1", handle, decision)
    )
    assert result.send_status is send_status
    assert result.capture_status is capture_status
    assert result.capture_ref is None
    assert reason in result.reason_codes


@pytest.mark.asyncio
async def test_capture_failure_downgrades_to_sent_unavailable(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    now: datetime,
) -> None:
    handle, prepared = await prepared_handle(preparer, execution_request)
    decision = make_decision(prepared, now)
    executor = build_executor(
        handles,
        sessions,
        now,
        transport=StubTransport(captured_send(execution_request.run_key, now)),
        capture=FakeCapture(status=ResultStatus.FAILED),
    )
    result = await executor.execute(
        ExecuteRequest(execution_request.run_key, "request-1", handle, decision)
    )
    assert result.send_status is SendStatus.SENT
    assert result.capture_status is CaptureStatus.UNAVAILABLE
    assert result.capture_ref is None
    assert ReasonCode.CAPTURE_UNAVAILABLE in result.reason_codes


@pytest.mark.asyncio
async def test_transport_not_entered_is_not_sent(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    handles: InMemoryPreparedHandleStore,
    sessions: object,
    now: datetime,
) -> None:
    # 게이트를 통과했어도 transport가 실제로 진입하지 않으면 not_sent다. 공개 사유 코드 매핑은
    # 별도 PR(transport_not_entered)이 처리하므로 여기서는 전송/캡처 상태만 확인한다.
    handle, prepared = await prepared_handle(preparer, execution_request)
    decision = make_decision(prepared, now)
    executor = build_executor(
        handles,
        sessions,
        now,
        transport=StubTransport(SendOutcome(TransportObservation.NOT_ENTERED)),
    )
    result = await executor.execute(
        ExecuteRequest(execution_request.run_key, "request-1", handle, decision)
    )
    assert result.send_status is SendStatus.NOT_SENT
    assert result.capture_status is CaptureStatus.NOT_APPLICABLE
    assert result.capture_ref is None


# ---------------------------------------------------------------- 예산 ledger 단위


def test_budget_ledger_caps_and_dedups_binding() -> None:
    ledger = InMemoryBudgetLedger()
    assert ledger.try_consume(_RUN, "b1", 2) is True
    assert ledger.try_consume(_RUN, "b1", 2) is True  # 같은 binding 재차감 없음
    assert ledger.try_consume(_RUN, "b2", 2) is True
    assert ledger.try_consume(_RUN, "b3", 2) is False  # 한도 초과


# ---------------------------------------------------------------- 지원 double


def _change_generation(binding: SessionBinding, generation: int) -> SessionBinding:
    # 세션과 신원 generation을 함께 바꿔 바인딩 불변식(둘이 일치)을 지킨다.
    identity = binding.identity
    new_identity = None if identity is None else replace(identity, generation=generation)
    return replace(
        binding, session=replace(binding.session, generation=generation), identity=new_identity
    )


class _StaticSessions:
    """고정된 바인딩만 돌려주는 최소 `SessionBindingReader` 더블."""

    def __init__(self, bindings: dict[tuple[RunKey, Ref], SessionBinding]) -> None:
        self._bindings = bindings

    def read_session_binding(self, run_key: RunKey, session_ref: Ref) -> SessionBindingResult:
        binding = self._bindings.get((run_key, session_ref))
        if binding is None:
            return SessionBindingResult(run_key, ResultStatus.FAILED, None, (ReasonCode.NOT_FOUND,))
        return SessionBindingResult(run_key, ResultStatus.COMPLETE, binding, ())


# ---------------------------------------------------------------- auth_signal 배선


_AUTH_PROFILE = "auth-prof-whoami"


async def identify_handle(
    registration: GatewayRegistration,
    sessions: object,
    handles: InMemoryPreparedHandleStore,
    now: datetime,
    *,
    purpose: Purpose,
) -> tuple[Ref, ExecuteRequest]:
    """auth_profile을 가진 operation으로 purpose 요청을 prepare해 핸들을 얻는다."""
    operation = OperationRegistration(
        source=SourceVersion(issuer="reg", source_ref="op-whoami", revision=2),
        operation_ref="op-whoami",
        allowed_purposes=(Purpose.AUTHENTICATE, Purpose.IDENTIFY),
        auth_profile_ref=_AUTH_PROFILE,
        method="GET",
        origin=_ORIGIN,
        path_template="/whoami",
        resource_bindings=(),
    )
    store = InMemoryGatewayRegistrations()
    store.register(_RUN, replace(registration, operations=(operation,)))
    preparer = GatewayPreparer(
        store,
        sessions,  # type: ignore[arg-type]
        handles,
        "gateway",
        clock=lambda: now,
        binding_id_factory=lambda: "binding-fixed",
    )
    request = ExecutionRequest(
        run_key=_RUN,
        request_ref="request-1",
        operation_ref="op-whoami",
        operation_revision=2,
        resource_ref=None,
        resource_binding_ref=None,
        resource_binding_revision=None,
        purpose=purpose,
        http=PrivateHttpRequest(
            origin=_ORIGIN, method="GET", path="/whoami", parameters=(), timeout_ms=5_000
        ),
        session=_SESSION_HANDLE,
        owner_session=None,
        scope_revision=1,
        profile_revision=1,
        expected_policy=None,
        cross_confirmation=None,
    )
    result = await preparer.prepare(request)
    assert result.status is ResultStatus.COMPLETE and result.prepared_handle is not None
    exec_request = ExecuteRequest(_RUN, "request-1", result.prepared_handle, None)
    return result.prepared_handle, exec_request


@pytest.mark.asyncio
async def test_identify_extracts_identity_auth_signal(
    registration: GatewayRegistration,
    sessions: object,
    handles: InMemoryPreparedHandleStore,
    now: datetime,
) -> None:
    handle, exec_request = await identify_handle(
        registration, sessions, handles, now, purpose=Purpose.IDENTIFY
    )
    prepared = handles.consume(_RUN, handle)
    assert prepared is not None
    handle2 = handles.allocate(prepared)  # execute가 소비할 수 있도록 다시 넣는다
    signal = AuthSignal(AuthSignalKind.IDENTITY, AuthSignalState.ACCEPTED, "subject-alias")
    extractor = StubAuthSignalExtractor(signal)
    decision = make_decision(prepared, now)
    executor = build_executor(handles, sessions, now, auth_extractor=extractor)
    result = await executor.execute(ExecuteRequest(_RUN, "request-1", handle2, decision))
    assert result.send_status is SendStatus.SENT
    assert result.auth_signal == signal
    assert extractor.calls == [Purpose.IDENTIFY]  # 요청 purpose로 호출


@pytest.mark.asyncio
async def test_authenticate_does_not_leak_identity_signal(
    registration: GatewayRegistration,
    sessions: object,
    handles: InMemoryPreparedHandleStore,
    now: datetime,
) -> None:
    handle, _ = await identify_handle(
        registration, sessions, handles, now, purpose=Purpose.AUTHENTICATE
    )
    prepared = handles.consume(_RUN, handle)
    assert prepared is not None
    handle2 = handles.allocate(prepared)
    # identity 신호만 설정된 추출기 → AUTHENTICATE 요청에는 반환하지 않는다(교차 목적 누출 방지).
    extractor = StubAuthSignalExtractor(
        AuthSignal(AuthSignalKind.IDENTITY, AuthSignalState.ACCEPTED, "subject-alias")
    )
    decision = make_decision(prepared, now)
    executor = build_executor(handles, sessions, now, auth_extractor=extractor)
    result = await executor.execute(ExecuteRequest(_RUN, "request-1", handle2, decision))
    assert extractor.calls == [Purpose.AUTHENTICATE]
    assert result.auth_signal is None


@pytest.mark.asyncio
async def test_observe_does_not_extract_even_with_auth_profile(
    registration: GatewayRegistration,
    sessions: object,
    handles: InMemoryPreparedHandleStore,
    now: datetime,
) -> None:
    # auth_profile_ref가 있어도 purpose가 OBSERVE면 추출하지 않는다(purpose 가드 단독 검증).
    handle, _ = await identify_handle(registration, sessions, handles, now, purpose=Purpose.OBSERVE)
    prepared = handles.consume(_RUN, handle)
    assert prepared is not None and prepared.auth_profile_ref == _AUTH_PROFILE
    handle2 = handles.allocate(prepared)
    extractor = StubAuthSignalExtractor(
        AuthSignal(AuthSignalKind.IDENTITY, AuthSignalState.ACCEPTED, "subject-alias")
    )
    executor = build_executor(handles, sessions, now, auth_extractor=extractor)
    result = await executor.execute(
        ExecuteRequest(_RUN, "request-1", handle2, make_decision(prepared, now))
    )
    assert result.auth_signal is None
    assert extractor.calls == []  # 관찰은 추출 안 함


@pytest.mark.asyncio
async def test_not_sent_skips_extraction(
    registration: GatewayRegistration,
    sessions: object,
    handles: InMemoryPreparedHandleStore,
    now: datetime,
) -> None:
    handle, _ = await identify_handle(
        registration, sessions, handles, now, purpose=Purpose.IDENTIFY
    )
    prepared = handles.consume(_RUN, handle)
    assert prepared is not None
    handle2 = handles.allocate(prepared)
    extractor = StubAuthSignalExtractor(
        AuthSignal(AuthSignalKind.IDENTITY, AuthSignalState.ACCEPTED, "subject-alias")
    )
    executor = build_executor(
        handles, sessions, now, budget=CountingBudget(allow=False), auth_extractor=extractor
    )
    decision = make_decision(prepared, now)
    result = await executor.execute(ExecuteRequest(_RUN, "request-1", handle2, decision))
    assert result.send_status is SendStatus.NOT_SENT
    assert result.auth_signal is None
    assert extractor.calls == []  # 전송 안 했으면 추출 없음
