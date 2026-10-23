"""whoami/acquire_session가 주입받는 webdiag 내부 포트와 설정이다.

contracts에는 identity 감사 writer가 없고(verify/read만), §10상 WebDiag가 identity journal의
소유자이므로 commit 포트를 webdiag 내부에 둔다. app이 실제 어댑터를 주입하고 테스트는 fake로
대체한다. IdentityProfile은 contracts 등록 타입을 묶은 webdiag 내부 설정이며 사본이 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from abc2lab_contracts.audit import AuditReceipt
from abc2lab_contracts.evidence import SealRequest, SealResult
from abc2lab_contracts.primitives import ReasonCode, Ref, Revision, UtcTime
from abc2lab_contracts.registration import ComparisonRules, OperationRegistration
from abc2lab_contracts.session import IdentityContent


class EvidenceSealer(Protocol):
    """ExecutionEvidencePort 중 WebDiag가 쓰는 seal만 좁힌 주입 포트다.

    실제 ExecutionEvidencePort가 구조적으로 이를 만족한다. 로컬 캡처를 소비해 민감값 제거 근거를
    저장하고 그 완료를 확인한 EvidenceSummary를 반환한다.
    """

    async def seal(self, request: SealRequest) -> SealResult:
        """캡처를 봉인해 저장 완료 Evidence 요약을 반환한다(미완료는 사유 보존)."""
        ...


@dataclass(frozen=True, slots=True)
class IdentityProfile:
    """identify 동작 수행과 주체 확인·근거 봉인에 필요한 등록 묶음이다."""

    operation: OperationRegistration
    expected_subject_ref: Ref
    scope_revision: Revision
    profile_revision: Revision
    timeout_ms: int
    identity_ttl_ms: int
    rules: ComparisonRules


class IdentityProfileRegistry(Protocol):
    """identity_profile_ref를 등록된 IdentityProfile로 해석하는 주입 설정이다."""

    def resolve(self, identity_profile_ref: Ref) -> IdentityProfile | None:
        """미등록 프로필은 None을 반환해 unsupported로 처리하게 한다."""
        ...


@dataclass(frozen=True, slots=True)
class IdentityCommit:
    """identity journal commit 결과. receipt가 없으면 verified를 발행하지 않는다."""

    receipt: AuditReceipt | None
    reason_codes: tuple[ReasonCode, ...]


class IdentityJournal(Protocol):
    """WebDiag 소유 identity journal에 불변 확인 내용을 commit하고 영수증을 받는다."""

    async def commit_identity(self, content: IdentityContent) -> IdentityCommit:
        """저장 실패 시 receipt=None과 사유를 남긴다(verified 위장 금지)."""
        ...


class WebDiagClock(Protocol):
    """논리 요청 ID 발급과 UTC 시각을 제공하는 주입 포트다."""

    def now(self) -> UtcTime:
        """timezone-aware UTC 시각을 반환한다."""
        ...

    def new_ref(self, label: str) -> Ref:
        """label을 접두어로 하는 고유 참조를 발급한다."""
        ...
