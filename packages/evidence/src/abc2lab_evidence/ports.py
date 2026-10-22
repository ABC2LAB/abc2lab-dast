"""evidence 내부 주입 Protocol.

공개 포트(`LocalCapturePort`·`ExecutionEvidencePort`·`EvidencePort`)와 공유 레코드는
`abc2lab_contracts`가 소유한다. 여기서는 app이 주입하는 evidence 로컬 협력자만 둔다.
정규화·canary 규칙 내용은 judge 소유이며 app이 규칙 엔진으로 주입한다(evidence는
judge를 import하지 않는다). run HMAC 키와 감사 저널 쓰기는 주입 구현이 소유한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from abc2lab_contracts.audit import AuditReceipt, AuditRecordBinding
from abc2lab_contracts.capture import CaptureRequest, RawResponse, ReleaseCapturesRequest
from abc2lab_contracts.primitives import CheckState, CloseResult, Ref, ResponseClass, RunKey
from abc2lab_contracts.registration import OperationRegistration, ResourceBinding


@dataclass(frozen=True, slots=True)
class DataSignals:
    """규칙 엔진이 산출하는 비자명 데이터·반사·템플릿 신호다."""

    nontrivial_data_match: CheckState
    reflection_excluded: CheckState
    template_excluded: CheckState


class CaptureRegistry(Protocol):
    """app이 주입하는 등록 조회 뷰. capture 바인딩 검증에만 쓰는 읽기 전용이다."""

    def operation(self, operation_ref: Ref) -> OperationRegistration | None:
        """등록된 동작을 반환하고 없으면 None을 반환한다."""
        ...

    def resource_binding(self, resource_binding_ref: Ref) -> ResourceBinding | None:
        """등록된 자원 바인딩을 반환하고 없으면 None을 반환한다."""
        ...


class CaptureAccess(Protocol):
    """실행영역 캡처 저장소의 동기 읽기·해제 포트(LocalCaptureStore가 구현)."""

    def acquire(self, run_key: RunKey, capture_ref: Ref) -> CaptureRequest | None:
        """활성 캡처의 원문·맥락을 읽고 만료·부재·run 불일치는 None이다."""
        ...

    def release_captures(self, request: ReleaseCapturesRequest) -> CloseResult:
        """사용한 캡처를 멱등으로 해제한다."""
        ...


class ComparisonRuleEngine(Protocol):
    """judge 소유 규칙을 app이 주입한 엔진. 정규화·분류·오라클 신호를 수행한다."""

    def classify(self, raw: RawResponse) -> ResponseClass:
        """등록 규칙으로 응답 종류를 분류한다."""
        ...

    def normalize(self, raw: RawResponse) -> bytes:
        """HMAC 비교용 정규 바이트를 만든다. 제외 필드는 규칙이 정한다."""
        ...

    def assess_data(
        self, owner: RawResponse, cross: RawResponse, *, hmac_match: bool
    ) -> DataSignals:
        """canary로 비자명 일치·반사·템플릿을 판정한다. HMAC 일치만으로 YES 금지."""
        ...


class RunMac(Protocol):
    """run HMAC 계산 포트. 키는 구현 메모리에만 두고 결과·인자로 노출하지 않는다."""

    def compute(self, run_key: RunKey, data: bytes) -> bytes:
        """정규 바이트의 run HMAC 다이제스트를 반환한다."""
        ...


class EvidenceAuditJournal(Protocol):
    """Evidence 생산자 감사 저널 쓰기 포트. 선할당 event_ref/바인딩으로 commit한다."""

    async def commit(
        self, run_key: RunKey, producer: Ref, event_ref: Ref, binding: AuditRecordBinding
    ) -> AuditReceipt | None:
        """불변 artifact 감사를 내구 저장하고 영수증을 반환하거나 실패 시 None."""
        ...
