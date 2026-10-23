"""gateway가 소유하는 실행 예산 ledger 포트와 메모리 구현.

예산은 "이 run이 몇 번 전송 시도를 썼나"라는 런타임 가변 상태라 순수 코어에 둘 수 없고, app이
주입하는 gateway 내부 포트다(명세 §5: 요청 semaphore·예산은 Gateway 소유). 공유 계약이 아니며 남은
예산은 감사 payload·fingerprint에 넣지 않는다(§11-42). 한도(`max_attempts`)는 등록 `BudgetSnapshot`
에서 오고 ledger는 소비분만 센다.
"""

from __future__ import annotations

from typing import Protocol

from abc2lab_contracts.primitives import Ref, RunKey


class BudgetLedger(Protocol):
    """전송 직전 임계 구역에서 await 없이 예산을 원자 차감하는 포트."""

    def try_consume(self, run_key: RunKey, binding_id: Ref, max_attempts: int) -> bool:
        """한도 안이면 한 번 차감하고 True. 같은 binding_id 재호출은 재차감 없이 True.

        단일 event loop·스레드에서 호출하며 await 없이 즉시 결정한다. 한도 초과면 False이고 소비하지
        않는다. 재전송 금지를 위해 같은 준비 요청(binding_id)은 한 번만 센다.
        """
        ...


class InMemoryBudgetLedger:
    """유한 메모리의 run별 소비 카운터. 비내구(흐름 테스트용)."""

    def __init__(self) -> None:
        self._consumed: dict[RunKey, set[Ref]] = {}

    def try_consume(self, run_key: RunKey, binding_id: Ref, max_attempts: int) -> bool:
        """run의 소비 binding 집합으로 멱등 차감한다."""
        consumed = self._consumed.setdefault(run_key, set())
        if binding_id in consumed:
            # 같은 준비 요청의 재시도는 이미 센 시도다. 재차감하지 않는다.
            return True
        if len(consumed) >= max_attempts:
            return False
        consumed.add(binding_id)
        return True
