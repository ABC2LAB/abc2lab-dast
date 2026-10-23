"""등록 OperationRegistration에서 Gateway용 ExecutionRequest를 구성한다(순수).

WebDiag는 app이 주입한 등록 값으로 실제 요청을 구성하고, Gateway가 독립적으로 재검증한다.
비밀·인증 값은 여기 들어가지 않는다(Gateway 내부에서 결합). purpose는 등록 operation이
허용한 범위여야 하며, 목적만 바꿔 다른 동작을 허용받을 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass

from abc2lab_contracts.execution import ExecutionRequest, PrivateHttpRequest
from abc2lab_contracts.primitives import (
    ParameterLocation,
    Purpose,
    Ref,
    RequestParameter,
    Revision,
    RunKey,
)
from abc2lab_contracts.registration import (
    CrossExecutionConfirmation,
    ExpectedAccessPolicySnapshot,
    OperationRegistration,
    ResourceBinding,
)
from abc2lab_contracts.session import SessionHandle


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """ExecutionRequest 구성에 함께 움직이는 등록·세션·목적 값을 묶는다."""

    run_key: RunKey
    request_ref: Ref
    operation: OperationRegistration
    purpose: Purpose
    scope_revision: Revision
    profile_revision: Revision
    timeout_ms: int
    session: SessionHandle | None = None
    owner_session: SessionHandle | None = None
    resource_binding: ResourceBinding | None = None
    expected_policy: ExpectedAccessPolicySnapshot | None = None
    cross_confirmation: CrossExecutionConfirmation | None = None


def resolve_path(path_template: str, parameters: tuple[RequestParameter, ...]) -> str:
    """path-location 파라미터를 템플릿에 치환한다. 미치환 placeholder는 거부한다."""
    path = path_template
    for parameter in parameters:
        if parameter.location is ParameterLocation.PATH:
            placeholder = "{" + parameter.name + "}"
            if placeholder not in path:
                raise ValueError(f"path parameter not in template: {parameter.name}")
            path = path.replace(placeholder, parameter.value)
    if "{" in path or "}" in path:
        raise ValueError("unresolved path template placeholder")
    return path


def build_execution_request(plan: ExecutionPlan) -> ExecutionRequest:
    """등록 operation·자원 바인딩에서 비밀 없는 ExecutionRequest를 구성한다."""
    if plan.purpose not in plan.operation.allowed_purposes:
        raise ValueError("purpose not allowed for operation")
    binding = plan.resource_binding
    parameters = binding.parameters if binding is not None else ()
    return ExecutionRequest(
        run_key=plan.run_key,
        request_ref=plan.request_ref,
        operation_ref=plan.operation.operation_ref,
        operation_revision=plan.operation.source.revision,
        resource_ref=binding.resource_ref if binding is not None else None,
        resource_binding_ref=binding.resource_binding_ref if binding is not None else None,
        resource_binding_revision=binding.source.revision if binding is not None else None,
        purpose=plan.purpose,
        http=PrivateHttpRequest(
            origin=plan.operation.origin,
            method=plan.operation.method,
            path=resolve_path(plan.operation.path_template, parameters),
            parameters=parameters,
            timeout_ms=plan.timeout_ms,
        ),
        session=plan.session,
        owner_session=plan.owner_session,
        scope_revision=plan.scope_revision,
        profile_revision=plan.profile_revision,
        expected_policy=plan.expected_policy,
        cross_confirmation=plan.cross_confirmation,
    )
