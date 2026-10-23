"""`GatewayPort.prepare` 구현: 등록·세션 해석 → 비밀 없는 view 구성 → 단일 소비 핸들 발급.

전송은 하지 않는다. 등록은 app이 run별로 주입한 불변 snapshot에서만 오며, 세션 신원은 주입된 동기
바인딩 reader에서 읽는다. 해석 불가·revision 불일치·만료·취소·세션 불명이면 핸들·view 없이 failed를
반환한다(fail-closed). 실제 요청(원문 경로·파라미터 값·세션)은 view에 담지 않고 핸들 저장소의 실행
메모리에만 보관해 execute가 소비한다. 전송 상태를 바꾸지 않는다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from abc2lab_contracts.execution import ExecutionRequest, PrepareResult
from abc2lab_contracts.ports import SessionBindingReader
from abc2lab_contracts.primitives import ReasonCode, Ref, ResultStatus, RunKey
from abc2lab_contracts.registration import (
    ExecutionProfileSnapshot,
    OperationRegistration,
    ResourceBinding,
    ScopeSnapshot,
)
from abc2lab_contracts.session import SessionBinding, SessionHandle

from abc2lab_gateway.adapters.handles import PreparedHandleStore, PreparedRequest
from abc2lab_gateway.adapters.prepare import build_policy_input
from abc2lab_gateway.adapters.registration import GatewayRegistration, GatewayRegistrationSource

_LOGGER = logging.getLogger(__name__)

# 준비 핸들은 짧게만 유효하다. execute가 곧바로 소비하며, 구성·세션 유효기간과 함께
# 최솟값으로 묶인다.
_PREPARED_HANDLE_TTL = timedelta(seconds=30)


class PrepareError(Exception):
    """준비를 fail-closed로 끝내는 내부 신호. 사유 코드를 동반한다."""

    def __init__(self, *reasons: ReasonCode) -> None:
        super().__init__(reasons)
        self.reasons = reasons


def new_binding_id() -> Ref:
    """다른 준비 요청과 겹치지 않는 새 바인딩 식별자를 만든다."""
    return f"gateway-binding-{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _resolve_view_expiry(
    now: datetime,
    scope: ScopeSnapshot,
    profile: ExecutionProfileSnapshot,
    session: SessionHandle | None,
) -> datetime:
    """view·핸들 유효기간을 구성·세션 유효기간과 핸들 TTL의 최솟값으로 묶는다."""
    bounds = [scope.valid_until, profile.valid_until, now + _PREPARED_HANDLE_TTL]
    if session is not None:
        bounds.append(session.expires_at)
    return min(bounds)


class GatewayPreparer:
    """전송 없이 view와 단일 소비 핸들을 준비하는 `GatewayPort.prepare` 구현."""

    def __init__(
        self,
        registrations: GatewayRegistrationSource,
        sessions: SessionBindingReader,
        handles: PreparedHandleStore,
        binding_issuer: Ref,
        *,
        clock: Callable[[], datetime] = _utc_now,
        binding_id_factory: Callable[[], Ref] = new_binding_id,
    ) -> None:
        self._registrations = registrations
        self._sessions = sessions
        self._handles = handles
        self._binding_issuer = binding_issuer
        self._clock = clock
        self._new_binding_id = binding_id_factory

    async def prepare(self, request: ExecutionRequest) -> PrepareResult:
        """전송 없이 단일 소비 핸들과 정책 view를 준비한다.

        Returns:
            해석·구성에 성공하면 핸들과 view를 담은 complete, 해석 불가·revision 불일치·만료·취소·
            세션 불명이면 핸들·view 없는 failed다. 실행 가능한 준비를 조건 미달로 발급하지 않는다.
        """
        try:
            registration = self._resolve_registration(request)
            operation, resource_binding = self._resolve_operation(request, registration)
            now = self._clock()
            binding = self._read_session(request.run_key, request.session)
            owner_binding = self._read_owner_session(request.run_key, request.owner_session)
            expires_at = _resolve_view_expiry(
                now, registration.scope, registration.profile, request.session
            )
            if expires_at <= now:
                raise PrepareError(ReasonCode.SNAPSHOT_EXPIRED)
        except PrepareError as error:
            return self._failed(request, error.reasons)

        policy_input = build_policy_input(
            request,
            registration,
            operation,
            resource_binding,
            binding,
            owner_binding,
            binding_id=self._new_binding_id(),
            binding_issuer=self._binding_issuer,
            expires_at=expires_at,
        )
        handle = self._handles.allocate(
            PreparedRequest(
                run_key=request.run_key,
                request_ref=request.request_ref,
                binding_id=policy_input.binding_id,
                policy_input=policy_input,
                request=request,
                expires_at=expires_at,
                auth_profile_ref=operation.auth_profile_ref,
            )
        )
        _LOGGER.info(
            "gateway prepared request: run=%s request=%s operation=%s",
            request.run_key.run_ref,
            request.request_ref,
            request.operation_ref,
        )
        return PrepareResult(request.run_key, ResultStatus.COMPLETE, handle, policy_input, ())

    def _resolve_registration(self, request: ExecutionRequest) -> GatewayRegistration:
        """run 등록을 읽고 scope·profile revision이 요청과 맞는지 확인한다."""
        registration = self._registrations.registration_for(request.run_key)
        if registration is None:
            raise PrepareError(ReasonCode.CONFIGURATION_MISSING)
        if request.scope_revision != registration.scope.source.revision:
            raise PrepareError(ReasonCode.REVISION_UNAVAILABLE)
        if request.profile_revision != registration.profile.source.revision:
            raise PrepareError(ReasonCode.REVISION_UNAVAILABLE)
        return registration

    def _resolve_operation(
        self, request: ExecutionRequest, registration: GatewayRegistration
    ) -> tuple[OperationRegistration, ResourceBinding | None]:
        """요청 동작과 자원 바인딩을 등록 원본에서 revision까지 맞춰 해석한다."""
        operation = next(
            (
                item
                for item in registration.operations
                if item.operation_ref == request.operation_ref
            ),
            None,
        )
        if operation is None:
            raise PrepareError(ReasonCode.NOT_FOUND)
        if operation.source.revision != request.operation_revision:
            raise PrepareError(ReasonCode.REVISION_UNAVAILABLE)
        if request.resource_binding_ref is None:
            return operation, None
        binding = next(
            (
                item
                for item in operation.resource_bindings
                if item.resource_binding_ref == request.resource_binding_ref
            ),
            None,
        )
        if binding is None:
            raise PrepareError(ReasonCode.NOT_FOUND)
        if binding.source.revision != request.resource_binding_revision:
            raise PrepareError(ReasonCode.REVISION_UNAVAILABLE)
        return operation, binding

    def _read_session(
        self, run_key: RunKey, session: SessionHandle | None
    ) -> SessionBinding | None:
        """요청 세션의 바인딩을 읽는다. 없는 세션은 익명이고, 불명·취소는 fail-closed다."""
        if session is None:
            return None
        result = self._sessions.read_session_binding(run_key, session.session_ref)
        if result.status is not ResultStatus.COMPLETE or result.binding is None:
            reasons = result.reason_codes or (ReasonCode.INTERNAL_ERROR,)
            raise PrepareError(*reasons)
        if result.binding.cancelled:
            raise PrepareError(ReasonCode.CANCELLED)
        return result.binding

    def _read_owner_session(
        self, run_key: RunKey, owner_session: SessionHandle | None
    ) -> SessionBinding | None:
        """자원 소유자 세션 바인딩을 읽는다. 불명·취소는 소유자 신원 부재로 두고 실패시키지 않는다.

        교차 실행 소유자 신원을 확인할 수 없으면 view의 owner_identity가 None이 되고, policy가
        교차 검사에서 소유자 신원 불명으로 막는다(gateway는 판정하지 않는다).
        """
        if owner_session is None:
            return None
        result = self._sessions.read_session_binding(run_key, owner_session.session_ref)
        if result.status is not ResultStatus.COMPLETE or result.binding is None:
            return None
        if result.binding.cancelled:
            return None
        return result.binding

    def _failed(self, request: ExecutionRequest, reasons: tuple[ReasonCode, ...]) -> PrepareResult:
        """핸들·view 없이 사유만 담은 failed 결과를 만든다. 사유 중복은 제거한다."""
        deduped = tuple(dict.fromkeys(reasons))
        _LOGGER.error(
            "gateway prepare failed: run=%s request=%s reasons=%s",
            request.run_key.run_ref,
            request.request_ref,
            deduped,
        )
        return PrepareResult(request.run_key, ResultStatus.FAILED, None, None, deduped)
