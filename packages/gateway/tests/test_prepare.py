"""`GatewayPort.prepare`와 view 구성의 단위 테스트. 네트워크·I/O 없이 실행한다."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from abc2lab_contracts.execution import (
    ExecutionRequest,
    PolicyIdentityStatus,
    PrivateHttpRequest,
)
from abc2lab_contracts.ports import SessionBindingReader
from abc2lab_contracts.primitives import (
    ParameterLocation,
    Purpose,
    ReasonCode,
    RequestParameter,
    ResultStatus,
    SourceVersion,
)
from abc2lab_contracts.registration import (
    CrossExecutionConfirmation,
    ExpectedAccess,
    ExpectedAccessPolicySnapshot,
    OperationRegistration,
    ResolutionState,
    ResourceBinding,
)
from abc2lab_contracts.session import SessionBinding, SessionHandle
from abc2lab_gateway.adapters import (
    GatewayPreparer,
    GatewayRegistration,
    InMemoryGatewayRegistrations,
    InMemoryPreparedHandleStore,
    build_owner_identity,
    build_policy_input,
    derive_identity_view,
    derive_policy_attributes,
)

# ---- view 구성 (순수 함수) ----


def test_build_policy_input_matches_registered_object_get(
    execution_request: ExecutionRequest,
    registration: GatewayRegistration,
    operation: OperationRegistration,
    resource_binding: ResourceBinding,
    confirmed_binding: SessionBinding,
    now: datetime,
) -> None:
    view = build_policy_input(
        execution_request,
        registration,
        operation,
        resource_binding,
        confirmed_binding,
        None,
        binding_id="binding-1",
        binding_issuer="gateway",
        expires_at=now + timedelta(minutes=1),
    )
    attributes = view.policy_attributes
    assert attributes.registered_path_matches is True
    assert attributes.parameters_match_registration is True
    assert attributes.parameter_names == ("order_id",)
    assert attributes.resource_ref == "res-order-1001"
    assert attributes.resource_binding_ref == "rb-order-1"
    assert attributes.resource_binding_revision == 4
    assert attributes.resource_owner_subject_ref == "subject-owner"
    assert attributes.provenance == operation.source
    assert view.identity_status is PolicyIdentityStatus.VERIFIED
    assert view.account_ref == "acct-eval"
    assert view.session_generation == 2
    assert view.subject_ref == "subject-eval"
    # 주입 snapshot은 그대로 실린다(policy가 원본과 전체 필드 재대조).
    assert view.scope == registration.scope
    assert view.profile == registration.profile
    assert view.budget == registration.budget


def test_path_mismatch_is_recorded_not_raised(
    execution_request: ExecutionRequest,
    registration: GatewayRegistration,
    operation: OperationRegistration,
    resource_binding: ResourceBinding,
    confirmed_binding: SessionBinding,
    now: datetime,
) -> None:
    # 실제 경로가 바인딩이 가리키는 자원과 다르면 불일치를 사실대로 남긴다(예외 아님).
    other = replace(execution_request, http=replace(execution_request.http, path="/orders/9999"))
    view = build_policy_input(
        other,
        registration,
        operation,
        resource_binding,
        confirmed_binding,
        None,
        binding_id="b",
        binding_issuer="gw",
        expires_at=now + timedelta(minutes=1),
    )
    assert view.policy_attributes.registered_path_matches is False


def test_method_mismatch_breaks_operation_match(
    operation: OperationRegistration,
    resource_binding: ResourceBinding,
    http: PrivateHttpRequest,
) -> None:
    attributes = derive_policy_attributes(replace(http, method="POST"), operation, resource_binding)
    assert attributes.registered_path_matches is False


def test_parameter_mismatch_is_recorded(
    operation: OperationRegistration,
    resource_binding: ResourceBinding,
    http: PrivateHttpRequest,
) -> None:
    # 실제 파라미터 값만 바뀌고 경로 문자열은 그대로인 요청. 경로는 바인딩 값(1001)으로 채워
    # 비교하므로 여전히 일치하지만, 파라미터 집합이 등록 바인딩과 달라 불일치로 남는다(독립 신호).
    changed = replace(
        http, parameters=(RequestParameter("order_id", ParameterLocation.PATH, "2002"),)
    )
    attributes = derive_policy_attributes(changed, operation, resource_binding)
    assert attributes.registered_path_matches is True
    assert attributes.parameters_match_registration is False


def test_no_binding_requires_no_params_and_static_path() -> None:
    health = OperationRegistration(
        source=SourceVersion(issuer="reg", source_ref="op-health", revision=1),
        operation_ref="op-health",
        allowed_purposes=(Purpose.OBSERVE,),
        auth_profile_ref=None,
        method="GET",
        origin="https://api.example.test",
        path_template="/health",
        resource_bindings=(),
    )
    request = PrivateHttpRequest(
        origin="https://api.example.test",
        method="GET",
        path="/health",
        parameters=(),
        timeout_ms=1000,
    )
    attributes = derive_policy_attributes(request, health, None)
    assert attributes.registered_path_matches is True
    assert attributes.parameters_match_registration is True
    assert attributes.resource_ref is None
    # 자리표시자 템플릿인데 바인딩이 없으면 경로를 대조할 수 없어 False다.
    placeholder = replace(health, path_template="/health/{id}")
    assert derive_policy_attributes(request, placeholder, None).registered_path_matches is False


def test_identity_anonymous_without_session() -> None:
    view = derive_identity_view(None)
    assert view.identity_status is PolicyIdentityStatus.ANONYMOUS
    assert view.account_ref is None
    assert view.session_generation is None
    assert view.subject_ref is None


def test_identity_unknown_keeps_account_but_hides_subject(
    unverified_binding: SessionBinding,
) -> None:
    view = derive_identity_view(unverified_binding)
    assert view.identity_status is PolicyIdentityStatus.UNKNOWN
    assert view.account_ref == "acct-eval"
    assert view.session_generation == 2
    assert view.identity_ref is None
    assert view.subject_ref is None


def test_owner_identity_built_when_verified(owner_binding: SessionBinding) -> None:
    owner = build_owner_identity(owner_binding)
    assert owner is not None
    assert owner.subject_ref == "subject-owner"
    assert owner.account_ref == "acct-owner"


def test_owner_identity_none_when_absent_or_unverified(
    unverified_binding: SessionBinding,
) -> None:
    assert build_owner_identity(None) is None
    assert build_owner_identity(unverified_binding) is None


# ---- 서비스 orchestration ----


@pytest.mark.asyncio
async def test_prepare_complete_returns_handle_and_view(
    preparer: GatewayPreparer,
    handles: InMemoryPreparedHandleStore,
    execution_request: ExecutionRequest,
    now: datetime,
) -> None:
    result = await preparer.prepare(execution_request)
    assert result.status is ResultStatus.COMPLETE
    assert result.policy_input is not None
    assert result.prepared_handle is not None
    assert result.policy_input.binding_id == "binding-fixed"
    assert result.policy_input.expires_at == now + timedelta(seconds=30)
    # 발급한 핸들은 저장소에서 원요청·view로 소비된다.
    prepared = handles.consume(execution_request.run_key, result.prepared_handle)
    assert prepared is not None
    assert prepared.request == execution_request
    assert prepared.policy_input == result.policy_input


@pytest.mark.asyncio
async def test_prepare_anonymous_session_is_complete(
    preparer: GatewayPreparer, execution_request: ExecutionRequest
) -> None:
    result = await preparer.prepare(replace(execution_request, session=None))
    assert result.status is ResultStatus.COMPLETE
    assert result.policy_input is not None
    assert result.policy_input.identity_status is PolicyIdentityStatus.ANONYMOUS
    assert result.policy_input.account_ref is None


@pytest.mark.asyncio
async def test_prepare_owner_identity_passes_through(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    owner_session_handle: SessionHandle,
) -> None:
    request = replace(
        execution_request, owner_session=owner_session_handle, purpose=Purpose.ACCESS_COMPARE
    )
    result = await preparer.prepare(request)
    assert result.status is ResultStatus.COMPLETE
    assert result.policy_input is not None
    owner = result.policy_input.owner_identity
    assert owner is not None
    assert owner.subject_ref == "subject-owner"


@pytest.mark.asyncio
async def test_prepare_unreadable_owner_stays_complete_without_owner_identity(
    preparer: GatewayPreparer,
    execution_request: ExecutionRequest,
    now: datetime,
) -> None:
    missing_owner = SessionHandle(
        session_ref="sess-missing-owner",
        run_key=execution_request.run_key,
        account_ref="acct-owner",
        generation=1,
        expires_at=now + timedelta(minutes=30),
    )
    request = replace(
        execution_request, owner_session=missing_owner, purpose=Purpose.ACCESS_COMPARE
    )
    result = await preparer.prepare(request)
    # 소유자 신원 확인 실패는 prepare를 실패시키지 않고 owner_identity를 비운다(policy가 막는다).
    assert result.status is ResultStatus.COMPLETE
    assert result.policy_input is not None
    assert result.policy_input.owner_identity is None


@pytest.mark.asyncio
async def test_prepare_expected_policy_and_cross_confirmation_pass_through(
    preparer: GatewayPreparer, execution_request: ExecutionRequest, now: datetime
) -> None:
    policy = ExpectedAccessPolicySnapshot(
        source=SourceVersion(issuer="reg", source_ref="eap", revision=1),
        policy_ref="eap-1",
        target_ref="target-1",
        environment_ref="env-1",
        resource_ref="res-order-1001",
        operation_ref="op-get-order",
        owner_subject_ref="subject-owner",
        evaluated_subject_ref="subject-eval",
        expected_access=ExpectedAccess.DENY,
        sharing=ResolutionState.RESOLVED_NONE,
        delegation=ResolutionState.RESOLVED_NONE,
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
    )
    confirmation = CrossExecutionConfirmation(
        source=SourceVersion(issuer="reg", source_ref="cross", revision=1),
        run_key=execution_request.run_key,
        resource_ref="res-order-1001",
        operation_ref="op-get-order",
        owner_account_ref="acct-owner",
        evaluated_account_ref="acct-eval",
        valid_until=now + timedelta(minutes=30),
    )
    request = replace(
        execution_request,
        purpose=Purpose.ACCESS_COMPARE,
        expected_policy=policy,
        cross_confirmation=confirmation,
    )
    result = await preparer.prepare(request)
    assert result.policy_input is not None
    assert result.policy_input.expected_policy == policy
    assert result.policy_input.cross_confirmation == confirmation


@pytest.mark.asyncio
async def test_prepare_missing_registration_fails(
    sessions: SessionBindingReader,
    handles: InMemoryPreparedHandleStore,
    execution_request: ExecutionRequest,
    now: datetime,
) -> None:
    empty = GatewayPreparer(
        InMemoryGatewayRegistrations(), sessions, handles, "gateway", clock=lambda: now
    )
    result = await empty.prepare(execution_request)
    assert result.status is ResultStatus.FAILED
    assert result.prepared_handle is None
    assert result.policy_input is None
    assert result.reason_codes == (ReasonCode.CONFIGURATION_MISSING,)


@pytest.mark.asyncio
async def test_prepare_scope_revision_mismatch_fails(
    preparer: GatewayPreparer, execution_request: ExecutionRequest
) -> None:
    result = await preparer.prepare(replace(execution_request, scope_revision=2))
    assert result.status is ResultStatus.FAILED
    assert result.reason_codes == (ReasonCode.REVISION_UNAVAILABLE,)


@pytest.mark.asyncio
async def test_prepare_profile_revision_mismatch_fails(
    preparer: GatewayPreparer, execution_request: ExecutionRequest
) -> None:
    result = await preparer.prepare(replace(execution_request, profile_revision=9))
    assert result.status is ResultStatus.FAILED
    assert result.reason_codes == (ReasonCode.REVISION_UNAVAILABLE,)


@pytest.mark.asyncio
async def test_prepare_unregistered_operation_fails(
    preparer: GatewayPreparer, execution_request: ExecutionRequest
) -> None:
    result = await preparer.prepare(replace(execution_request, operation_ref="op-unknown"))
    assert result.status is ResultStatus.FAILED
    assert result.reason_codes == (ReasonCode.NOT_FOUND,)


@pytest.mark.asyncio
async def test_prepare_operation_revision_mismatch_fails(
    preparer: GatewayPreparer, execution_request: ExecutionRequest
) -> None:
    result = await preparer.prepare(replace(execution_request, operation_revision=9))
    assert result.status is ResultStatus.FAILED
    assert result.reason_codes == (ReasonCode.REVISION_UNAVAILABLE,)


@pytest.mark.asyncio
async def test_prepare_unknown_resource_binding_fails(
    preparer: GatewayPreparer, execution_request: ExecutionRequest
) -> None:
    result = await preparer.prepare(replace(execution_request, resource_binding_ref="rb-unknown"))
    assert result.status is ResultStatus.FAILED
    assert result.reason_codes == (ReasonCode.NOT_FOUND,)


@pytest.mark.asyncio
async def test_prepare_resource_binding_revision_mismatch_fails(
    preparer: GatewayPreparer, execution_request: ExecutionRequest
) -> None:
    result = await preparer.prepare(replace(execution_request, resource_binding_revision=9))
    assert result.status is ResultStatus.FAILED
    assert result.reason_codes == (ReasonCode.REVISION_UNAVAILABLE,)


@pytest.mark.asyncio
async def test_prepare_unreadable_session_fails_closed(
    preparer: GatewayPreparer, execution_request: ExecutionRequest, now: datetime
) -> None:
    missing = SessionHandle(
        session_ref="sess-missing",
        run_key=execution_request.run_key,
        account_ref="acct-eval",
        generation=2,
        expires_at=now + timedelta(minutes=30),
    )
    result = await preparer.prepare(replace(execution_request, session=missing))
    assert result.status is ResultStatus.FAILED
    assert result.prepared_handle is None
    assert ReasonCode.SESSION_EXPIRED in result.reason_codes


@pytest.mark.asyncio
async def test_prepare_cancelled_session_fails_closed(
    registrations: InMemoryGatewayRegistrations,
    sessions_cancelled: SessionBindingReader,
    handles: InMemoryPreparedHandleStore,
    execution_request: ExecutionRequest,
    now: datetime,
) -> None:
    preparer = GatewayPreparer(
        registrations, sessions_cancelled, handles, "gateway", clock=lambda: now
    )
    result = await preparer.prepare(execution_request)
    assert result.status is ResultStatus.FAILED
    assert result.reason_codes == (ReasonCode.CANCELLED,)


@pytest.mark.asyncio
async def test_prepare_unverified_session_is_complete_but_unknown(
    registrations: InMemoryGatewayRegistrations,
    sessions_unverified: SessionBindingReader,
    handles: InMemoryPreparedHandleStore,
    execution_request: ExecutionRequest,
    now: datetime,
) -> None:
    preparer = GatewayPreparer(
        registrations, sessions_unverified, handles, "gateway", clock=lambda: now
    )
    result = await preparer.prepare(execution_request)
    assert result.status is ResultStatus.COMPLETE
    assert result.policy_input is not None
    assert result.policy_input.identity_status is PolicyIdentityStatus.UNKNOWN


@pytest.mark.asyncio
async def test_prepare_expired_configuration_fails(
    registrations: InMemoryGatewayRegistrations,
    preparer: GatewayPreparer,
    registration: GatewayRegistration,
    execution_request: ExecutionRequest,
    now: datetime,
) -> None:
    expired_scope = replace(registration.scope, valid_until=now)
    registrations.register(execution_request.run_key, replace(registration, scope=expired_scope))
    result = await preparer.prepare(execution_request)
    assert result.status is ResultStatus.FAILED
    assert result.reason_codes == (ReasonCode.SNAPSHOT_EXPIRED,)
