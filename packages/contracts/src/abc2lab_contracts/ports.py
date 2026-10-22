"""실행 경계의 I/O 포트와 같은 loop의 동기 메모리 포트다."""

from typing import Protocol

from abc2lab_contracts.audit import (
    AuditPage,
    AuditReadRequest,
    AuditVerifyRequest,
    AuditVerifyResult,
)
from abc2lab_contracts.capture import CaptureRequest, CaptureResult, ReleaseCapturesRequest
from abc2lab_contracts.evidence import (
    CompareOutcome,
    CompareRequest,
    EvidenceReadRequest,
    EvidenceReadResult,
    RecoverSubmissionRequest,
    RedactedBundle,
    SealRequest,
    SealResult,
    StoreOutcome,
)
from abc2lab_contracts.execution import (
    AttemptResult,
    ExecuteRequest,
    ExecutionRequest,
    PolicyDecisionResult,
    PolicyInput,
    PrepareResult,
)
from abc2lab_contracts.judge import (
    JudgePolicyReadRequest,
    JudgePolicyReadResult,
    JudgeRequest,
    JudgeResult,
)
from abc2lab_contracts.knowledge import (
    CandidateAck,
    CandidateSubmission,
    CaseReadRequest,
    CaseReadResult,
    ProjectionAck,
    ProjectionSubmission,
)
from abc2lab_contracts.primitives import CloseResult, Ref, RunKey
from abc2lab_contracts.session import (
    SessionBindingResult,
    SessionContextCloseRequest,
    SessionContextRequest,
    SessionContextResult,
)


class JudgePort(Protocol):
    """Authorize every call and publish only independently verified committed verdicts.

    ReadContext is excluded from semantic idempotency input, but cached results
    still require current read authorization. Providers match result run/case to
    the request and verify source records; constructor checks do not prove this.
    Before publishing ALLOWED, verify B's identity, canonical case/policy binding,
    applicability and validity at the evaluation time, then derive allow reasons
    from that verified policy. Neither a reason label nor unknown A/B-distinctness
    or cross-data checks establishes permission. Normal B identity absence is
    UNDECIDABLE; forged sources and failed verification/read boundaries fail the call.
    FAILED accepts only explicit call/audit failure reasons, never diagnostic reasons.
    """

    async def judge(self, request: JudgeRequest) -> JudgeResult:
        """Resolve the case policy and verify evidence before committing a verdict."""
        ...


class JudgePolicyReader(Protocol):
    """Read a case policy from app-injected immutable registration provenance.

    Authorize every read. Verify any supplied hint against its policy_ref,
    SourceVersion and full registered content before resolving the case policy
    independently. A complete result attests that this hint check succeeded;
    its policy is the case's canonical policy, not a copy of the hint. A different
    authentic hint is left for Judge to classify as UNDECIDABLE/policy-invalid.
    Missing policy on a known case is distinct from an unknown case, forgery or
    read failure. Only the latter fail the read. Match returned run/case to the
    request. No constructor proves provenance, authorization or an audit commit.
    Known absence returns exactly (EXPECTED_ACCESS_POLICY_MISSING,); FAILED uses
    only explicit call/audit failure reasons, without that normal-absence marker.
    """

    async def read_case_policy(self, request: JudgePolicyReadRequest) -> JudgePolicyReadResult:
        """Return a canonical policy or known absence; preserve source/read failures."""
        ...


class KnowledgePort(Protocol):
    """Expose Host-coordinated candidate registration, projection and snapshot reads."""

    async def register_candidates(self, request: CandidateSubmission) -> CandidateAck:
        """Normalize/deduplicate hints and retain accepted candidates on partial results."""
        ...

    async def project(self, request: ProjectionSubmission) -> ProjectionAck:
        """Verify producer records and dependencies before applying one source event."""
        ...

    async def get_case_view(self, request: CaseReadRequest) -> CaseReadResult:
        """Read an authorized bounded snapshot without silently replacing its revision."""
        ...


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


class LocalCapturePort(Protocol):
    """실행 로컬 영역에서만 쓰는 같은 loop·스레드의 동기 메모리 포트다.

    등록 정보·맥락·한도를 유한 메모리에서 대조하고 await·I/O·저장·분석 없이 인계한다.
    active -> released/expired, TTL 60초, 캡처당 1 MiB, run당 active 8개를 지킨다.
    1 MiB는 body bytes + 모든 헤더 name/value의 UTF-8 bytes 합계이며 객체 오버헤드는 제외한다.
    포트 구현은 실패·취소·만료·종료 시 참조를 정리하고 해제된 핸들의 재사용을 막는다.
    bytes/str의 물리적 소거를 보장하지 않으며 Host/LLM/MCP에 이 포트를 주입하지 않는다.
    """

    def capture(self, request: CaptureRequest) -> CaptureResult:
        """원문/view를 인계받고 불일치·한도 초과는 failed/None과 사유로 반환한다.

        완료 후 Gateway는 인계한 참조를 보유하지 않는다. 실패 시 Evidence가 인계받은
        참조를 정리하며 Gateway도 원문/view 참조를 버리고 알려진 전송 상태를 보존한다.
        경로·파라미터의 인증 값 제외와 등록 일치 검사는 주입된 등록 정보로 수행한다.
        """
        ...

    def release_captures(self, request: ReleaseCapturesRequest) -> CloseResult:
        """지정 핸들만 멱등 해제한다. 빈 tuple은 해당 run 종료 시 전체 정리다.

        해제 실패 시 사용 가능한 핸들을 남기지 않는다. 이 결과는 전송 상태를 바꾸지 않는다.
        """
        ...


class ExecutionEvidencePort(Protocol):
    """WebDiag-only sealing and idempotent reconciliation without public raw access."""

    async def seal(self, request: SealRequest) -> SealResult:
        """Consume the one-shot capture and verify its Evidence store/audit commits."""
        ...

    async def compare_and_seal(self, request: CompareRequest) -> CompareOutcome:
        """Consume A/B captures and verify three stores and producer audits."""
        ...

    async def recover_submission(
        self, request: RecoverSubmissionRequest
    ) -> SealResult | CompareOutcome:
        """Recheck without replay; validate_recovery_result enforces kind/run agreement."""
        ...


class EvidencePort(Protocol):
    """Authorized redacted storage and summary reads; no executable capture handles."""

    async def store_evidence(self, request: RedactedBundle) -> StoreOutcome:
        """Commit only typed redacted artifacts with independent source checks."""
        ...

    async def evidence_read_summary(self, request: EvidenceReadRequest) -> EvidenceReadResult:
        """Read only permitted committed summaries and comparisons."""
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
