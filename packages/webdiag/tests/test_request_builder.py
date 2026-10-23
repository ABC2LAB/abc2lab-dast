"""등록값→ExecutionRequest 구성과 경로 치환·목적 검증을 검사한다."""

import pytest
from abc2lab_contracts.primitives import (
    ParameterLocation,
    Purpose,
    RequestParameter,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.registration import OperationRegistration, ResourceBinding
from abc2lab_webdiag.core.request_builder import (
    ExecutionPlan,
    build_execution_request,
    resolve_path,
)

_RUN = RunKey(
    organization_ref="org-1", target_ref="target-1", environment_ref="env-1", run_ref="run-1"
)
_SRC = SourceVersion(issuer="issuer-1", source_ref="src-1", revision=3)


def _operation(
    *,
    purposes: tuple[Purpose, ...],
    path_template: str,
    auth_profile_ref: str | None,
) -> OperationRegistration:
    return OperationRegistration(
        source=_SRC,
        operation_ref="op-1",
        allowed_purposes=purposes,
        auth_profile_ref=auth_profile_ref,
        method="GET",
        origin="https://app.example",
        path_template=path_template,
        resource_bindings=(),
    )


def _binding() -> ResourceBinding:
    return ResourceBinding(
        resource_binding_ref="rb-1",
        source=_SRC,
        resource_ref="resource-1",
        owner_subject_ref="subject-a",
        parameters=(RequestParameter(name="id", location=ParameterLocation.PATH, value="42"),),
    )


def _plan(**overrides: object) -> ExecutionPlan:
    base: dict[str, object] = {
        "run_key": _RUN,
        "request_ref": "req-1",
        "operation": _operation(
            purposes=(Purpose.OBSERVE,), path_template="/orders/{id}", auth_profile_ref=None
        ),
        "purpose": Purpose.OBSERVE,
        "scope_revision": 2,
        "profile_revision": 5,
        "timeout_ms": 5000,
        "resource_binding": _binding(),
    }
    base.update(overrides)
    return ExecutionPlan(**base)  # type: ignore[arg-type]


def test_builds_observe_request_with_resolved_path() -> None:
    """자원 바인딩 path 파라미터가 템플릿에 치환되고 등록 revision이 실린다."""
    request = build_execution_request(_plan())
    assert request.http.path == "/orders/42"
    assert request.http.origin == "https://app.example"
    assert request.operation_revision == 3
    assert request.resource_ref == "resource-1"
    assert request.resource_binding_ref == "rb-1"
    assert request.resource_binding_revision == 3
    assert request.scope_revision == 2


def test_builds_authenticate_request_without_resource() -> None:
    """인증 동작은 자원 바인딩 없이 고정 경로를 구성한다."""
    plan = _plan(
        operation=_operation(
            purposes=(Purpose.AUTHENTICATE,), path_template="/login", auth_profile_ref="auth-1"
        ),
        purpose=Purpose.AUTHENTICATE,
        resource_binding=None,
    )
    request = build_execution_request(plan)
    assert request.http.path == "/login"
    assert request.http.parameters == ()
    assert request.resource_ref is None
    assert request.purpose is Purpose.AUTHENTICATE


def test_purpose_not_allowed_is_rejected() -> None:
    """등록 operation이 허용하지 않은 목적은 거부한다."""
    plan = _plan(purpose=Purpose.ACCESS_COMPARE)
    with pytest.raises(ValueError, match="purpose not allowed"):
        build_execution_request(plan)


def test_resolve_path_substitutes_only_path_params() -> None:
    """path 파라미터만 치환하고 query 파라미터는 경로에 넣지 않는다."""
    params = (
        RequestParameter(name="id", location=ParameterLocation.PATH, value="7"),
        RequestParameter(name="q", location=ParameterLocation.QUERY, value="x"),
    )
    assert resolve_path("/orders/{id}", params) == "/orders/7"


def test_resolve_path_rejects_unresolved_placeholder() -> None:
    """치환되지 않은 placeholder가 남으면 거부한다."""
    with pytest.raises(ValueError, match="unresolved path template"):
        resolve_path("/orders/{id}", ())


def test_resolve_path_rejects_param_absent_from_template() -> None:
    """템플릿에 없는 path 파라미터는 거부한다."""
    params = (RequestParameter(name="missing", location=ParameterLocation.PATH, value="1"),)
    with pytest.raises(ValueError, match="path parameter not in template"):
        resolve_path("/login", params)
