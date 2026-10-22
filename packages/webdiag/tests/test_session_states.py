"""세션 상태 전이 규칙의 합법·불법 이동을 검사한다."""

import pytest
from abc2lab_contracts.session import SessionState
from abc2lab_webdiag.core.session_states import ensure_transition, is_allowed_transition

_LEGAL = [
    (SessionState.NOT_READY, SessionState.AUTHENTICATING),
    (SessionState.NOT_READY, SessionState.UNAVAILABLE),
    (SessionState.AUTHENTICATING, SessionState.CONFIRMED),
    (SessionState.AUTHENTICATING, SessionState.UNAVAILABLE),
    (SessionState.CONFIRMED, SessionState.EXPIRY_SUSPECTED),
    (SessionState.EXPIRY_SUSPECTED, SessionState.RECOVERING),
    (SessionState.EXPIRY_SUSPECTED, SessionState.UNAVAILABLE),
    (SessionState.RECOVERING, SessionState.CONFIRMED),
    (SessionState.RECOVERING, SessionState.UNAVAILABLE),
]

_ILLEGAL = [
    (SessionState.NOT_READY, SessionState.CONFIRMED),  # authenticating 건너뜀
    (SessionState.CONFIRMED, SessionState.NOT_READY),  # 역방향
    (SessionState.CONFIRMED, SessionState.AUTHENTICATING),  # expiry→recovering 경유 필요
    (SessionState.EXPIRY_SUSPECTED, SessionState.CONFIRMED),  # 복구 없이 확인 금지
    (SessionState.UNAVAILABLE, SessionState.CONFIRMED),  # 종착(복구 아님)
    (SessionState.CLOSED, SessionState.AUTHENTICATING),  # 종료는 terminal
    (SessionState.CLOSED, SessionState.CONFIRMED),
]


@pytest.mark.parametrize(("current", "target"), _LEGAL)
def test_legal_transitions(current: SessionState, target: SessionState) -> None:
    """문서화된 흐름의 이동은 허용된다."""
    assert is_allowed_transition(current, target) is True
    ensure_transition(current, target)


@pytest.mark.parametrize(("current", "target"), _ILLEGAL)
def test_illegal_transitions(current: SessionState, target: SessionState) -> None:
    """건너뛰기·역방향·종료 후 이동은 거부된다."""
    assert is_allowed_transition(current, target) is False
    with pytest.raises(ValueError, match="illegal session transition"):
        ensure_transition(current, target)


@pytest.mark.parametrize("state", list(SessionState))
def test_same_state_is_idempotent(state: SessionState) -> None:
    """같은 상태 유지는 멱등 재발행으로 허용된다."""
    assert is_allowed_transition(state, state) is True


@pytest.mark.parametrize("state", list(SessionState))
def test_any_nonclosed_can_close(state: SessionState) -> None:
    """비종료 상태는 CLOSED로 갈 수 있고 CLOSED→CLOSED도 멱등이다."""
    assert is_allowed_transition(state, SessionState.CLOSED) is True


def test_closed_is_terminal_except_self() -> None:
    """CLOSED에서 다른 상태로 나가는 이동은 모두 금지한다."""
    for target in SessionState:
        expected = target is SessionState.CLOSED
        assert is_allowed_transition(SessionState.CLOSED, target) is expected
