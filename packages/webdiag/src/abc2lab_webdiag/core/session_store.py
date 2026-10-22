"""실행 세션 바인딩의 락 없는 일관 snapshot 저장소다."""

from __future__ import annotations

from dataclasses import replace

from abc2lab_contracts.primitives import ReasonCode, Ref, ResultStatus, RunKey
from abc2lab_contracts.session import SessionBinding, SessionBindingResult, SessionState


class StaleBindingError(RuntimeError):
    """구세대·취소·종료된 세션을 되살리려는 발행을 거부할 때 발생한다."""


class SessionBindingStore:
    """WebDiag가 단일 소유하는 세션 바인딩의 기록자이자 동기 읽기 지점이다.

    같은 event loop·스레드에서만 호출한다. 모든 변경은 불변 ``SessionBinding``을 먼저
    만들고 한 번의 대입으로 교체하므로 중간 상태가 없다. 읽기는 항상 완전한 한 snapshot을
    보고, 교체 직후 첫 읽기부터 새 상태를 본다(이전 generation·identity와 새 state·cancelled가
    섞인 torn read를 허용하지 않음). 이 저장소는 await·I/O·잠금을 쓰지 않는다. Gateway의
    전송 직전 재조회(§10)도 이 포트로 수행한다.
    """

    __slots__ = ("_bindings",)

    def __init__(self) -> None:
        """run·세션별 현재 바인딩만 보관하는 빈 저장소를 만든다."""
        self._bindings: dict[tuple[RunKey, Ref], SessionBinding] = {}

    def read_session_binding(self, run_key: RunKey, session_ref: Ref) -> SessionBindingResult:
        """현재 바인딩을 즉시 반환한다. 없는 세션을 익명·빈 정상 결과로 바꾸지 않는다."""
        binding = self._bindings.get((run_key, session_ref))
        if binding is None:
            return SessionBindingResult(
                run_key=run_key,
                status=ResultStatus.FAILED,
                binding=None,
                reason_codes=(ReasonCode.NOT_FOUND,),
            )
        return SessionBindingResult(
            run_key=run_key,
            status=ResultStatus.COMPLETE,
            binding=binding,
            reason_codes=(),
        )

    def publish(self, binding: SessionBinding) -> None:
        """새 바인딩을 원자 교체로 발행한다. 구세대·취소·종료 재활성화는 거부한다.

        같은 generation의 재발행은 허용해 authenticating→confirmed 전이를 반영한다.
        """
        key = (binding.session.run_key, binding.session.session_ref)
        current = self._bindings.get(key)
        if current is not None:
            if current.state is SessionState.CLOSED:
                raise StaleBindingError("closed session cannot be republished")
            if binding.session.generation < current.session.generation:
                raise StaleBindingError("stale session generation cannot be published")
            if current.cancelled and not binding.cancelled:
                raise StaleBindingError("cancelled session cannot be reactivated")
        self._bindings[key] = binding

    def cancel(self, run_key: RunKey, session_ref: Ref) -> bool:
        """현재 바인딩을 취소 표시로 교체한다. 없는 세션은 False, 재호출은 멱등."""
        key = (run_key, session_ref)
        current = self._bindings.get(key)
        if current is None:
            return False
        if not current.cancelled:
            self._bindings[key] = replace(current, cancelled=True)
        return True

    def close(self, run_key: RunKey, session_ref: Ref) -> bool:
        """세션을 종료 상태로 교체해 이후 발행·사용을 막는다. 없는 세션은 False, 멱등."""
        key = (run_key, session_ref)
        current = self._bindings.get(key)
        if current is None:
            return False
        if current.state is not SessionState.CLOSED or not current.cancelled:
            self._bindings[key] = replace(current, state=SessionState.CLOSED, cancelled=True)
        return True

    def discard_run(self, run_key: RunKey) -> None:
        """run 종료·중단 정리 시 해당 run의 모든 바인딩 참조를 제거한다."""
        for key in [stored for stored in self._bindings if stored[0] == run_key]:
            del self._bindings[key]
