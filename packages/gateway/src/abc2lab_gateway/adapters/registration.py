"""Gateway 실행 경계가 소비하는 run별 등록 snapshot과 같은 loop의 동기 reader다.

app이 run별로 주입하는 불변 snapshot을 I/O·락 없이 즉시 읽는다. policy에 주입하는 것과 같은
scope·profile·operation 원본에 PolicyInput이 싣는 budget snapshot을 더한 묶음이다. 내부 저장
어댑터일 뿐 공개 계약을 대신하지 않으며 원문·자격 증명을 담지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from abc2lab_contracts.primitives import RunKey
from abc2lab_contracts.registration import (
    BudgetSnapshot,
    ExecutionProfileSnapshot,
    OperationRegistration,
    ScopeSnapshot,
)


@dataclass(frozen=True, slots=True)
class GatewayRegistration:
    """한 run에 대해 app이 주입한 등록 snapshot 묶음.

    scope·profile·operations는 policy에 주입하는 원본과 같은 값이어야 한다. gateway가 만든 view를
    policy가 주입 원본과 전체 필드까지 재대조하므로(S1 §5), 두 모듈은 같은 snapshot을 받는다.
    """

    scope: ScopeSnapshot
    profile: ExecutionProfileSnapshot
    budget: BudgetSnapshot
    operations: tuple[OperationRegistration, ...] = field(default_factory=tuple)


class GatewayRegistrationSource(Protocol):
    """run의 현재 등록을 I/O 없이 즉시 읽는 포트."""

    def registration_for(self, run_key: RunKey) -> GatewayRegistration | None:
        """run의 등록 snapshot을 반환한다. 등록이 없으면 None."""
        ...


class InMemoryGatewayRegistrations:
    """run별 등록 snapshot 보관소. 교체로 범위 축소·revision 상향을 반영한다."""

    def __init__(self) -> None:
        self._by_run: dict[RunKey, GatewayRegistration] = {}

    def register(self, run_key: RunKey, registration: GatewayRegistration) -> None:
        """run의 등록을 설정하거나 교체한다."""
        self._by_run[run_key] = registration

    def registration_for(self, run_key: RunKey) -> GatewayRegistration | None:
        """run의 현재 등록 snapshot을 반환한다. 등록이 없으면 None."""
        return self._by_run.get(run_key)
