"""submission 단위 판정 멱등 저장소(메모리).

같은 `submission_ref`와 같은 의미 입력이면 최초 COMPLETE 결과를 그대로 돌려준다(새 판정·event_ref·
revision 없음). 의미 입력에서 `ReadContext`는 뺀다 — 권한은 저장소가 아니라 호출마다 인가 포트가
확인한다. 같은 submission 호출은 submission별 잠금으로 직렬화한다. 실패 결과는 저장하지 않는다.
프로세스가 끝나면 사라지므로 app은 내구 저장소로 바꿔 주입해야 한다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from abc2lab_contracts.judge import JudgeRequest, JudgeResult
from abc2lab_contracts.primitives import Ref, RunKey
from abc2lab_contracts.registration import ExpectedAccessPolicySnapshot
from abc2lab_contracts.session import IdentityResult


@dataclass(frozen=True, slots=True)
class SemanticInput:
    """멱등 비교에 쓰는 요청의 의미 입력. `ReadContext`는 포함하지 않는다."""

    case_ref: Ref
    expected_policy: ExpectedAccessPolicySnapshot | None
    owner_identity: IdentityResult | None
    evaluated_identity: IdentityResult | None
    comparison_ref: Ref | None

    @classmethod
    def of(cls, request: JudgeRequest) -> SemanticInput:
        """요청에서 의미 입력만 뽑는다."""
        return cls(
            case_ref=request.case_ref,
            expected_policy=request.expected_policy,
            owner_identity=request.owner_identity,
            evaluated_identity=request.evaluated_identity,
            comparison_ref=request.comparison_ref,
        )


@dataclass(frozen=True, slots=True)
class StoredSubmission:
    """저장된 submission의 의미 입력과 최초 COMPLETE 결과."""

    semantic: SemanticInput
    result: JudgeResult


class InMemorySubmissionStore:
    """같은 event loop에서 쓰는 비내구 submission 저장소."""

    def __init__(self) -> None:
        self._locks: dict[tuple[RunKey, Ref], asyncio.Lock] = {}
        self._submissions: dict[tuple[RunKey, Ref], StoredSubmission] = {}

    def lock_for(self, run_key: RunKey, submission_ref: Ref) -> asyncio.Lock:
        """같은 submission 호출을 직렬화하는 잠금을 반환한다."""
        return self._locks.setdefault((run_key, submission_ref), asyncio.Lock())

    def get(self, run_key: RunKey, submission_ref: Ref) -> StoredSubmission | None:
        """저장된 submission이 있으면 반환한다."""
        return self._submissions.get((run_key, submission_ref))

    def put(self, run_key: RunKey, submission_ref: Ref, stored: StoredSubmission) -> None:
        """COMPLETE 결과를 저장한다. 이미 있으면 덮어쓰지 않는다."""
        self._submissions.setdefault((run_key, submission_ref), stored)
