"""`GatewayPort.execute` 구현: 핸들 소비 → §10 ①~⑤ → capture 인계.

순서(§10): ① 받은 Policy 결정의 commit 검증(+binding·view 재대조) → ② 전송 전 intent 기록·자기
commit 검증 → ③ 무-await 임계 구역 세션 재검사 → ④ 예산 원자 차감 → ⑤ transport·캡처 인계. ①②가
막으면 임계 구역·예산·transport에 **진입하지 않고** 감사 가능한 not_sent만 남긴다. intent는 ① 통과
경로에서만 기록한다(안 보낼 요청에 "보내려 했다" 감사를 남기지 않는다). transport 진입 후 미확정은
`unknown`이며 자동 재전송하지 않는다. 예산·Vault·transport·journal은 gateway 내부 주입 포트다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from abc2lab_contracts.audit import (
    AttemptRecord,
    AuditEventKind,
    AuditRecordBinding,
    AuditVerifyRequest,
    RequestIntentRecord,
    VerificationState,
)
from abc2lab_contracts.capture import CaptureRequest, ExecutedRequestView, RawResponse
from abc2lab_contracts.execution import AttemptResult, ExecuteRequest, PolicyDecision
from abc2lab_contracts.fingerprint import policy_decision_fingerprint, policy_input_fingerprint
from abc2lab_contracts.ports import AuditVerifier, LocalCapturePort, SessionBindingReader
from abc2lab_contracts.primitives import (
    AuditLink,
    Purpose,
    Ref,
    ResultStatus,
    RunKey,
)
from abc2lab_contracts.primitives import (
    CaptureStatus as WireCaptureStatus,
)
from abc2lab_contracts.primitives import (
    SendStatus as WireSendStatus,
)
from abc2lab_contracts.session import AuthSignal

from abc2lab_gateway.adapters.auth_signal import AuthSignalExtractor
from abc2lab_gateway.adapters.budget import BudgetLedger
from abc2lab_gateway.adapters.handles import PreparedHandleStore, PreparedRequest
from abc2lab_gateway.adapters.journal import (
    GatewayJournal,
    JournalCommitError,
    attempt_record_binding,
    intent_record_binding,
)
from abc2lab_gateway.adapters.translation import (
    AttemptContext,
    to_attempt_result,
    to_contract_reasons,
    to_decision_outcome,
)
from abc2lab_gateway.adapters.transport import SendCommand, Transport
from abc2lab_gateway.adapters.vault import VaultBinder
from abc2lab_gateway.core.model import (
    AttemptOutcome,
    CaptureStatus,
    DecisionCommit,
    DecisionOutcome,
    GatewayReason,
    PreTransportGate,
    RecheckResult,
    SendStatus,
    TransportObservation,
)
from abc2lab_gateway.core.outcome import classify_pre_transport, classify_transport

_LOGGER = logging.getLogger(__name__)
_ATTEMPT_RECORD_REVISION = 1


def new_attempt_ref(producer: Ref, run_key: RunKey) -> Ref:
    """다른 시도와 겹치지 않는 새 attempt_ref를 만든다(핸들 소비 직후 발급)."""
    return f"{producer}:{run_key.run_ref}:attempt:{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _not_sent(reason: GatewayReason) -> AttemptOutcome:
    """전송 미진입이 입증된 결과."""
    return AttemptOutcome(SendStatus.NOT_SENT, CaptureStatus.NOT_APPLICABLE, False, (reason,))


def _sent_unavailable(reason: GatewayReason) -> AttemptOutcome:
    """전송은 됐으나 캡처가 실패·불가한 결과. 전송 상태를 보존한다."""
    return AttemptOutcome(SendStatus.SENT, CaptureStatus.UNAVAILABLE, False, (reason,))


def make_request_intent(
    prepared: PreparedRequest,
    attempt_ref: Ref,
    decision: PolicyDecision,
    *,
    created_at: datetime,
) -> RequestIntentRecord:
    """전송 전 불변 intent를 준비 요청과 검증된 결정에서 구성한다(비밀·원문 미포함)."""
    return RequestIntentRecord(
        run_key=prepared.run_key,
        request_ref=prepared.request_ref,
        attempt_ref=attempt_ref,
        binding_id=decision.binding_id,
        operation_ref=prepared.request.operation_ref,
        operation_revision=prepared.request.operation_revision,
        purpose=prepared.request.purpose,
        account_ref=prepared.policy_input.account_ref,
        session_generation=prepared.policy_input.session_generation,
        decision_ref=decision.decision_ref,
        evaluated_view_fingerprint=policy_input_fingerprint(prepared.policy_input),
        created_at=created_at,
    )


@dataclass(frozen=True, slots=True)
class ExecuteDependencies:
    """app이 주입하는 execute 협력자. 모두 gateway 내부 포트다."""

    handles: PreparedHandleStore
    sessions: SessionBindingReader
    decision_verifier: AuditVerifier
    journal: GatewayJournal
    budget: BudgetLedger
    vault: VaultBinder
    transport: Transport
    capture: LocalCapturePort
    auth_extractor: AuthSignalExtractor
    clock: Callable[[], datetime] = _utc_now


@dataclass(frozen=True, slots=True)
class ExecuteSettings:
    """execute 설정. producer ref는 여기서만 받는다."""

    producer: Ref


class GatewayExecutor:
    """`GatewayPort.execute` 구현. 검증·게이트를 거친 뒤에만 전송하고 전송 상태를 보존한다."""

    def __init__(
        self,
        dependencies: ExecuteDependencies,
        settings: ExecuteSettings,
        *,
        attempt_ref_factory: Callable[[Ref, RunKey], Ref] = new_attempt_ref,
    ) -> None:
        self._deps = dependencies
        self._settings = settings
        self._new_attempt_ref = attempt_ref_factory

    async def execute(self, request: ExecuteRequest) -> AttemptResult:
        """핸들을 소비하고 §10 ①~⑤를 거쳐 알려진 전송 상태를 보존한 `AttemptResult`를 낸다."""
        prepared = self._deps.handles.consume(request.run_key, request.prepared_handle)
        attempt_ref = self._new_attempt_ref(self._settings.producer, request.run_key)
        if prepared is None or prepared.request_ref != request.request_ref:
            # 없음·소비됨·만료·run/request 불일치. 전송 0건.
            return await self._finish(
                request,
                None,
                attempt_ref,
                _not_sent(GatewayReason.PREPARED_HANDLE_INVALID),
                decision_ref=None,
                binding_id=None,
                capture_ref=None,
                audit_links=(),
            )

        decision_block = await self._check_decision(request, prepared)
        if decision_block is not None:
            outcome, decision_ref, binding_id = decision_block
            return await self._finish(
                request,
                prepared,
                attempt_ref,
                outcome,
                decision_ref=decision_ref,
                binding_id=binding_id,
                capture_ref=None,
                audit_links=(),
            )

        # ① 통과(ALLOW·VERIFIED·binding/view 일치). 이제 decision 참조는 신뢰할 수 있다.
        decision = request.decision
        assert decision is not None  # _check_decision이 None/BLOCK/미검증을 모두 걸렀다
        decision_ref, binding_id = decision.decision_ref, decision.binding_id

        intent_links = await self._commit_intent(request, prepared, attempt_ref, decision)
        if intent_links is None:
            return await self._finish(
                request,
                prepared,
                attempt_ref,
                _not_sent(GatewayReason.AUDIT_COMMIT_FAILED),
                decision_ref=decision_ref,
                binding_id=binding_id,
                capture_ref=None,
                audit_links=(),
            )

        # ③④ 무-await 임계 구역: 세션 재검사 → 예산 원자 차감 → 최종 게이트.
        now = self._deps.clock()
        recheck, transport_context_ref = self._recheck(prepared, now)
        budget_committed = False
        if recheck.passed:
            budget_committed = self._deps.budget.try_consume(
                request.run_key, binding_id, prepared.policy_input.budget.max_attempts
            )
        gate = PreTransportGate(
            decision=DecisionOutcome.ALLOW,
            audit_committed=True,
            recheck=recheck,
            budget_committed=budget_committed,
            decision_commit=DecisionCommit.VERIFIED,
        )
        gate_block = classify_pre_transport(gate)
        # 임계 구역 끝. 이후 await가 와도 재검사·예산 결정은 이미 확정됐다.
        if gate_block is not None:
            return await self._finish(
                request,
                prepared,
                attempt_ref,
                gate_block,
                decision_ref=decision_ref,
                binding_id=binding_id,
                capture_ref=None,
                audit_links=intent_links,
            )

        outcome, capture_ref, auth_signal = await self._transport_and_capture(
            request, prepared, attempt_ref, transport_context_ref, now
        )
        return await self._finish(
            request,
            prepared,
            attempt_ref,
            outcome,
            decision_ref=decision_ref,
            binding_id=binding_id,
            capture_ref=capture_ref,
            auth_signal=auth_signal,
            audit_links=intent_links,
        )

    async def _check_decision(
        self, request: ExecuteRequest, prepared: PreparedRequest
    ) -> tuple[AttemptOutcome, Ref | None, Ref | None] | None:
        """① 결정 outcome·commit·binding/view를 검증한다. 막으면 (not_sent, refs), 통과면 None."""
        decision = request.decision
        if decision is None:
            return _not_sent(GatewayReason.DECISION_MISSING), None, None
        expected_view = policy_input_fingerprint(prepared.policy_input)
        if (
            decision.binding_id != prepared.binding_id
            or decision.evaluated_view_fingerprint != expected_view
        ):
            # 결정이 이 준비 view의 것이 아니다. 검증된 참조가 없으므로 refs는 None.
            return _not_sent(GatewayReason.BINDING_MISMATCH), None, None
        expected = AuditRecordBinding(
            AuditEventKind.POLICY_DECISION,
            decision.decision_ref,
            1,
            policy_decision_fingerprint(decision),
            request.request_ref,
            None,
            decision.binding_id,
        )
        verification = await self._deps.decision_verifier.verify_committed(
            AuditVerifyRequest(request.run_key, decision.audit_receipt, expected)
        )
        if (
            verification.run_key != request.run_key
            or verification.state is VerificationState.INVALID
        ):
            return _not_sent(GatewayReason.DECISION_UNVERIFIED), None, None
        if verification.state is VerificationState.UNKNOWN:
            return _not_sent(GatewayReason.DECISION_VERIFICATION_UNKNOWN), None, None
        if to_decision_outcome(decision) is not DecisionOutcome.ALLOW:
            # 검증된 차단 결정. 참조는 신뢰할 수 있다.
            return (
                _not_sent(GatewayReason.POLICY_BLOCKED),
                decision.decision_ref,
                decision.binding_id,
            )
        return None

    async def _commit_intent(
        self,
        request: ExecuteRequest,
        prepared: PreparedRequest,
        attempt_ref: Ref,
        decision: PolicyDecision,
    ) -> tuple[AuditLink, ...] | None:
        """② intent를 기록·self verify한다. 성공하면 intent 감사 링크, 실패하면 None."""
        record = make_request_intent(prepared, attempt_ref, decision, created_at=self._deps.clock())
        try:
            receipt = await self._deps.journal.append_intent(record)
            verification = await self._deps.journal.verify_committed(
                AuditVerifyRequest(request.run_key, receipt, intent_record_binding(record))
            )
        except JournalCommitError as error:
            _LOGGER.error(
                "gateway intent commit failed: run=%s attempt=%s reason=%s",
                request.run_key.run_ref,
                attempt_ref,
                error.reason_code,
            )
            return None
        if (
            verification.run_key != request.run_key
            or verification.state is not VerificationState.VERIFIED
        ):
            _LOGGER.error(
                "gateway intent verification failed: run=%s attempt=%s state=%s",
                request.run_key.run_ref,
                attempt_ref,
                verification.state,
            )
            return None
        return (AuditLink(self._settings.producer, receipt.event_ref),)

    def _recheck(
        self, prepared: PreparedRequest, now: datetime
    ) -> tuple[RecheckResult, Ref | None]:
        """③ 전송 직전 세션 재검사(실행+owner). prepare snapshot 재사용이 아니라 지금 다시 읽는다.

        await 없는 동기 읽기다. 실행 세션의 현재 transport context 참조도 함께 돌려준다.
        """
        context_ref: Ref | None = None
        for handle, is_exec in (
            (prepared.request.session, True),
            (prepared.request.owner_session, False),
        ):
            if handle is None:
                continue
            result = self._deps.sessions.read_session_binding(prepared.run_key, handle.session_ref)
            if result.status is not ResultStatus.COMPLETE or result.binding is None:
                return RecheckResult(False, GatewayReason.SESSION_GENERATION_CHANGED), None
            binding = result.binding
            if binding.cancelled:
                return RecheckResult(False, GatewayReason.CANCELLED), None
            if binding.session.generation != handle.generation:
                return RecheckResult(False, GatewayReason.SESSION_GENERATION_CHANGED), None
            if now >= binding.session.expires_at:
                return RecheckResult(False, GatewayReason.DEADLINE_EXCEEDED), None
            if is_exec:
                context_ref = binding.transport_context_ref
        return RecheckResult(True), context_ref

    async def _transport_and_capture(
        self,
        request: ExecuteRequest,
        prepared: PreparedRequest,
        attempt_ref: Ref,
        transport_context_ref: Ref | None,
        observed_at: datetime,
    ) -> tuple[AttemptOutcome, Ref | None, AuthSignal | None]:
        """⑤ 자격 결합 → 전송 → 관찰 분류 → auth_signal 추출 → 캡처 동기 인계."""
        if transport_context_ref is not None:
            await self._deps.vault.bind(
                request.run_key, prepared.policy_input.account_ref, transport_context_ref
            )
        send = await self._deps.transport.send(
            SendCommand(request.run_key, attempt_ref, prepared.request, transport_context_ref)
        )
        outcome = classify_transport(send.observation)
        if send.observation is not TransportObservation.SENT_CAPTURED:
            return outcome, None, None
        if send.raw_response is None or send.executed_request is None:
            return _sent_unavailable(GatewayReason.CAPTURE_UNAVAILABLE), None, None
        auth_signal = await self._extract_auth_signal(
            prepared, send.raw_response, send.executed_request
        )
        capture = self._deps.capture.capture(
            CaptureRequest(
                run_key=request.run_key,
                attempt_ref=attempt_ref,
                request_ref=request.request_ref,
                operation_ref=prepared.request.operation_ref,
                resource_ref=prepared.request.resource_ref,
                account_ref=prepared.policy_input.account_ref,
                session_generation=prepared.policy_input.session_generation,
                identity_ref=prepared.policy_input.identity_ref,
                observed_at=observed_at,
                executed_request=send.executed_request,
                raw_response=send.raw_response,
            )
        )
        if capture.status is ResultStatus.COMPLETE and capture.capture_ref is not None:
            return outcome, capture.capture_ref, auth_signal
        # 캡처 실패는 전송 상태를 보존하고 sent/unavailable로 내린다.
        return _sent_unavailable(GatewayReason.CAPTURE_UNAVAILABLE), None, auth_signal

    async def _extract_auth_signal(
        self,
        prepared: PreparedRequest,
        response: RawResponse,
        executed: ExecutedRequestView,
    ) -> AuthSignal | None:
        """인증/신원 요청의 응답에서 비밀 없는 AuthSignal을 추출한다. 그 외 목적은 None.

        교차 목적 신호 누출을 막으려고 **그 요청의 purpose**를 그대로 넘긴다(AUTHENTICATE→
        login_result,
        IDENTIFY→identity). 추출기는 원문을 실행 메모리에서만 읽고 등록 별칭 subject만 반환한다.
        """
        purpose = prepared.request.purpose
        if purpose not in (Purpose.AUTHENTICATE, Purpose.IDENTIFY):
            return None
        if prepared.auth_profile_ref is None:
            return None
        return await self._deps.auth_extractor.extract(
            prepared.auth_profile_ref, purpose, response, executed
        )

    async def _finish(
        self,
        request: ExecuteRequest,
        prepared: PreparedRequest | None,
        attempt_ref: Ref,
        outcome: AttemptOutcome,
        *,
        decision_ref: Ref | None,
        binding_id: Ref | None,
        capture_ref: Ref | None,
        audit_links: tuple[AuditLink, ...],
        auth_signal: AuthSignal | None = None,
    ) -> AttemptResult:
        """공통 종결: AttemptRecord commit → self verify → `AttemptResult`.

        append/verify 실패는 알려진 전송 상태를 보존하고 사유에 `audit_commit_failed`를 더한다.
        """
        record = AttemptRecord(
            run_key=request.run_key,
            request_ref=request.request_ref,
            attempt_ref=attempt_ref,
            revision=_ATTEMPT_RECORD_REVISION,
            decision_ref=decision_ref,
            binding_id=binding_id,
            operation_ref=None if prepared is None else prepared.request.operation_ref,
            account_ref=None if prepared is None else prepared.policy_input.account_ref,
            session_generation=None
            if prepared is None
            else prepared.policy_input.session_generation,
            send_status=WireSendStatus(outcome.send_status.value),
            capture_status=WireCaptureStatus(outcome.capture_status.value),
            occurred_at=self._deps.clock(),
            reason_codes=to_contract_reasons(outcome.reason_codes),
        )
        links = audit_links
        try:
            receipt = await self._deps.journal.append_attempt(record)
            verification = await self._deps.journal.verify_committed(
                AuditVerifyRequest(request.run_key, receipt, attempt_record_binding(record))
            )
            if (
                verification.run_key == request.run_key
                and verification.state is VerificationState.VERIFIED
            ):
                links = audit_links + (AuditLink(self._settings.producer, receipt.event_ref),)
            else:
                outcome = _with_audit_failure(outcome)
        except JournalCommitError:
            outcome = _with_audit_failure(outcome)
        context = AttemptContext(
            run_key=request.run_key,
            request_ref=request.request_ref,
            attempt_ref=attempt_ref,
            decision_ref=decision_ref,
            binding_id=binding_id,
            capture_ref=capture_ref,
            auth_signal=auth_signal,
            audit_links=links,
        )
        result = to_attempt_result(outcome, context)
        _LOGGER.info(
            "gateway attempt: run=%s request=%s attempt=%s send=%s capture=%s",
            request.run_key.run_ref,
            request.request_ref,
            attempt_ref,
            result.send_status,
            result.capture_status,
        )
        return result


def _with_audit_failure(outcome: AttemptOutcome) -> AttemptOutcome:
    if GatewayReason.AUDIT_COMMIT_FAILED in outcome.reason_codes:
        return outcome
    return replace(
        outcome, reason_codes=outcome.reason_codes + (GatewayReason.AUDIT_COMMIT_FAILED,)
    )
