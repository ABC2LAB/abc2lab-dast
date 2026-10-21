"""실행 경계의 I/O 포트와 같은 loop의 즉시 세션 읽기 포트다."""

from typing import Protocol

from abc2lab_contracts.audit import (
    AuditPage,
    AuditReadRequest,
    AuditVerifyRequest,
    AuditVerifyResult,
)
from abc2lab_contracts.execution import (
    AttemptResult,
    ExecuteRequest,
    ExecutionRequest,
    PolicyDecisionResult,
    PolicyInput,
    PrepareResult,
)
from abc2lab_contracts.primitives import CloseResult, Ref, RunKey
from abc2lab_contracts.session import (
    SessionBindingResult,
    SessionContextCloseRequest,
    SessionContextRequest,
    SessionContextResult,
)


class GatewayPort(Protocol):
    """WebDiag가 사용하는 준비·실행 호출 계약이다."""

    async def prepare(self, request: ExecutionRequest) -> PrepareResult:
        """전송 없이 단일 소비 핸들과 정책 view를 준비한다."""
        ...

    async def execute(self, request: ExecuteRequest) -> AttemptResult:
        """검증한 핸들을 소비하고 알려진 전송 상태를 보존한다."""
        ...


class PolicyPort(Protocol):
    """정책 평가와 해당 결정의 감사 commit까지 대기하는 포트다."""

    async def evaluate(self, request: PolicyInput) -> PolicyDecisionResult:
        """기본 거부로 평가하고 저장을 확인한 결정만 반환한다."""
        ...


class SessionBindingReader(Protocol):
    """같은 loop·스레드에서 락과 I/O 없이 일관 snapshot을 읽는다."""

    def read_session_binding(self, run_key: RunKey, session_ref: Ref) -> SessionBindingResult:
        """await 없는 임계 구역에서도 즉시 현재 상태를 반환한다."""
        ...


class SessionContextPort(Protocol):
    """Gateway가 격리된 전송 context를 생성·종료하는 포트다."""

    async def open_session_context(self, request: SessionContextRequest) -> SessionContextResult:
        """로그인이나 대상 전송 없이 context만 할당한다."""
        ...

    async def close_session_context(self, request: SessionContextCloseRequest) -> CloseResult:
        """새 전송을 금지하고 context의 비밀을 정리한다."""
        ...


class AuditVerifier(Protocol):
    """자기 journal의 실제 저장 내용을 검증하는 생산자 포트다."""

    async def verify_committed(self, request: AuditVerifyRequest) -> AuditVerifyResult:
        """영수증 복사가 아닌 저장된 기록과 expected의 일치를 확인한다."""
        ...


class AuditReader(Protocol):
    """권한을 검사한 일관 감사 snapshot의 페이지를 읽는 포트다."""

    async def read_audit(self, request: AuditReadRequest) -> AuditPage:
        """미봉인·실패·봉인된 빈 journal을 구분해 반환한다."""
        ...
