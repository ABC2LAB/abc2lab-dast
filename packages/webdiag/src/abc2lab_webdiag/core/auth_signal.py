"""Gateway가 등록 규칙으로 추출한 AuthSignal을 WebDiag 상태 판단으로 해석한다(순수).

로그인 성공 신호와 실제 주체 확인을 구분한다(§8.3). 주체는 등록된 기대 주체와 대조하며,
신호 부재·다른 종류·주체 미추출은 확정하지 않고 UNKNOWN으로 남긴다(익명·성공 강등 없음).
"""

from __future__ import annotations

from abc2lab_contracts.primitives import Ref
from abc2lab_contracts.session import AuthSignal, AuthSignalKind, AuthSignalState, IdentityStatus


def login_result(signal: AuthSignal | None) -> AuthSignalState:
    """login_result 신호의 수락/거절을 돌려준다. 다른 종류·부재는 UNKNOWN."""
    if signal is None or signal.kind is not AuthSignalKind.LOGIN_RESULT:
        return AuthSignalState.UNKNOWN
    return signal.state


def identity_status(
    signal: AuthSignal | None, expected_subject_ref: Ref
) -> tuple[IdentityStatus, Ref | None]:
    """identity 신호를 등록된 기대 주체와 대조해 신원 상태·주체를 판정한다.

    수락 + 주체 일치 → VERIFIED, 수락 + 주체 불일치 → MISMATCH(실제 다른 주체 확인).
    주체 미추출·거절·불명·다른 종류·부재는 UNKNOWN(확정 유보). EXPIRED는 만료 신호의 몫이다.
    """
    if signal is None or signal.kind is not AuthSignalKind.IDENTITY:
        return (IdentityStatus.UNKNOWN, None)
    if signal.state is AuthSignalState.ACCEPTED and signal.subject_ref is not None:
        if signal.subject_ref == expected_subject_ref:
            return (IdentityStatus.VERIFIED, signal.subject_ref)
        return (IdentityStatus.MISMATCH, signal.subject_ref)
    return (IdentityStatus.UNKNOWN, signal.subject_ref)
