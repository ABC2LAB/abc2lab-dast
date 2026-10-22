"""세션 context 생명주기 orchestration — 전송 없이 격리 context를 열고 닫는다.

Gateway의 ``SessionContextPort``로 격리 context만 할당받아 AUTHENTICATING 바인딩을 발행하고,
종료 시 먼저 바인딩을 terminal로 바꾼 뒤 context를 닫는다(§4). 로그인·주체 확인·관찰의
실제 전송 cycle은 후속 슬라이스(run_request·authenticate·identify)에서 더한다. 이 모듈은
await 사이에 상태 저장소를 원자 교체로만 갱신하고 비밀·원문을 다루지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from abc2lab_contracts.ports import SessionContextPort
from abc2lab_contracts.primitives import CloseResult, ReasonCode, Ref, ResultStatus, RunKey, UtcTime
from abc2lab_contracts.session import (
    SessionBinding,
    SessionContextCloseRequest,
    SessionContextRequest,
    SessionHandle,
    SessionState,
)

from abc2lab_webdiag.core.session_states import ensure_transition
from abc2lab_webdiag.core.session_store import SessionBindingStore


@dataclass(frozen=True, slots=True)
class SessionOpenOutcome:
    """context 할당·바인딩 발행 결과. 성공은 ``binding``이 존재할 때다."""

    binding: SessionBinding | None
    reason_codes: tuple[ReasonCode, ...]


class SessionManager:
    """세션 상태 저장소와 Gateway context 포트를 묶어 생명주기를 조정한다."""

    __slots__ = ("_context", "_store")

    def __init__(self, context_port: SessionContextPort, store: SessionBindingStore) -> None:
        """실행 전용 context 포트와 WebDiag 소유 바인딩 저장소를 주입받는다."""
        self._context = context_port
        self._store = store

    async def open_authenticating(
        self,
        run_key: RunKey,
        account_ref: Ref,
        session_ref: Ref,
        auth_profile_ref: Ref,
        generation: int,
        expires_at: UtcTime,
    ) -> SessionOpenOutcome:
        """격리 context를 열고 AUTHENTICATING 바인딩을 발행한다.

        context 할당 실패 시 바인딩을 발행하지 않고 사유만 보존한다(익명 강등 없음).
        할당 성공 직후 반환된 context_ref를 바인딩에 기록하고 나서만 인증을 시작할 수 있다.
        """
        result = await self._context.open_session_context(
            SessionContextRequest(
                run_key=run_key,
                session_ref=session_ref,
                account_ref=account_ref,
                generation=generation,
                auth_profile_ref=auth_profile_ref,
            )
        )
        if result.status is not ResultStatus.COMPLETE or result.transport_context_ref is None:
            return SessionOpenOutcome(binding=None, reason_codes=result.reason_codes)
        binding = SessionBinding(
            session=SessionHandle(
                session_ref=session_ref,
                run_key=run_key,
                account_ref=account_ref,
                generation=generation,
                expires_at=expires_at,
            ),
            state=SessionState.AUTHENTICATING,
            identity=None,
            transport_context_ref=result.transport_context_ref,
            cancelled=False,
        )
        self._store.publish(binding)
        return SessionOpenOutcome(binding=binding, reason_codes=())

    async def close(self, run_key: RunKey, session_ref: Ref) -> CloseResult:
        """세션을 terminal로 바꾼 뒤 context를 닫는다. 없는 세션은 멱등 완료."""
        current = self._store.read_session_binding(run_key, session_ref)
        if current.binding is None:
            return CloseResult(run_key=run_key, status=ResultStatus.COMPLETE, reason_codes=())
        ensure_transition(current.binding.state, SessionState.CLOSED)
        transport_context_ref = current.binding.transport_context_ref
        # 먼저 바인딩을 terminal로 바꿔 이후 전송·재활성화를 막고(§4), 그 다음 context를 닫는다.
        self._store.close(run_key, session_ref)
        return await self._context.close_session_context(
            SessionContextCloseRequest(run_key=run_key, transport_context_ref=transport_context_ref)
        )
