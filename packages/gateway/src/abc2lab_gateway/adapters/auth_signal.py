"""gateway가 소유하는 인증 신호 추출 포트와 무전송 stub.

전송한 응답에서 등록된 인증 프로필 규칙으로 **비밀 없는 `AuthSignal`**(kind/state/subject_ref)만
뽑는다.
원문(응답 본문·헤더·쿠키)은 실행 메모리에서만 읽고 공용 흐름에 넘기지 않는다(§4). 공유 계약이 아니라
app이 주입하는 gateway 내부 포트다. 실제 규칙 기반 추출기는 후속.
"""

from __future__ import annotations

from typing import Protocol

from abc2lab_contracts.capture import ExecutedRequestView, RawResponse
from abc2lab_contracts.primitives import Purpose, Ref
from abc2lab_contracts.session import AuthSignal, AuthSignalKind


class AuthSignalExtractor(Protocol):
    """전송 응답에서 요청 목적에 맞는 인증 신호 하나를 추출하는 포트."""

    async def extract(
        self,
        auth_profile_ref: Ref,
        purpose: Purpose,
        response: RawResponse,
        executed: ExecutedRequestView,
    ) -> AuthSignal | None:
        """`purpose`에 맞는 신호(AUTHENTICATE→login_result, IDENTIFY→identity)를 추출한다.

        뽑을 수 없으면 `None`. **`subject_ref`는 등록된 subject 별칭으로 해석한 값**이며 응답 원문의
        사용자명·토큰을 그대로 넣지 않는다. 비밀번호·원문·쿠키는 반환·로그·감사에 넣지 않는다.
        호출자는
        그 요청의 실제 `purpose`를 넘겨 교차 목적 신호가 섞이지 않게 한다.
        """
        ...


_PURPOSE_KIND: dict[Purpose, AuthSignalKind] = {
    Purpose.AUTHENTICATE: AuthSignalKind.LOGIN_RESULT,
    Purpose.IDENTIFY: AuthSignalKind.IDENTITY,
}


class StubAuthSignalExtractor:
    """설정한 신호를 요청 purpose가 일치할 때만 돌려주는 무전송 fake.

    실제 응답을 해석하지 않는다. `signal`은 이미 등록 별칭으로 해석된 비밀 없는 값이어야 한다.
    호출받은 purpose를 기록해 교차 목적 호출을 단정할 수 있게 한다.
    """

    def __init__(self, signal: AuthSignal | None = None) -> None:
        self._signal = signal
        self.calls: list[Purpose] = []

    async def extract(
        self,
        auth_profile_ref: Ref,
        purpose: Purpose,
        response: RawResponse,
        executed: ExecutedRequestView,
    ) -> AuthSignal | None:
        """설정 신호의 kind가 요청 purpose에 대응할 때만 반환한다. 그 외는 None."""
        self.calls.append(purpose)
        if self._signal is None:
            return None
        if _PURPOSE_KIND.get(purpose) is not self._signal.kind:
            return None
        return self._signal
