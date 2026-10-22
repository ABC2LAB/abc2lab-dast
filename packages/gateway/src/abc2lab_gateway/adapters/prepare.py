"""실제 요청에서 비밀 없는 `PolicyInput` view를 구성하는 순수 함수들이다.

gateway만 실제 http 요청(원문 경로·파라미터 값)을 보므로, 등록된 동작·자원 바인딩과의 구조 일치
여부를 여기서 계산해 view의 불리언 필드로만 남긴다. 값 자체는 view에 담지 않는다. 신원은 주입된
세션 바인딩 snapshot에서 유도하며, 없는 세션을 익명으로 승격하지 않는다(상태로 구분). policy가 이
view를 주입 원본과 재대조하므로(S1 §5) 각 필드를 등록과 정확히 대응시킨다. I/O·판정은 하지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from abc2lab_contracts.execution import (
    POLICY_INPUT_SCHEMA_VERSION,
    ExecutionRequest,
    PolicyAttributes,
    PolicyIdentityStatus,
    PolicyInput,
    PrivateHttpRequest,
)
from abc2lab_contracts.primitives import ParameterLocation, Ref
from abc2lab_contracts.registration import OperationRegistration, ResourceBinding
from abc2lab_contracts.session import IdentityBindingSummary, IdentityStatus, SessionBinding

from abc2lab_gateway.adapters.registration import GatewayRegistration

_PATH_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


@dataclass(frozen=True, slots=True)
class _IdentityView:
    """세션 바인딩에서 유도한 정책용 신원 축약. 검증 전에는 식별자를 비운다."""

    account_ref: Ref | None
    session_generation: int | None
    identity_ref: Ref | None
    subject_ref: Ref | None
    identity_status: PolicyIdentityStatus


def _expected_path(path_template: str, path_values: dict[str, str]) -> str | None:
    """등록 경로 템플릿의 `{name}` 자리를 등록 파라미터 값으로 채운다.

    대응 값이 없는 자리가 하나라도 있으면 None(대조 불가)을 돌려준다.
    """
    if any(name not in path_values for name in _PATH_PLACEHOLDER.findall(path_template)):
        return None
    return _PATH_PLACEHOLDER.sub(lambda match: path_values[match.group(1)], path_template)


def _request_matches_operation(
    http: PrivateHttpRequest,
    operation: OperationRegistration,
    resource_binding: ResourceBinding | None,
) -> bool:
    """실제 요청이 등록 동작의 origin·method·경로와 구조상 일치하는지 본다.

    경로는 자원 바인딩의 PATH 파라미터 값으로 템플릿을 채운 결과와 비교한다. 바인딩이 없으면
    자리표시자 없는 템플릿만 일치할 수 있다. 값은 view에 담지 않고 이 불리언만 남긴다.
    """
    if http.origin != operation.origin or http.method != operation.method:
        return False
    path_values: dict[str, str] = {}
    if resource_binding is not None:
        path_values = {
            parameter.name: parameter.value
            for parameter in resource_binding.parameters
            if parameter.location is ParameterLocation.PATH
        }
    expected = _expected_path(operation.path_template, path_values)
    return expected is not None and expected == http.path


def _parameters_match_registration(
    http: PrivateHttpRequest, resource_binding: ResourceBinding | None
) -> bool:
    """실제 파라미터가 등록 바인딩과 정확히 대응하는지 본다.

    자원 바인딩을 참조하면 (name·location·value) 집합이 등록 바인딩과 같아야 한다. 바인딩이 없는
    요청은 파라미터가 없어야 한다(비객체 요청).
    """
    if resource_binding is None:
        return len(http.parameters) == 0
    return frozenset(http.parameters) == frozenset(resource_binding.parameters)


def derive_policy_attributes(
    http: PrivateHttpRequest,
    operation: OperationRegistration,
    resource_binding: ResourceBinding | None,
) -> PolicyAttributes:
    """실제 요청과 등록을 대조해 값 없는 구조 view를 만든다."""
    return PolicyAttributes(
        registered_path_matches=_request_matches_operation(http, operation, resource_binding),
        parameter_names=tuple(parameter.name for parameter in http.parameters),
        parameters_match_registration=_parameters_match_registration(http, resource_binding),
        resource_ref=resource_binding.resource_ref if resource_binding else None,
        resource_binding_ref=(resource_binding.resource_binding_ref if resource_binding else None),
        resource_binding_revision=(resource_binding.source.revision if resource_binding else None),
        resource_owner_subject_ref=(
            resource_binding.owner_subject_ref if resource_binding else None
        ),
        provenance=operation.source,
    )


def derive_identity_view(binding: SessionBinding | None) -> _IdentityView:
    """세션 바인딩에서 정책용 신원 축약을 만든다.

    세션이 없으면 익명, 바인딩이 검증된 신원을 담으면 verified(식별자 포함), 그 외에는 unknown으로
    두되 세션 핸들이 아는 계정·generation은 남긴다. 없는 신원을 verified로 올리지 않는다.
    """
    if binding is None:
        return _IdentityView(None, None, None, None, PolicyIdentityStatus.ANONYMOUS)
    session = binding.session
    identity = binding.identity
    if identity is not None and identity.status is IdentityStatus.VERIFIED:
        return _IdentityView(
            account_ref=session.account_ref,
            session_generation=session.generation,
            identity_ref=identity.identity_ref,
            subject_ref=identity.subject_ref,
            identity_status=PolicyIdentityStatus.VERIFIED,
        )
    return _IdentityView(
        account_ref=session.account_ref,
        session_generation=session.generation,
        identity_ref=None,
        subject_ref=None,
        identity_status=PolicyIdentityStatus.UNKNOWN,
    )


def build_owner_identity(owner_binding: SessionBinding | None) -> IdentityBindingSummary | None:
    """자원 소유자 세션 바인딩에서 교차 실행용 소유자 신원 view를 만든다.

    검증된 신원 바인딩일 때만 요약을 낸다. 미검증·부재면 None이며, policy가 교차 검사에서
    소유자 신원 불명으로 막는다.
    """
    if owner_binding is None or owner_binding.identity is None:
        return None
    identity = owner_binding.identity
    if identity.status is not IdentityStatus.VERIFIED:
        return None
    # verified IdentityResult는 identity_ref·subject_ref·verified_at·valid_until이 모두 있다.
    assert identity.identity_ref is not None
    assert identity.subject_ref is not None
    assert identity.verified_at is not None
    assert identity.valid_until is not None
    return IdentityBindingSummary(
        identity_ref=identity.identity_ref,
        session_ref=identity.session_ref,
        account_ref=identity.account_ref,
        subject_ref=identity.subject_ref,
        generation=identity.generation,
        verified_at=identity.verified_at,
        valid_until=identity.valid_until,
    )


def build_policy_input(
    request: ExecutionRequest,
    registration: GatewayRegistration,
    operation: OperationRegistration,
    resource_binding: ResourceBinding | None,
    binding: SessionBinding | None,
    owner_binding: SessionBinding | None,
    *,
    binding_id: Ref,
    binding_issuer: Ref,
    expires_at: datetime,
) -> PolicyInput:
    """해석된 등록·세션 바인딩에서 비밀 없는 `PolicyInput` view를 조립한다.

    scope·profile·budget은 주입 원본을 그대로 싣고, 구조 일치·자원 바인딩·신원은 유도한 값으로
    채운다. expected_policy·cross_confirmation은 요청값을 그대로 전달하며 policy가 주입 원본과
    재대조한다.
    """
    identity = derive_identity_view(binding)
    return PolicyInput(
        schema_version=POLICY_INPUT_SCHEMA_VERSION,
        run_key=request.run_key,
        request_ref=request.request_ref,
        binding_id=binding_id,
        binding_issuer=binding_issuer,
        expires_at=expires_at,
        origin=request.http.origin,
        method=request.http.method,
        operation_ref=request.operation_ref,
        operation_revision=request.operation_revision,
        purpose=request.purpose,
        policy_attributes=derive_policy_attributes(request.http, operation, resource_binding),
        account_ref=identity.account_ref,
        session_generation=identity.session_generation,
        identity_ref=identity.identity_ref,
        subject_ref=identity.subject_ref,
        identity_status=identity.identity_status,
        owner_identity=build_owner_identity(owner_binding),
        scope=registration.scope,
        profile=registration.profile,
        budget=registration.budget,
        expected_policy=request.expected_policy,
        cross_confirmation=request.cross_confirmation,
    )
