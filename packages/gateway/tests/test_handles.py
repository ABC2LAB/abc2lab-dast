"""준비 핸들 저장소의 단위 테스트. 단일 소비·만료·run 범위를 확인한다. I/O 없이 실행한다."""

from __future__ import annotations

from datetime import datetime, timedelta

from abc2lab_contracts.execution import ExecutionRequest
from abc2lab_contracts.primitives import RunKey
from abc2lab_contracts.registration import OperationRegistration, ResourceBinding
from abc2lab_contracts.session import SessionBinding
from abc2lab_gateway.adapters import (
    GatewayRegistration,
    InMemoryPreparedHandleStore,
    PreparedRequest,
    build_policy_input,
)


def _prepared(
    request: ExecutionRequest,
    registration: GatewayRegistration,
    operation: OperationRegistration,
    resource_binding: ResourceBinding,
    binding: SessionBinding,
    expires_at: datetime,
) -> PreparedRequest:
    policy_input = build_policy_input(
        request,
        registration,
        operation,
        resource_binding,
        binding,
        None,
        binding_id="binding-1",
        binding_issuer="gateway",
        expires_at=expires_at,
    )
    return PreparedRequest(
        run_key=request.run_key,
        request_ref=request.request_ref,
        binding_id="binding-1",
        policy_input=policy_input,
        request=request,
        expires_at=expires_at,
    )


def test_allocate_then_consume_returns_prepared(
    execution_request: ExecutionRequest,
    registration: GatewayRegistration,
    operation: OperationRegistration,
    resource_binding: ResourceBinding,
    confirmed_binding: SessionBinding,
    now: datetime,
) -> None:
    store = InMemoryPreparedHandleStore(clock=lambda: now)
    prepared = _prepared(
        execution_request,
        registration,
        operation,
        resource_binding,
        confirmed_binding,
        now + timedelta(minutes=1),
    )
    handle = store.allocate(prepared)
    assert store.consume(execution_request.run_key, handle) is prepared


def test_consume_is_single_use(
    execution_request: ExecutionRequest,
    registration: GatewayRegistration,
    operation: OperationRegistration,
    resource_binding: ResourceBinding,
    confirmed_binding: SessionBinding,
    now: datetime,
) -> None:
    store = InMemoryPreparedHandleStore(clock=lambda: now)
    prepared = _prepared(
        execution_request,
        registration,
        operation,
        resource_binding,
        confirmed_binding,
        now + timedelta(minutes=1),
    )
    handle = store.allocate(prepared)
    assert store.consume(execution_request.run_key, handle) is prepared
    assert store.consume(execution_request.run_key, handle) is None


def test_consume_unknown_handle_is_none(run_key: RunKey, now: datetime) -> None:
    store = InMemoryPreparedHandleStore(clock=lambda: now)
    assert store.consume(run_key, "missing") is None


def test_consume_rejects_foreign_run_and_keeps_handle(
    execution_request: ExecutionRequest,
    registration: GatewayRegistration,
    operation: OperationRegistration,
    resource_binding: ResourceBinding,
    confirmed_binding: SessionBinding,
    now: datetime,
) -> None:
    store = InMemoryPreparedHandleStore(clock=lambda: now)
    prepared = _prepared(
        execution_request,
        registration,
        operation,
        resource_binding,
        confirmed_binding,
        now + timedelta(minutes=1),
    )
    handle = store.allocate(prepared)
    foreign = RunKey("org-x", "tgt-x", "env-x", "run-x")
    assert store.consume(foreign, handle) is None
    # 다른 run은 소비하지 못하므로 올바른 run은 여전히 소비할 수 있다.
    assert store.consume(execution_request.run_key, handle) is prepared


def test_consume_rejects_expired_handle(
    execution_request: ExecutionRequest,
    registration: GatewayRegistration,
    operation: OperationRegistration,
    resource_binding: ResourceBinding,
    confirmed_binding: SessionBinding,
    now: datetime,
) -> None:
    store = InMemoryPreparedHandleStore(clock=lambda: now)
    # expires_at == now 이므로 이미 만료다.
    prepared = _prepared(
        execution_request, registration, operation, resource_binding, confirmed_binding, now
    )
    handle = store.allocate(prepared)
    assert store.consume(execution_request.run_key, handle) is None
    # 만료 핸들은 정리되어 재조회도 None이다.
    assert store.consume(execution_request.run_key, handle) is None
