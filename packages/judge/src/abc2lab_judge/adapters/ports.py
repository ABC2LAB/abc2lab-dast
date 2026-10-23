"""judge가 소유하는 내부 주입 포트.

공유 계약(contracts)이 아니라 judge 제공자 내부 경계다. app이 구현해 주입하며 다른 모듈은 이 포트를
import하지 않는다.
"""

from __future__ import annotations

from typing import Protocol

from abc2lab_contracts.primitives import ReadContext, Ref, RunKey


class JudgeReadAuthorizer(Protocol):
    """호출자의 현재 판정 읽기 권한을 매 호출 확인하는 포트."""

    async def authorize(self, run_key: RunKey, context: ReadContext, case_ref: Ref) -> bool:
        """지금 이 호출자가 이 run의 case 판정을 받을 수 있으면 True.

        캐시된 결과를 돌려줄 때도 매번 호출한다. 권한을 확인하지 못하면 True로 추정하지 않는다.
        """
        ...
