"""WebDiag가 소유하는 SessionState 전이 규칙이다.

session.py·S1 §4에 문서화된 흐름에서 합법 전이를 도출한다. 상태별 불변식(confirmed는 검증
identity 필요 등)은 ``SessionBinding``이 강제하고, 여기서는 상태 간 이동의 합법성만 판정한다.
I/O·generation 발급·근거 저장은 orchestration의 몫이며 이 모듈은 순수하다.
"""

from __future__ import annotations

from abc2lab_contracts.session import SessionState

# 같은 상태 유지(멱등 재발행)와 비종료→CLOSED는 아래에서 따로 허용한다.
_ALLOWED_MOVES: dict[SessionState, frozenset[SessionState]] = {
    SessionState.NOT_READY: frozenset({SessionState.AUTHENTICATING, SessionState.UNAVAILABLE}),
    SessionState.AUTHENTICATING: frozenset({SessionState.CONFIRMED, SessionState.UNAVAILABLE}),
    SessionState.CONFIRMED: frozenset({SessionState.EXPIRY_SUSPECTED}),
    SessionState.EXPIRY_SUSPECTED: frozenset({SessionState.RECOVERING, SessionState.UNAVAILABLE}),
    SessionState.RECOVERING: frozenset({SessionState.CONFIRMED, SessionState.UNAVAILABLE}),
    SessionState.UNAVAILABLE: frozenset(),
    SessionState.CLOSED: frozenset(),
}


def is_allowed_transition(current: SessionState, target: SessionState) -> bool:
    """상태 이동이 합법인지 판정한다.

    같은 상태 유지는 항상 허용(인증 중 identity 갱신 등 멱등 재발행)하고, CLOSED는 종료
    상태라 CLOSED→CLOSED 외 어떤 이동도 금지한다. 모든 비종료 상태는 CLOSED로 갈 수 있다.
    """
    if target is current:
        return True
    if current is SessionState.CLOSED:
        return False
    if target is SessionState.CLOSED:
        return True
    return target in _ALLOWED_MOVES[current]


def ensure_transition(current: SessionState, target: SessionState) -> None:
    """합법이 아닌 상태 이동이면 ``ValueError``를 발생시킨다."""
    if not is_allowed_transition(current, target):
        raise ValueError(f"illegal session transition: {current.value} -> {target.value}")
