"""Host↔WebDiag 경계의 요청·결과 record와 WebDiagPort다.

[C4 초안](../../../docs/planning/c4-webdiag-contract-draft.md)의 합의를 구현한다. 기존
session·observation·knowledge·projection·evidence·registration 타입을 재사용하며 임의
dict·Any·사본을 만들지 않는다. S1은 HTTP 단일 경로라 web_observe(브라우저)는 포함하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from abc2lab_contracts._validation import ContractRecord
from abc2lab_contracts.evidence import ComparisonProjected, StoredComparison
from abc2lab_contracts.knowledge import Candidate, CandidateHint
from abc2lab_contracts.observation import Observation
from abc2lab_contracts.primitives import AttemptSummary, ReasonCode, Ref, ResultStatus, RunKey
from abc2lab_contracts.projection import ObservationProjected
from abc2lab_contracts.registration import CrossExecutionConfirmation, ExpectedAccessPolicySnapshot
from abc2lab_contracts.session import IdentityResult, SessionHandle, SessionResult

# WebDiag가 원본 producer(자기 Observation, Evidence의 비교)에서 받아 변경 없이 전달하는 투영이다.
type WebDiagProjectionEvent = ObservationProjected | ComparisonProjected


@dataclass(frozen=True, slots=True)
class SessionRequest(ContractRecord):
    """등록 인증 프로필로 계정 세션을 확보하는 요청이다."""

    run_key: RunKey
    account_ref: Ref
    auth_profile_ref: Ref


@dataclass(frozen=True, slots=True)
class IdentityRequest(ContractRecord):
    """현재 세션의 실제 주체를 확인하는 요청이다."""

    run_key: RunKey
    session: SessionHandle
    identity_profile_ref: Ref


@dataclass(frozen=True, slots=True)
class DiscoveryRequest(ContractRecord):
    """등록 seed에서 유한 상한으로 후보 단서를 수집하는 요청이다."""

    run_key: RunKey
    seed_operation_refs: tuple[Ref, ...]
    account_ref: Ref
    max_candidates: int

    def _validate_invariants(self) -> None:
        if type(self.max_candidates) is not int or self.max_candidates < 1:
            raise ValueError("max_candidates must be a positive integer")


@dataclass(frozen=True, slots=True)
class ObserveRequest(ContractRecord):
    """Host가 조회·검증한 자기 자원 Candidate를 관찰하는 요청이다."""

    run_key: RunKey
    candidate: Candidate
    account_ref: Ref
    observation_profile_ref: Ref


@dataclass(frozen=True, slots=True)
class AccessCompareRequest(ContractRecord):
    """소유자 기준과 평가 계정의 교차 접근을 비교하는 요청이다.

    expected_policy·cross_confirmation은 Host가 등록 원본에서 선택·전달만 하고 Gateway/Policy가
    재대조한다. 교차가 아니면 둘 다 None이다.
    """

    run_key: RunKey
    case_ref: Ref
    candidate: Candidate
    owner_account_ref: Ref
    evaluated_account_ref: Ref
    expected_policy: ExpectedAccessPolicySnapshot | None
    cross_confirmation: CrossExecutionConfirmation | None


@dataclass(frozen=True, slots=True)
class DiscoveryResult(ContractRecord):
    """Knowledge 등록 전의 민감값 제거 단서다. ID/revision은 발급하지 않는다."""

    run_key: RunKey
    status: ResultStatus
    hints: tuple[CandidateHint, ...]
    attempt_summaries: tuple[AttemptSummary, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.FAILED and self.hints:
            raise ValueError("failed discovery result cannot publish hints")


@dataclass(frozen=True, slots=True)
class ObserveResult(ContractRecord):
    """자기 자원 관찰 결과다. Observation은 공개 Evidence 저장이 완료된 complete에만 존재한다."""

    run_key: RunKey
    status: ResultStatus
    observation: Observation | None
    projection_events: tuple[ObservationProjected, ...]
    attempt_summaries: tuple[AttemptSummary, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.COMPLETE:
            if self.observation is None or not self.projection_events:
                raise ValueError("complete observe result requires observation and projection")
        elif self.observation is not None:
            raise ValueError("non-complete observe result cannot publish an observation")


@dataclass(frozen=True, slots=True)
class AccessCompareResult(ContractRecord):
    """교차 비교 결과다. complete에만 저장 완료 비교와 대응 투영이 존재한다."""

    run_key: RunKey
    case_ref: Ref
    status: ResultStatus
    owner_identity: IdentityResult | None
    evaluated_identity: IdentityResult | None
    owner_observation: Observation | None
    stored_comparison: StoredComparison | None
    stored_evidence_refs: tuple[Ref, ...]
    projection_events: tuple[ObservationProjected | ComparisonProjected, ...]
    attempt_summaries: tuple[AttemptSummary, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.COMPLETE:
            if self.stored_comparison is None or not self.projection_events:
                raise ValueError(
                    "complete access compare requires stored comparison and projection"
                )
        elif self.stored_comparison is not None:
            raise ValueError("non-complete access compare cannot publish a stored comparison")


class WebDiagPort(Protocol):
    """Host가 사례별로 호출하는 WebDiag 공개 포트다. 전부 I/O 대기를 포함해 async다."""

    async def collect(self, request: DiscoveryRequest) -> DiscoveryResult:
        """등록 seed에서 민감값 제거 단서를 수집한다. 등록은 Host가 Knowledge에 한다."""
        ...

    async def http_observe(self, request: ObserveRequest) -> ObserveResult:
        """자기 자원만 관찰한다. 교차 요청 창구로 변질되지 않는다."""
        ...

    async def access_compare(self, request: AccessCompareRequest) -> AccessCompareResult:
        """교차 접근을 이 호출 내부에서만 조정한다. D-0 통과 전에는 무전송 대역이다."""
        ...

    async def acquire_session(self, request: SessionRequest) -> SessionResult:
        """로그인과 whoami까지 마쳐 confirmed 세션을 반환한다."""
        ...

    async def whoami(self, request: IdentityRequest) -> IdentityResult:
        """로그인 성공과 별개로 현재 세션의 실제 주체를 확인한다."""
        ...
