"""gateway 어댑터 테스트의 공용 C2 fixture와 세션 reader 더블. 네트워크·DB 없이 만든다."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from abc2lab_contracts.audit import AuditEventKind, AuditReceipt, AuditRecordBinding
from abc2lab_contracts.execution import ExecutionRequest, PrivateHttpRequest
from abc2lab_contracts.primitives import (
    ParameterLocation,
    Purpose,
    ReasonCode,
    Ref,
    RequestParameter,
    ResultStatus,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.registration import (
    BudgetSnapshot,
    ExecutionProfileSnapshot,
    OperationRegistration,
    ResourceBinding,
    ScopeSnapshot,
)
from abc2lab_contracts.session import (
    IdentityResult,
    IdentityStatus,
    SessionBinding,
    SessionBindingResult,
    SessionHandle,
    SessionState,
)
from abc2lab_gateway.adapters import (
    GatewayPreparer,
    GatewayRegistration,
    InMemoryGatewayRegistrations,
    InMemoryPreparedHandleStore,
)

_ORIGIN = "https://api.example.test"


class InMemorySessionBindings:
    """`SessionBindingReader` 테스트 더블. 저장된 바인딩·실패를 즉시 돌려준다."""

    def __init__(self) -> None:
        self._bindings: dict[tuple[RunKey, Ref], SessionBinding] = {}
        self._failures: dict[tuple[RunKey, Ref], tuple[ReasonCode, ...]] = {}

    def set_binding(self, run_key: RunKey, binding: SessionBinding) -> None:
        self._bindings[(run_key, binding.session.session_ref)] = binding

    def set_failure(self, run_key: RunKey, session_ref: Ref, *reasons: ReasonCode) -> None:
        self._failures[(run_key, session_ref)] = reasons

    def read_session_binding(self, run_key: RunKey, session_ref: Ref) -> SessionBindingResult:
        key = (run_key, session_ref)
        if key in self._bindings:
            return SessionBindingResult(run_key, ResultStatus.COMPLETE, self._bindings[key], ())
        reasons = self._failures.get(key, (ReasonCode.SESSION_EXPIRED,))
        return SessionBindingResult(run_key, ResultStatus.FAILED, None, reasons)


def verified_identity(
    run_key: RunKey, session: SessionHandle, subject_ref: Ref, now: datetime
) -> IdentityResult:
    """테스트용 verified IdentityResult를 만든다. 감사 영수증까지 포함한다."""
    binding = AuditRecordBinding(
        event_kind=AuditEventKind.IDENTITY,
        record_ref=f"identity-{session.session_ref}",
        record_revision=1,
        record_fingerprint="a" * 64,
        request_ref=None,
        attempt_ref=None,
        binding_id=None,
    )
    receipt = AuditReceipt(
        run_key=run_key,
        producer="webdiag",
        event_ref=f"webdiag:{session.session_ref}:1",
        sequence=1,
        binding=binding,
        committed_at=now - timedelta(minutes=30),
    )
    return IdentityResult(
        run_key=run_key,
        identity_ref=f"identity-{session.session_ref}",
        status=IdentityStatus.VERIFIED,
        session_ref=session.session_ref,
        account_ref=session.account_ref,
        generation=session.generation,
        subject_ref=subject_ref,
        evidence_ref=f"evidence-{session.session_ref}",
        verified_at=now - timedelta(minutes=30),
        valid_until=now + timedelta(minutes=30),
        audit_receipt=receipt,
        attempt_summaries=(),
        reason_codes=(),
    )


def confirmed(session: SessionHandle, identity: IdentityResult) -> SessionBinding:
    """verified 신원을 담은 confirmed 세션 바인딩을 만든다."""
    return SessionBinding(
        session=session,
        state=SessionState.CONFIRMED,
        identity=identity,
        transport_context_ref=f"ctx-{session.session_ref}",
        cancelled=False,
    )


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def run_key() -> RunKey:
    return RunKey(
        organization_ref="org-1", target_ref="target-1", environment_ref="env-1", run_ref="run-1"
    )


@pytest.fixture
def scope(now: datetime) -> ScopeSnapshot:
    return ScopeSnapshot(
        source=SourceVersion(issuer="reg", source_ref="scope", revision=1),
        allowed_origins=(_ORIGIN,),
        allowed_operation_refs=("op-get-order",),
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
    )


@pytest.fixture
def profile(now: datetime) -> ExecutionProfileSnapshot:
    return ExecutionProfileSnapshot(
        source=SourceVersion(issuer="reg", source_ref="profile", revision=1),
        allowed_methods=("GET",),
        allowed_purposes=(Purpose.OBSERVE, Purpose.ACCESS_COMPARE),
        allow_redirects=False,
        valid_until=now + timedelta(hours=1),
    )


@pytest.fixture
def budget() -> BudgetSnapshot:
    return BudgetSnapshot(
        source=SourceVersion(issuer="reg", source_ref="budget", revision=1),
        max_attempts=3,
        max_duration_ms=10_000,
        max_response_bytes=1_048_576,
    )


@pytest.fixture
def resource_binding() -> ResourceBinding:
    return ResourceBinding(
        resource_binding_ref="rb-order-1",
        source=SourceVersion(issuer="reg", source_ref="binding", revision=4),
        resource_ref="res-order-1001",
        owner_subject_ref="subject-owner",
        parameters=(RequestParameter("order_id", ParameterLocation.PATH, "1001"),),
    )


@pytest.fixture
def operation(resource_binding: ResourceBinding) -> OperationRegistration:
    return OperationRegistration(
        source=SourceVersion(issuer="reg", source_ref="op-get-order", revision=2),
        operation_ref="op-get-order",
        allowed_purposes=(Purpose.OBSERVE, Purpose.ACCESS_COMPARE),
        auth_profile_ref=None,
        method="GET",
        origin=_ORIGIN,
        path_template="/orders/{order_id}",
        resource_bindings=(resource_binding,),
    )


@pytest.fixture
def registration(
    scope: ScopeSnapshot,
    profile: ExecutionProfileSnapshot,
    budget: BudgetSnapshot,
    operation: OperationRegistration,
) -> GatewayRegistration:
    return GatewayRegistration(scope=scope, profile=profile, budget=budget, operations=(operation,))


@pytest.fixture
def http() -> PrivateHttpRequest:
    return PrivateHttpRequest(
        origin=_ORIGIN,
        method="GET",
        path="/orders/1001",
        parameters=(RequestParameter("order_id", ParameterLocation.PATH, "1001"),),
        timeout_ms=5_000,
    )


@pytest.fixture
def session_handle(run_key: RunKey, now: datetime) -> SessionHandle:
    return SessionHandle(
        session_ref="sess-eval",
        run_key=run_key,
        account_ref="acct-eval",
        generation=2,
        expires_at=now + timedelta(minutes=30),
    )


@pytest.fixture
def owner_session_handle(run_key: RunKey, now: datetime) -> SessionHandle:
    return SessionHandle(
        session_ref="sess-owner",
        run_key=run_key,
        account_ref="acct-owner",
        generation=1,
        expires_at=now + timedelta(minutes=30),
    )


@pytest.fixture
def confirmed_binding(
    run_key: RunKey, session_handle: SessionHandle, now: datetime
) -> SessionBinding:
    return confirmed(
        session_handle, verified_identity(run_key, session_handle, "subject-eval", now)
    )


@pytest.fixture
def owner_binding(
    run_key: RunKey, owner_session_handle: SessionHandle, now: datetime
) -> SessionBinding:
    identity = verified_identity(run_key, owner_session_handle, "subject-owner", now)
    return confirmed(owner_session_handle, identity)


@pytest.fixture
def sessions(
    run_key: RunKey, confirmed_binding: SessionBinding, owner_binding: SessionBinding
) -> InMemorySessionBindings:
    store = InMemorySessionBindings()
    store.set_binding(run_key, confirmed_binding)
    store.set_binding(run_key, owner_binding)
    return store


@pytest.fixture
def registrations(
    run_key: RunKey, registration: GatewayRegistration
) -> InMemoryGatewayRegistrations:
    store = InMemoryGatewayRegistrations()
    store.register(run_key, registration)
    return store


@pytest.fixture
def handles(now: datetime) -> InMemoryPreparedHandleStore:
    return InMemoryPreparedHandleStore(clock=lambda: now)


@pytest.fixture
def preparer(
    registrations: InMemoryGatewayRegistrations,
    sessions: InMemorySessionBindings,
    handles: InMemoryPreparedHandleStore,
    now: datetime,
) -> GatewayPreparer:
    return GatewayPreparer(
        registrations,
        sessions,
        handles,
        "gateway",
        clock=lambda: now,
        binding_id_factory=lambda: "binding-fixed",
    )


@pytest.fixture
def execution_request(
    run_key: RunKey, http: PrivateHttpRequest, session_handle: SessionHandle
) -> ExecutionRequest:
    """등록과 맞는 기본 객체 GET 요청. 변형 테스트는 dataclasses.replace로 바꾼다."""
    return ExecutionRequest(
        run_key=run_key,
        request_ref="request-1",
        operation_ref="op-get-order",
        operation_revision=2,
        resource_ref="res-order-1001",
        resource_binding_ref="rb-order-1",
        resource_binding_revision=4,
        purpose=Purpose.OBSERVE,
        http=http,
        session=session_handle,
        owner_session=None,
        scope_revision=1,
        profile_revision=1,
        expected_policy=None,
        cross_confirmation=None,
    )


@pytest.fixture
def unverified_binding(session_handle: SessionHandle) -> SessionBinding:
    """세션은 있으나 신원이 확정되지 않은 바인딩(상태 unavailable, 신원 없음)."""
    return SessionBinding(
        session=session_handle,
        state=SessionState.UNAVAILABLE,
        identity=None,
        transport_context_ref="ctx-eval",
        cancelled=False,
    )


@pytest.fixture
def cancelled_binding(
    run_key: RunKey, session_handle: SessionHandle, now: datetime
) -> SessionBinding:
    """verified 신원을 담았으나 취소된 바인딩."""
    identity = verified_identity(run_key, session_handle, "subject-eval", now)
    return SessionBinding(
        session=session_handle,
        state=SessionState.CONFIRMED,
        identity=identity,
        transport_context_ref="ctx-eval",
        cancelled=True,
    )


@pytest.fixture
def sessions_cancelled(
    run_key: RunKey, cancelled_binding: SessionBinding
) -> InMemorySessionBindings:
    store = InMemorySessionBindings()
    store.set_binding(run_key, cancelled_binding)
    return store


@pytest.fixture
def sessions_unverified(
    run_key: RunKey, unverified_binding: SessionBinding
) -> InMemorySessionBindings:
    store = InMemorySessionBindings()
    store.set_binding(run_key, unverified_binding)
    return store
