"""세션 인증·주체 확인 orchestration. 이번 단계는 whoami(주체 확인)를 구현한다.

빌딩블록(request_builder·run_request·auth_signal)을 엮어 identify 요청을 수행하고, 주체가
검증되면 응답 근거를 봉인(seal)해 evidence_ref를 얻고 identity journal에 commit한 뒤에만
VERIFIED IdentityResult를 발행한다. 미검증·근거/감사 실패는 확정하지 않고 사유를 보존한다.
"""

from __future__ import annotations

from datetime import timedelta

from abc2lab_contracts.evidence import SealRequest
from abc2lab_contracts.ports import GatewayPort, PolicyPort
from abc2lab_contracts.primitives import AttemptSummary, Purpose, ReasonCode, Ref, ResultStatus
from abc2lab_contracts.session import (
    IdentityContent,
    IdentityResult,
    IdentityStatus,
    SessionHandle,
)
from abc2lab_contracts.webdiag import IdentityRequest

from abc2lab_webdiag.core.auth_signal import identity_status
from abc2lab_webdiag.core.identity_ports import (
    EvidenceSealer,
    IdentityJournal,
    IdentityProfile,
    IdentityProfileRegistry,
    WebDiagClock,
)
from abc2lab_webdiag.core.request_builder import ExecutionPlan, build_execution_request
from abc2lab_webdiag.core.request_cycle import run_request, to_attempt_summary


class SessionAuthenticator:
    """등록 프로필과 실행 포트로 주체 확인(및 이후 세션 확보)을 조정한다."""

    __slots__ = ("_registry", "_clock", "_gateway", "_policy", "_evidence", "_journal")

    def __init__(
        self,
        registry: IdentityProfileRegistry,
        clock: WebDiagClock,
        gateway: GatewayPort,
        policy: PolicyPort,
        evidence: EvidenceSealer,
        journal: IdentityJournal,
    ) -> None:
        """등록 조회·시계·Gateway·Policy·로컬 Evidence·identity journal을 주입받는다."""
        self._registry = registry
        self._clock = clock
        self._gateway = gateway
        self._policy = policy
        self._evidence = evidence
        self._journal = journal

    async def whoami(self, request: IdentityRequest) -> IdentityResult:
        """현재 세션의 실제 주체를 확인한다. 로그인 성공과 별개이며(§8.3) 확정만 유보한다."""
        session = request.session
        profile = self._registry.resolve(request.identity_profile_ref)
        if profile is None:
            return self._unverified(
                session, IdentityStatus.UNKNOWN, None, (), (ReasonCode.UNSUPPORTED_AUTHENTICATION,)
            )
        plan = ExecutionPlan(
            run_key=request.run_key,
            request_ref=self._clock.new_ref("request"),
            operation=profile.operation,
            purpose=Purpose.IDENTIFY,
            scope_revision=profile.scope_revision,
            profile_revision=profile.profile_revision,
            timeout_ms=profile.timeout_ms,
            session=session,
        )
        outcome = await run_request(self._gateway, self._policy, build_execution_request(plan))
        if outcome.attempt is None:
            return self._unverified(session, IdentityStatus.UNKNOWN, None, (), outcome.reason_codes)
        summaries = (to_attempt_summary(outcome.attempt),)
        status, subject = identity_status(outcome.attempt.auth_signal, profile.expected_subject_ref)
        if status is not IdentityStatus.VERIFIED:
            return self._unverified(
                session, status, subject, summaries, outcome.attempt.reason_codes
            )
        return await self._confirm_verified(
            session, subject, outcome.attempt.capture_ref, summaries, profile
        )

    async def _confirm_verified(
        self,
        session: SessionHandle,
        subject: Ref | None,
        capture_ref: Ref | None,
        summaries: tuple[AttemptSummary, ...],
        profile: IdentityProfile,
    ) -> IdentityResult:
        """검증된 주체의 근거를 봉인·감사 commit한 뒤에만 VERIFIED를 발행한다."""
        if capture_ref is None:
            return self._unverified(
                session,
                IdentityStatus.UNKNOWN,
                subject,
                summaries,
                (ReasonCode.CAPTURE_UNAVAILABLE,),
            )
        seal = await self._evidence.seal(
            SealRequest(
                run_key=session.run_key,
                submission_ref=self._clock.new_ref("submission"),
                capture_ref=capture_ref,
                rules=profile.rules,
            )
        )
        if seal.status is not ResultStatus.COMPLETE or seal.evidence is None:
            reasons = seal.reason_codes or (ReasonCode.EVIDENCE_STORE_FAILED,)
            return self._unverified(session, IdentityStatus.UNKNOWN, subject, summaries, reasons)
        now = self._clock.now()
        content = IdentityContent(
            run_key=session.run_key,
            identity_ref=self._clock.new_ref("identity"),
            status=IdentityStatus.VERIFIED,
            session_ref=session.session_ref,
            account_ref=session.account_ref,
            generation=session.generation,
            subject_ref=subject,
            evidence_ref=seal.evidence.evidence_ref,
            verified_at=now,
            valid_until=now + timedelta(milliseconds=profile.identity_ttl_ms),
            attempt_summaries=summaries,
            reason_codes=(),
        )
        commit = await self._journal.commit_identity(content)
        if commit.receipt is None:
            reasons = commit.reason_codes or (ReasonCode.AUDIT_COMMIT_FAILED,)
            return self._unverified(session, IdentityStatus.UNKNOWN, subject, summaries, reasons)
        return IdentityResult.from_content(content, commit.receipt)

    def _unverified(
        self,
        session: SessionHandle,
        status: IdentityStatus,
        subject: Ref | None,
        summaries: tuple[AttemptSummary, ...],
        reason_codes: tuple[ReasonCode, ...],
    ) -> IdentityResult:
        """근거·감사 없이 미검증 신원 결과를 만든다(VERIFIED는 여기서 발행하지 않음)."""
        return IdentityResult(
            run_key=session.run_key,
            identity_ref=None,
            status=status,
            session_ref=session.session_ref,
            account_ref=session.account_ref,
            generation=session.generation,
            subject_ref=subject,
            evidence_ref=None,
            verified_at=None,
            valid_until=None,
            audit_receipt=None,
            attempt_summaries=summaries,
            reason_codes=reason_codes,
        )
