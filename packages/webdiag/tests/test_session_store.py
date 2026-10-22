"""SessionBindingStore의 일관 읽기·원자 교체·재활성화 거부를 검사한다."""

from datetime import UTC, datetime

import pytest
from abc2lab_contracts.ports import SessionBindingReader
from abc2lab_contracts.primitives import ReasonCode, ResultStatus, RunKey
from abc2lab_contracts.session import SessionBinding, SessionHandle, SessionState
from abc2lab_webdiag.core.session_store import SessionBindingStore, StaleBindingError

_RUN = RunKey(
    organization_ref="org-1",
    target_ref="target-1",
    environment_ref="env-1",
    run_ref="run-1",
)
_OTHER_RUN = RunKey(
    organization_ref="org-1",
    target_ref="target-1",
    environment_ref="env-1",
    run_ref="run-2",
)
_EXPIRES = datetime(2026, 10, 22, 0, 0, 0, tzinfo=UTC)


def _handle(session_ref: str, generation: int, run_key: RunKey = _RUN) -> SessionHandle:
    return SessionHandle(
        session_ref=session_ref,
        run_key=run_key,
        account_ref="account-a",
        generation=generation,
        expires_at=_EXPIRES,
    )


def _binding(
    session_ref: str = "session-a",
    *,
    generation: int = 1,
    state: SessionState = SessionState.AUTHENTICATING,
    cancelled: bool = False,
    run_key: RunKey = _RUN,
) -> SessionBinding:
    return SessionBinding(
        session=_handle(session_ref, generation, run_key),
        state=state,
        identity=None,
        transport_context_ref="ctx-1",
        cancelled=cancelled,
    )


def test_store_satisfies_session_binding_reader() -> None:
    """저장소는 Gateway가 소비하는 동기 읽기 포트를 구조적으로 만족한다."""
    reader: SessionBindingReader = SessionBindingStore()
    assert reader.read_session_binding(_RUN, "missing").status is ResultStatus.FAILED


def test_published_binding_reads_complete() -> None:
    """발행한 바인딩은 완전한 snapshot으로 즉시 읽힌다."""
    store = SessionBindingStore()
    binding = _binding()
    store.publish(binding)
    result = store.read_session_binding(_RUN, "session-a")
    assert result.status is ResultStatus.COMPLETE
    assert result.binding is binding
    assert result.reason_codes == ()


def test_missing_session_is_failed_not_anonymous() -> None:
    """없는 세션은 익명이 아니라 실패와 사유로 남는다."""
    store = SessionBindingStore()
    result = store.read_session_binding(_RUN, "session-a")
    assert result.status is ResultStatus.FAILED
    assert result.binding is None
    assert ReasonCode.NOT_FOUND in result.reason_codes


def test_other_run_does_not_leak_binding() -> None:
    """같은 session_ref라도 다른 run으로 조회하면 노출되지 않는다."""
    store = SessionBindingStore()
    store.publish(_binding(run_key=_RUN))
    result = store.read_session_binding(_OTHER_RUN, "session-a")
    assert result.status is ResultStatus.FAILED
    assert result.binding is None


def test_swap_is_visible_on_first_read() -> None:
    """generation 교체 직후 첫 읽기부터 새 바인딩을 본다."""
    store = SessionBindingStore()
    store.publish(_binding(generation=1))
    swapped = _binding(generation=2, state=SessionState.EXPIRY_SUSPECTED)
    store.publish(swapped)
    result = store.read_session_binding(_RUN, "session-a")
    assert result.binding is swapped
    assert result.binding.session.generation == 2


def test_same_generation_republish_reflects_transition() -> None:
    """같은 generation 재발행으로 authenticating→confirmed 같은 전이를 반영한다."""
    store = SessionBindingStore()
    store.publish(_binding(generation=1, state=SessionState.AUTHENTICATING))
    advanced = _binding(generation=1, state=SessionState.EXPIRY_SUSPECTED)
    store.publish(advanced)
    assert store.read_session_binding(_RUN, "session-a").binding is advanced


def test_stale_generation_publish_is_rejected() -> None:
    """구세대 바인딩 발행은 거부한다(현재 세대를 되돌리지 않음)."""
    store = SessionBindingStore()
    store.publish(_binding(generation=2))
    with pytest.raises(StaleBindingError, match="stale session generation"):
        store.publish(_binding(generation=1))
    result = store.read_session_binding(_RUN, "session-a")
    assert result.binding is not None
    assert result.binding.session.generation == 2


def test_cancel_is_visible_and_idempotent() -> None:
    """취소는 읽기에 반영되고 재호출은 멱등이다."""
    store = SessionBindingStore()
    store.publish(_binding())
    assert store.cancel(_RUN, "session-a") is True
    result = store.read_session_binding(_RUN, "session-a")
    assert result.binding is not None
    assert result.binding.cancelled is True
    assert store.cancel(_RUN, "session-a") is True
    assert store.cancel(_RUN, "missing") is False


def test_cancelled_session_cannot_be_reactivated() -> None:
    """취소된 세션에 취소 해제 바인딩을 발행할 수 없다."""
    store = SessionBindingStore()
    store.publish(_binding())
    store.cancel(_RUN, "session-a")
    with pytest.raises(StaleBindingError, match="cannot be reactivated"):
        store.publish(_binding(generation=2, cancelled=False))


def test_close_marks_terminal_and_blocks_republish() -> None:
    """종료 세션은 CLOSED·cancelled로 읽히고 재발행이 막힌다."""
    store = SessionBindingStore()
    store.publish(_binding())
    assert store.close(_RUN, "session-a") is True
    result = store.read_session_binding(_RUN, "session-a")
    assert result.binding is not None
    assert result.binding.state is SessionState.CLOSED
    assert result.binding.cancelled is True
    assert store.close(_RUN, "session-a") is True
    with pytest.raises(StaleBindingError, match="closed session"):
        store.publish(_binding(generation=3))


def test_discard_run_removes_only_that_run() -> None:
    """run 정리는 해당 run의 바인딩만 제거한다."""
    store = SessionBindingStore()
    store.publish(_binding(run_key=_RUN))
    store.publish(_binding(run_key=_OTHER_RUN))
    store.discard_run(_RUN)
    assert store.read_session_binding(_RUN, "session-a").status is ResultStatus.FAILED
    assert store.read_session_binding(_OTHER_RUN, "session-a").status is ResultStatus.COMPLETE
