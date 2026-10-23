"""gateway가 소유하는 자격 결합(Vault) 포트와 메모리 구현.

계정 비밀은 전송 직전에만 전송 context에 결합하고 결과·로그·repr·감사에 넣지 않는다(명세 §5·
아키 §8.4). 공유 계약이 아니라 app이 주입하는 gateway 내부 포트다. 이 무전송 PR에서는 결합 호출을
전송 경로에서만 수행하고 비밀이 공개 결과로 새지 않는지를 검증한다. 실제 비밀 저장소·canary는
후속이다.
"""

from __future__ import annotations

from typing import Protocol

from abc2lab_contracts.primitives import Ref, RunKey


class VaultBinder(Protocol):
    """전송 직전 자격 증명을 격리된 transport context에 결합하는 포트."""

    async def bind(self, run_key: RunKey, account_ref: Ref | None, context_ref: Ref) -> None:
        """등록된 자격을 전송 context에만 결합한다. 반환·로그에 비밀을 담지 않는다.

        결합할 자격이 없으면 아무것도 하지 않는다(익명 요청). 실패는 구체 예외로 올리고 전송 상태를
        꾸미지 않는다.
        """
        ...


class InMemoryVaultBinder:
    """자격을 결합하지 않고 호출만 기록하는 무전송 테스트용 binder."""

    def __init__(self) -> None:
        self.bound_contexts: list[Ref] = []

    async def bind(self, run_key: RunKey, account_ref: Ref | None, context_ref: Ref) -> None:
        """결합을 기록만 한다. 실제 비밀은 다루지 않는다."""
        self.bound_contexts.append(context_ref)
