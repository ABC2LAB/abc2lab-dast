"""SessionManager의 context 생명주기·바인딩 발행·종료 순서를 검사한다."""

from datetime import UTC, datetime

import pytest
from abc2lab_contracts.primitives import CloseResult, ReasonCode, Ref, ResultStatus, RunKey
from abc2lab_contracts.session import (
    SessionContextCloseRequest,
    SessionContextRequest,
    SessionContextResult,
    SessionState,
)
from abc2lab_webdiag.core.session_manager import SessionManager
from abc2lab_webdiag.core.session_store import SessionBindingStore

_RUN = RunKey(
    organization_ref="org-1",
    target_ref="target-1",
    environment_ref="env-1",
    run_ref="run-1",
)
_EXPIRES = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)


class _FakeContextPort:
    """SessionContextPort 대역. open 성공 여부를 제어하고 호출을 기록한다."""

    def __init__(self, *, open_ok: bool = True) -> None:
        self.open_ok = open_ok
        self.opened: list[SessionContextRequest] = []
        self.closed: list[SessionContextCloseRequest] = []

    async def open_session_context(self, request: SessionContextRequest) -> SessionContextResult:
        self.opened.append(request)
        if not self.open_ok:
            return SessionContextResult(
                run_key=request.run_key,
                status=ResultStatus.FAILED,
                transport_context_ref=None,
                reason_codes=(ReasonCode.INTERNAL_ERROR,),
            )
        return SessionContextResult(
            run_key=request.run_key,
            status=ResultStatus.COMPLETE,
            transport_context_ref=f"ctx-{request.session_ref}",
            reason_codes=(),
        )

    async def close_session_context(self, request: SessionContextCloseRequest) -> CloseResult:
        self.closed.append(request)
        return CloseResult(run_key=request.run_key, status=ResultStatus.COMPLETE, reason_codes=())


async def _open(manager: SessionManager, session_ref: Ref = "session-a") -> None:
    await manager.open_authenticating(
        run_key=_RUN,
        account_ref="account-a",
        session_ref=session_ref,
        auth_profile_ref="auth-1",
        generation=1,
        expires_at=_EXPIRES,
    )


@pytest.mark.asyncio
async def test_open_publishes_authenticating_binding() -> None:
    """context 할당 성공 시 AUTHENTICATING 바인딩을 저장소에 발행한다."""
    context = _FakeContextPort()
    store = SessionBindingStore()
    manager = SessionManager(context, store)

    outcome = await manager.open_authenticating(
        run_key=_RUN,
        account_ref="account-a",
        session_ref="session-a",
        auth_profile_ref="auth-1",
        generation=1,
        expires_at=_EXPIRES,
    )

    assert outcome.binding is not None
    assert outcome.binding.state is SessionState.AUTHENTICATING
    assert outcome.binding.transport_context_ref == "ctx-session-a"
    read = store.read_session_binding(_RUN, "session-a")
    assert read.status is ResultStatus.COMPLETE
    assert context.opened[0].auth_profile_ref == "auth-1"


@pytest.mark.asyncio
async def test_open_failure_publishes_no_binding() -> None:
    """context 할당 실패 시 바인딩을 발행하지 않고 사유만 보존한다."""
    context = _FakeContextPort(open_ok=False)
    store = SessionBindingStore()
    manager = SessionManager(context, store)

    outcome = await manager.open_authenticating(
        run_key=_RUN,
        account_ref="account-a",
        session_ref="session-a",
        auth_profile_ref="auth-1",
        generation=1,
        expires_at=_EXPIRES,
    )

    assert outcome.binding is None
    assert ReasonCode.INTERNAL_ERROR in outcome.reason_codes
    assert store.read_session_binding(_RUN, "session-a").status is ResultStatus.FAILED


@pytest.mark.asyncio
async def test_close_marks_terminal_before_closing_context() -> None:
    """종료는 바인딩을 CLOSED로 바꾼 뒤 그 context_ref로 context를 닫는다."""
    context = _FakeContextPort()
    store = SessionBindingStore()
    manager = SessionManager(context, store)
    await _open(manager)

    result = await manager.close(_RUN, "session-a")

    assert result.status is ResultStatus.COMPLETE
    read = store.read_session_binding(_RUN, "session-a")
    assert read.binding is not None
    assert read.binding.state is SessionState.CLOSED
    assert read.binding.cancelled is True
    assert context.closed[0].transport_context_ref == "ctx-session-a"


@pytest.mark.asyncio
async def test_close_missing_session_is_idempotent_noop() -> None:
    """없는 세션 종료는 context를 닫지 않고 멱등 완료를 반환한다."""
    context = _FakeContextPort()
    store = SessionBindingStore()
    manager = SessionManager(context, store)

    result = await manager.close(_RUN, "session-a")

    assert result.status is ResultStatus.COMPLETE
    assert context.closed == []
