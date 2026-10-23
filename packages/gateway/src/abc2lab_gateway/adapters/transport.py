"""gateway가 소유하는 실제 전송 포트와 무전송 fake.

transport는 격리된 context로 등록 요청을 실제로 보내고 관찰 결과(§6의 전송 3상태)와, 보냈을 때
원문 응답·실제 전송 view를 실행 메모리로 돌려준다. redirect·자동 재시도·origin 간 이동은 끄며
effective origin 밖 이동은 전송 실패로 관찰한다(A6·A10). 공유 계약이 아니라 app이 주입하는 gateway
내부 포트다. 실제 httpx/Playwright 구현은 후속 PR(`integration` marker)이고 이 PR은 fake만 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from abc2lab_contracts.capture import ExecutedRequestView, RawResponse
from abc2lab_contracts.execution import ExecutionRequest
from abc2lab_contracts.primitives import Ref, RunKey

from abc2lab_gateway.core.model import TransportObservation


@dataclass(frozen=True, slots=True, repr=False)
class SendCommand:
    """전송에 필요한 실행 전용 입력. context 참조는 gateway 안에서만 쓴다."""

    run_key: RunKey
    attempt_ref: Ref
    request: ExecutionRequest
    transport_context_ref: Ref | None


@dataclass(frozen=True, slots=True, repr=False)
class SendOutcome:
    """전송 관찰과, 보냈을 때의 원문 응답·실제 전송 view.

    `SENT_CAPTURED`에서만 `raw_response`·`executed_request`가 모두 존재한다. 그 외 상태(미진입·
    캡처 불가·한도 초과·불명)에서는 둘 다 None이며 원문을 보존하지 않는다.
    """

    observation: TransportObservation
    raw_response: RawResponse | None = None
    executed_request: ExecutedRequestView | None = None


class Transport(Protocol):
    """격리된 context로 등록 요청을 보내고 전송 관찰을 돌려주는 포트."""

    async def send(self, command: SendCommand) -> SendOutcome:
        """요청을 한 번 전송하고 관찰 결과를 반환한다. 자동 재시도·리다이렉트 추적을 하지 않는다."""
        ...


class StubTransport:
    """미리 정한 관찰·원문을 돌려주는 무전송 fake. 실제 네트워크를 쓰지 않는다."""

    def __init__(self, outcome: SendOutcome) -> None:
        self._outcome = outcome
        self.commands: list[SendCommand] = []

    async def send(self, command: SendCommand) -> SendOutcome:
        """주어진 관찰을 그대로 돌려주고 호출을 기록한다."""
        self.commands.append(command)
        return self._outcome
