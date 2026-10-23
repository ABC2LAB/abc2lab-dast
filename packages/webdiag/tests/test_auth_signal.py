"""AuthSignal 해석 — 로그인 수락과 주체 일치/불일치 판정을 검사한다."""

from abc2lab_contracts.session import AuthSignal, AuthSignalKind, AuthSignalState, IdentityStatus
from abc2lab_webdiag.core.auth_signal import identity_status, login_result

_EXPECTED = "subject-a"


def _signal(kind: AuthSignalKind, state: AuthSignalState, subject: str | None) -> AuthSignal:
    return AuthSignal(kind=kind, state=state, subject_ref=subject)


def test_login_result_reports_accept_reject() -> None:
    """login_result 신호는 수락/거절을 그대로 보고한다."""
    accepted = _signal(AuthSignalKind.LOGIN_RESULT, AuthSignalState.ACCEPTED, None)
    rejected = _signal(AuthSignalKind.LOGIN_RESULT, AuthSignalState.REJECTED, None)
    assert login_result(accepted) is AuthSignalState.ACCEPTED
    assert login_result(rejected) is AuthSignalState.REJECTED


def test_login_result_unknown_for_absent_or_other_kind() -> None:
    """부재·다른 종류 신호는 UNKNOWN으로 남긴다."""
    identity = _signal(AuthSignalKind.IDENTITY, AuthSignalState.ACCEPTED, _EXPECTED)
    assert login_result(None) is AuthSignalState.UNKNOWN
    assert login_result(identity) is AuthSignalState.UNKNOWN


def test_identity_verified_on_matching_subject() -> None:
    """수락 + 등록 기대 주체 일치 → VERIFIED."""
    signal = _signal(AuthSignalKind.IDENTITY, AuthSignalState.ACCEPTED, _EXPECTED)
    assert identity_status(signal, _EXPECTED) == (IdentityStatus.VERIFIED, _EXPECTED)


def test_identity_mismatch_on_different_subject() -> None:
    """수락이지만 다른 주체가 확인되면 MISMATCH로 실제 주체를 보존한다."""
    signal = _signal(AuthSignalKind.IDENTITY, AuthSignalState.ACCEPTED, "subject-b")
    assert identity_status(signal, _EXPECTED) == (IdentityStatus.MISMATCH, "subject-b")


def test_identity_unknown_when_unconfirmed() -> None:
    """주체 미추출·거절·불명·부재는 확정하지 않고 UNKNOWN."""
    accepted_no_subject = _signal(AuthSignalKind.IDENTITY, AuthSignalState.ACCEPTED, None)
    rejected = _signal(AuthSignalKind.IDENTITY, AuthSignalState.REJECTED, "subject-b")
    unknown = _signal(AuthSignalKind.IDENTITY, AuthSignalState.UNKNOWN, None)
    assert identity_status(accepted_no_subject, _EXPECTED) == (IdentityStatus.UNKNOWN, None)
    assert identity_status(rejected, _EXPECTED) == (IdentityStatus.UNKNOWN, "subject-b")
    assert identity_status(unknown, _EXPECTED) == (IdentityStatus.UNKNOWN, None)
    assert identity_status(None, _EXPECTED) == (IdentityStatus.UNKNOWN, None)
