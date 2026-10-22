"""`PolicyPort` 구현: 평가 → 결정 내용 → fingerprint → journal commit → 저장 검증.

등록은 app이 run별로 주입한 불변 snapshot에서만 오며 view의 snapshot이나 검사 결과로 대체하지
않는다(S1 §5). 결정은 내용 생성 → contracts의 typed content fingerprint → journal commit →
영수증 → `verify_committed` 대조 → `PolicyDecision.from_content` 순서로 만든다. 등록 부재·저장
실패·검증 불일치면 결정 없는 failed를 반환하며 실행 가능한 allow를 발급하지 않는다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from abc2lab_contracts.audit import AuditVerifyRequest, PolicyOutcome, VerificationState
from abc2lab_contracts.execution import (
    PolicyDecision,
    PolicyDecisionContent,
    PolicyDecisionResult,
    PolicyInput,
)
from abc2lab_contracts.fingerprint import policy_input_fingerprint
from abc2lab_contracts.primitives import ReasonCode, Ref, ResultStatus, RunKey, SourceVersion
from abc2lab_contracts.registration import (
    CrossExecutionConfirmation,
    ExecutionProfileSnapshot,
    ExpectedAccessPolicySnapshot,
    OperationRegistration,
    ScopeSnapshot,
)

from abc2lab_policy.adapters.journal import (
    JournalCommitError,
    PolicyDecisionJournal,
    decision_record_binding,
)
from abc2lab_policy.adapters.translation import (
    build_authorization_context,
    build_evaluation_request,
    to_contract_reasons,
)
from abc2lab_policy.adapters.view_checks import (
    check_cross_execution,
    check_injected_view_consistency,
    check_operation_binding,
    check_scope_profile_limits,
)
from abc2lab_policy.core.evaluation import evaluate as evaluate_rules
from abc2lab_policy.core.model import AuthorizationContext, PolicyEvaluation

_LOGGER = logging.getLogger(__name__)

# 이미 만료된 view·구성에 대한 block 결정이 issued_at < expires_at 불변식을 지키기 위한 최소
# 유효기간이다. allow는 만료된 view·구성에서 나오지 않으므로 이 값을 쓰지 않는다.
_EXPIRED_DECISION_VALIDITY = timedelta(seconds=1)


@dataclass(frozen=True, slots=True)
class PolicyRegistration:
    """한 run에 대해 app이 주입한 등록 snapshot과 정책 버전."""

    scope: ScopeSnapshot
    profile: ExecutionProfileSnapshot
    operations: tuple[OperationRegistration, ...]
    policy_version: SourceVersion
    expected_policies: tuple[ExpectedAccessPolicySnapshot, ...] = ()
    cross_confirmations: tuple[CrossExecutionConfirmation, ...] = ()
    is_revoked: bool = False


class PolicyRegistrationSource(Protocol):
    """run의 현재 등록을 I/O 없이 즉시 읽는 포트."""

    def registration_for(self, run_key: RunKey) -> PolicyRegistration | None:
        """run의 현재 등록 snapshot을 반환한다. 등록이 없으면 None."""
        ...


class InMemoryPolicyRegistrations:
    """run별 등록 snapshot 보관소. 교체로 범위 축소·허가 취소를 반영한다."""

    def __init__(self) -> None:
        self._by_run: dict[RunKey, PolicyRegistration] = {}

    def register(self, run_key: RunKey, registration: PolicyRegistration) -> None:
        """run의 등록을 설정하거나 교체한다."""
        self._by_run[run_key] = registration

    def registration_for(self, run_key: RunKey) -> PolicyRegistration | None:
        """run의 현재 등록 snapshot을 반환한다. 등록이 없으면 None."""
        return self._by_run.get(run_key)


def new_decision_ref() -> Ref:
    """다른 결정과 겹치지 않는 새 결정 참조를 만든다."""
    return f"policy-decision-{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class _Issuance:
    """결정 내용에 붙일 발급 메타데이터."""

    decision_ref: Ref
    policy_version: SourceVersion
    issued_at: datetime
    expires_at: datetime


class PolicyService:
    """기본 거부 평가와 결정 commit 검증을 수행하는 `PolicyPort` 구현."""

    def __init__(
        self,
        registrations: PolicyRegistrationSource,
        journal: PolicyDecisionJournal,
        *,
        clock: Callable[[], datetime] = _utc_now,
        decision_ref_factory: Callable[[], Ref] = new_decision_ref,
    ) -> None:
        self._registrations = registrations
        self._journal = journal
        self._clock = clock
        self._new_decision_ref = decision_ref_factory

    async def evaluate(self, request: PolicyInput) -> PolicyDecisionResult:
        """기본 거부로 평가하고 journal 저장을 검증한 결정만 반환한다.

        Returns:
            commit·검증된 allow/block 결정은 complete다. 등록 부재·저장 실패·검증 불일치는
            결정 없는 failed이며 실행 가능한 allow를 발급하지 않는다.
        """
        registration = self._registrations.registration_for(request.run_key)
        if registration is None:
            _LOGGER.error(
                "policy registration missing: run=%s request=%s",
                request.run_key.run_ref,
                request.request_ref,
            )
            return _failed(request.run_key, ReasonCode.CONFIGURATION_MISSING)

        now = self._clock()
        authorization = build_authorization_context(
            registration.scope,
            registration.profile,
            registration.operations,
            is_revoked=registration.is_revoked,
        )
        # 변조/위조는 코어 판정 전에 먼저 본다. 코어가 다른 이유로 block해도 변조 사유가 남는다.
        mismatch_reasons = _injected_mismatch_reasons(request, registration, now)
        view_fingerprint = policy_input_fingerprint(request)
        evaluation = evaluate_rules(
            build_evaluation_request(request, view_fingerprint), authorization, now
        )
        resolved = _resolve_outcome(evaluation, mismatch_reasons)
        issuance = _Issuance(
            decision_ref=self._new_decision_ref(),
            policy_version=registration.policy_version,
            issued_at=now,
            expires_at=_decision_expiry(now, _expiry_bounds(request, authorization)),
        )
        content = _decision_content(request, evaluation, resolved, issuance)
        return await self._commit_verified(request, content)

    async def _commit_verified(
        self, request: PolicyInput, content: PolicyDecisionContent
    ) -> PolicyDecisionResult:
        """결정을 commit하고 저장 기록을 대조한 뒤에만 complete를 반환한다."""
        try:
            receipt = await self._journal.append(content, request.request_ref)
        except JournalCommitError as error:
            _log_failure("commit failed", content, error.reason_code)
            return _failed(request.run_key, error.reason_code)

        expected = decision_record_binding(content, request.request_ref)
        if receipt.run_key != request.run_key or receipt.binding != expected:
            # journal이 다른 기록의 영수증을 돌려줬다. 저장된 내용이 이 결정이라고 볼 수 없다.
            _log_failure("receipt mismatch", content, ReasonCode.AUDIT_COMMIT_FAILED)
            return _failed(request.run_key, ReasonCode.AUDIT_COMMIT_FAILED)

        verification = await self._journal.verify_committed(
            AuditVerifyRequest(run_key=request.run_key, receipt=receipt, expected=expected)
        )
        # 다른 run의 VERIFIED를 돌려주는 잘못된 어댑터를 수락하지 않는다.
        verified = (
            verification.run_key == request.run_key
            and verification.state is VerificationState.VERIFIED
        )
        if not verified:
            reason = (
                ReasonCode.AUDIT_VERIFICATION_UNKNOWN
                if verification.state is VerificationState.UNKNOWN
                else ReasonCode.AUDIT_COMMIT_FAILED
            )
            _log_failure("verification failed", content, reason)
            return _failed(request.run_key, reason, *verification.reason_codes)

        decision = PolicyDecision.from_content(content, receipt)
        _LOGGER.info(
            "policy decision committed: run=%s request=%s decision=%s outcome=%s",
            request.run_key.run_ref,
            request.request_ref,
            decision.decision_ref,
            decision.outcome,
        )
        return PolicyDecisionResult(request.run_key, ResultStatus.COMPLETE, decision, ())


@dataclass(frozen=True, slots=True)
class _ResolvedOutcome:
    """코어 평가와 주입 원본 대조를 합친 최종 판정."""

    outcome: PolicyOutcome
    reason_codes: tuple[ReasonCode, ...]


def _injected_mismatch_reasons(
    request: PolicyInput, registration: PolicyRegistration, now: datetime
) -> tuple[ReasonCode, ...]:
    """주입 원본 대조(view 일관성·실제 범위/프로필 제한·동작 바인딩·교차 실행)의 사유를 모은다."""
    reasons: list[ReasonCode] = []
    for single in (
        check_injected_view_consistency(request, registration.scope, registration.profile),
        check_scope_profile_limits(request, registration.scope, registration.profile, now),
        check_operation_binding(request, registration.operations),
    ):
        if single is not None:
            reasons.append(single)
    reasons.extend(
        check_cross_execution(
            request, registration.expected_policies, registration.cross_confirmations, now
        )
    )
    return tuple(reasons)


def _resolve_outcome(
    evaluation: PolicyEvaluation, mismatch_reasons: tuple[ReasonCode, ...]
) -> _ResolvedOutcome:
    """변조 사유와 코어 거부 사유를 합친다. 하나라도 있으면 block, 둘 다 없으면 allow."""
    core_reasons = () if evaluation.is_allow else to_contract_reasons(evaluation.reason_codes)
    reasons = tuple(dict.fromkeys(mismatch_reasons + core_reasons))
    if reasons:
        return _ResolvedOutcome(PolicyOutcome.BLOCK, reasons)
    return _ResolvedOutcome(PolicyOutcome.ALLOW, ())


def _decision_content(
    request: PolicyInput,
    evaluation: PolicyEvaluation,
    resolved: _ResolvedOutcome,
    issuance: _Issuance,
) -> PolicyDecisionContent:
    """내부 판정·주입 대조 결과를 receipt 없는 공개 결정 내용으로 조립한다."""
    return PolicyDecisionContent(
        run_key=request.run_key,
        decision_ref=issuance.decision_ref,
        binding_id=evaluation.binding_id,
        evaluated_view_fingerprint=evaluation.view_fingerprint,
        outcome=resolved.outcome,
        policy_version=issuance.policy_version,
        issued_at=issuance.issued_at,
        expires_at=issuance.expires_at,
        reason_codes=resolved.reason_codes,
    )


def _expiry_bounds(
    request: PolicyInput, authorization: AuthorizationContext
) -> tuple[datetime, ...]:
    """결정 유효기간을 제한하는 상한들. 교차면 기대 정책·확인 만료까지 포함한다."""
    bounds = [request.expires_at]
    if authorization.configuration_expires_at is not None:
        bounds.append(authorization.configuration_expires_at)
    if request.expected_policy is not None:
        bounds.append(request.expected_policy.valid_until)
    if request.cross_confirmation is not None:
        bounds.append(request.cross_confirmation.valid_until)
    return tuple(bounds)


def _decision_expiry(issued_at: datetime, bounds: tuple[datetime, ...]) -> datetime:
    """상한들의 최솟값으로 결정 유효기간을 제한한다. 이미 만료됐으면 최소 기간만 둔다."""
    expiry = min(bounds)
    if expiry <= issued_at:
        return issued_at + _EXPIRED_DECISION_VALIDITY
    return expiry


def _failed(run_key: RunKey, *reasons: ReasonCode) -> PolicyDecisionResult:
    """실행 가능한 결정 없이 사유만 담은 failed 결과를 만든다. 사유 중복은 제거한다."""
    return PolicyDecisionResult(run_key, ResultStatus.FAILED, None, tuple(dict.fromkeys(reasons)))


def _log_failure(stage: str, content: PolicyDecisionContent, reason: ReasonCode) -> None:
    _LOGGER.error(
        "policy decision %s: run=%s decision=%s reason=%s",
        stage,
        content.run_key.run_ref,
        content.decision_ref,
        reason,
    )
