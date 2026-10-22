"""준비 단계가 발급하는 단일 소비 요청 핸들과 같은 loop의 동기 저장소다.

prepare는 비밀 없는 `PolicyInput` view를 발행하되 실제 요청(원문 경로·파라미터 값·세션)은 공개하지
않고 이 저장소의 실행 메모리에만 보관한다. execute가 핸들로 한 번만 꺼내 소비하며, 만료·소비·run
불일치 핸들은 되돌려주지 않는다. 핸들 ref만 공개 계약을 오가고 보관 값은 로그·직렬화에 넣지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from abc2lab_contracts.execution import ExecutionRequest, PolicyInput, PreparedRequestHandle
from abc2lab_contracts.primitives import Ref, RunKey


@dataclass(frozen=True, slots=True, repr=False)
class PreparedRequest:
    """실행 메모리에만 두는 준비 결과. 원문 요청과 발행한 view·만료를 함께 묶는다."""

    run_key: RunKey
    request_ref: Ref
    binding_id: Ref
    policy_input: PolicyInput
    request: ExecutionRequest
    expires_at: datetime


class PreparedHandleStore(Protocol):
    """준비 요청을 보관하고 핸들로 한 번만 소비시키는 포트."""

    def allocate(self, prepared: PreparedRequest) -> PreparedRequestHandle:
        """새 단일 소비 핸들을 발급하고 준비 요청을 보관한다."""
        ...

    def consume(self, run_key: RunKey, handle: PreparedRequestHandle) -> PreparedRequest | None:
        """핸들을 한 번만 소비한다. 없거나 소비됨·만료·run 불일치면 None."""
        ...


def new_prepared_handle() -> PreparedRequestHandle:
    """다른 준비 요청과 겹치지 않는 새 핸들 ref를 만든다."""
    return f"gateway-prepared-{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InMemoryPreparedHandleStore:
    """유한 메모리의 단일 소비 핸들 저장소. 소비·만료 시 참조를 정리한다."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = _utc_now,
        handle_factory: Callable[[], PreparedRequestHandle] = new_prepared_handle,
    ) -> None:
        # clock/handle_factory는 테스트 주입용이다.
        self._clock = clock
        self._new_handle = handle_factory
        self._by_handle: dict[PreparedRequestHandle, PreparedRequest] = {}

    def allocate(self, prepared: PreparedRequest) -> PreparedRequestHandle:
        """새 핸들을 발급해 준비 요청을 보관한다."""
        handle = self._new_handle()
        self._by_handle[handle] = prepared
        return handle

    def consume(self, run_key: RunKey, handle: PreparedRequestHandle) -> PreparedRequest | None:
        """핸들을 한 번만 소비한다.

        run이 다르면 다른 run의 핸들이므로 보관한 채 None을 돌려준다. 소비됨·만료는 참조를 지우고
        None을 돌려준다. 유효하면 보관을 지우고(단일 소비) 준비 요청을 반환한다.
        """
        prepared = self._by_handle.get(handle)
        if prepared is None:
            return None
        if prepared.run_key != run_key:
            return None
        del self._by_handle[handle]
        now = self._clock()
        if now >= prepared.expires_at:
            return None
        return prepared
