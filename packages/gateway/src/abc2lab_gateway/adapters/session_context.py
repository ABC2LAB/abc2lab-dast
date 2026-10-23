"""gateway가 소유하는 실행 전용 세션 context 제공자(`SessionContextPort`).

로그인·전송 없이 격리된 transport context만 할당·정리한다(§4·아키 §8). context 발급은 요청 계정의
등록된 인증 프로필에 묶여, 계정 A가 계정 B의 auth profile로 context를 여는 스푸핑을 막는다. 같은
(run, session, generation) 반복 open은 멱등이다. 공유 계약이 아니라 app이 주입하는 gateway 내부
포트이며, 자격 증명·원문은 결과·로그·repr에 넣지 않는다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from abc2lab_contracts.primitives import CloseResult, ReasonCode, Ref, ResultStatus, RunKey
from abc2lab_contracts.registration import AccountRegistration
from abc2lab_contracts.session import (
    SessionContextCloseRequest,
    SessionContextRequest,
    SessionContextResult,
)

_LOGGER = logging.getLogger(__name__)


class AccountRegistrationSource(Protocol):
    """run별 계정 등록 정보를 읽는 포트. registration 원본과 같은 출처로 app이 먹인다."""

    def account_registration(self, run_key: RunKey, account_ref: Ref) -> AccountRegistration | None:
        """등록된 계정이면 그 등록 정보를, 없으면 None을 돌려준다."""
        ...


class InMemoryAccountRegistrations:
    """흐름 테스트용 비내구 계정 등록 저장소."""

    def __init__(self) -> None:
        self._by_account: dict[tuple[RunKey, Ref], AccountRegistration] = {}

    def register(self, run_key: RunKey, registration: AccountRegistration) -> None:
        """계정 등록을 저장한다."""
        self._by_account[(run_key, registration.account_ref)] = registration

    def account_registration(self, run_key: RunKey, account_ref: Ref) -> AccountRegistration | None:
        """등록된 계정 정보를 반환한다."""
        return self._by_account.get((run_key, account_ref))


@dataclass(frozen=True, slots=True, repr=False)
class _Context:
    """할당된 실행 context의 내부 기록. 비밀은 담지 않는다."""

    run_key: RunKey
    session_ref: Ref
    account_ref: Ref
    generation: int
    auth_profile_ref: Ref


def new_transport_context_ref() -> Ref:
    """다른 context와 겹치지 않는 새 transport context 참조를 만든다."""
    return f"gateway-context-{uuid4().hex}"


class GatewaySessionContexts:
    """격리 transport context를 열고 닫는 `SessionContextPort` 제공자."""

    def __init__(
        self,
        accounts: AccountRegistrationSource,
        *,
        context_factory: Callable[[], Ref] = new_transport_context_ref,
    ) -> None:
        self._accounts = accounts
        self._new_context = context_factory
        # (run, session_ref, generation) → context_ref: 멱등 재사용 조회용.
        self._by_session: dict[tuple[RunKey, Ref, int], Ref] = {}
        # context_ref → 기록: close·격리 확인용.
        self._by_context: dict[Ref, _Context] = {}

    async def open_session_context(self, request: SessionContextRequest) -> SessionContextResult:
        """계정 스코프 검증 후 격리 context를 할당한다(멱등). 로그인·전송은 하지 않는다."""
        registration = self._accounts.account_registration(request.run_key, request.account_ref)
        if registration is None or registration.auth_profile_ref != request.auth_profile_ref:
            # 미등록 계정·불일치 프로필. 계정에 묶지 않은 membership 허용은 스푸핑이라 거부한다.
            _LOGGER.warning(
                "gateway session context denied: run=%s account=%s",
                request.run_key.run_ref,
                request.account_ref,
            )
            return SessionContextResult(
                request.run_key, ResultStatus.FAILED, None, (ReasonCode.CONFIGURATION_MISSING,)
            )
        key = (request.run_key, request.session_ref, request.generation)
        existing = self._by_session.get(key)
        if existing is not None:
            # 같은 세션·generation 반복 open은 기존 context를 그대로 돌려준다(§4 멱등).
            return SessionContextResult(request.run_key, ResultStatus.COMPLETE, existing, ())
        context_ref = self._new_context()
        self._by_session[key] = context_ref
        self._by_context[context_ref] = _Context(
            run_key=request.run_key,
            session_ref=request.session_ref,
            account_ref=request.account_ref,
            generation=request.generation,
            auth_profile_ref=request.auth_profile_ref,
        )
        return SessionContextResult(request.run_key, ResultStatus.COMPLETE, context_ref, ())

    async def close_session_context(self, request: SessionContextCloseRequest) -> CloseResult:
        """context 참조를 정리하고 재사용을 막는다. 없는 ref는 멱등 완료다."""
        context = self._by_context.get(request.transport_context_ref)
        if context is not None and context.run_key == request.run_key:
            del self._by_context[request.transport_context_ref]
            self._by_session.pop((context.run_key, context.session_ref, context.generation), None)
        return CloseResult(request.run_key, ResultStatus.COMPLETE, ())
