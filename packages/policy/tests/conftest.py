"""policy 어댑터 테스트의 공용 C2 fixture. 네트워크·DB 없이 만든다."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from abc2lab_contracts.audit import AuditEventKind, AuditRecordBinding
from abc2lab_contracts.execution import (
    PolicyAttributes,
    PolicyDecision,
    PolicyIdentityStatus,
    PolicyInput,
)
from abc2lab_contracts.fingerprint import policy_decision_fingerprint
from abc2lab_contracts.primitives import Purpose, Ref, RunKey, SourceVersion
from abc2lab_contracts.registration import (
    BudgetSnapshot,
    CrossExecutionConfirmation,
    ExecutionProfileSnapshot,
    ExpectedAccess,
    ExpectedAccessPolicySnapshot,
    OperationRegistration,
    ResolutionState,
    ResourceBinding,
    ScopeSnapshot,
)
from abc2lab_contracts.session import IdentityBindingSummary
from abc2lab_policy.adapters import PolicyRegistration


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def source() -> SourceVersion:
    return SourceVersion(issuer="iss", source_ref="orders", revision=1)


@pytest.fixture
def run_key() -> RunKey:
    return RunKey(organization_ref="org", target_ref="tgt", environment_ref="env", run_ref="run-1")


@pytest.fixture
def scope(now: datetime, source: SourceVersion) -> ScopeSnapshot:
    return ScopeSnapshot(
        source=source,
        allowed_origins=("https://app.test",),
        allowed_operation_refs=("op-observe",),
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
    )


@pytest.fixture
def profile(now: datetime, source: SourceVersion) -> ExecutionProfileSnapshot:
    return ExecutionProfileSnapshot(
        source=source,
        allowed_methods=("GET",),
        allowed_purposes=(Purpose.OBSERVE, Purpose.ACCESS_COMPARE),
        allow_redirects=False,
        valid_until=now + timedelta(hours=2),
    )


@pytest.fixture
def operation(source: SourceVersion) -> OperationRegistration:
    return OperationRegistration(
        source=source,
        operation_ref="op-observe",
        allowed_purposes=(Purpose.OBSERVE, Purpose.ACCESS_COMPARE),
        auth_profile_ref=None,
        method="GET",
        origin="https://app.test",
        path_template="/orders/{id}",
        resource_bindings=(
            ResourceBinding(
                resource_binding_ref="rb-1",
                source=source,
                resource_ref="res-1",
                owner_subject_ref="subject-a",
                parameters=(),
            ),
        ),
    )


@pytest.fixture
def policy_input(
    now: datetime,
    run_key: RunKey,
    source: SourceVersion,
    scope: ScopeSnapshot,
    profile: ExecutionProfileSnapshot,
) -> PolicyInput:
    return PolicyInput(
        schema_version="policy_input.v1",
        run_key=run_key,
        request_ref="request-1",
        binding_id="binding-1",
        binding_issuer="gateway-1",
        expires_at=now + timedelta(minutes=10),
        origin="https://app.test",
        method="GET",
        operation_ref="op-observe",
        operation_revision=1,
        purpose=Purpose.OBSERVE,
        policy_attributes=PolicyAttributes(
            registered_path_matches=True,
            parameter_names=("id",),
            parameters_match_registration=True,
            resource_ref="res-1",
            resource_binding_ref="rb-1",
            resource_binding_revision=1,
            resource_owner_subject_ref="subject-a",
            provenance=source,
        ),
        account_ref="acct-a",
        session_generation=1,
        identity_ref="id-a",
        subject_ref="subject-a",
        identity_status=PolicyIdentityStatus.VERIFIED,
        owner_identity=None,
        scope=scope,
        profile=profile,
        budget=BudgetSnapshot(
            source=source, max_attempts=5, max_duration_ms=1000, max_response_bytes=1024
        ),
        expected_policy=None,
        cross_confirmation=None,
    )


@pytest.fixture
def registration(
    scope: ScopeSnapshot, profile: ExecutionProfileSnapshot, operation: OperationRegistration
) -> PolicyRegistration:
    return PolicyRegistration(
        scope=scope,
        profile=profile,
        operations=(operation,),
        policy_version=SourceVersion(issuer="iss", source_ref="policy-rules", revision=1),
    )


@pytest.fixture
def owner_identity(now: datetime) -> IdentityBindingSummary:
    """교차 실행의 소유자(A) 신원 요약. 평가 주체(B)와 계정·주체가 다르다."""
    return IdentityBindingSummary(
        identity_ref="identity-a",
        session_ref="session-a",
        account_ref="acct-a",
        subject_ref="subject-a",
        generation=1,
        verified_at=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
    )


@pytest.fixture
def expected_policy(now: datetime, source: SourceVersion) -> ExpectedAccessPolicySnapshot:
    """등록된 deny + resolved_none/resolved_none 교차 정책 원본."""
    return ExpectedAccessPolicySnapshot(
        source=source,
        policy_ref="policy-ab",
        target_ref="tgt",
        environment_ref="env",
        resource_ref="res-1",
        operation_ref="op-compare",
        owner_subject_ref="subject-a",
        evaluated_subject_ref="subject-b",
        expected_access=ExpectedAccess.DENY,
        sharing=ResolutionState.RESOLVED_NONE,
        delegation=ResolutionState.RESOLVED_NONE,
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
    )


@pytest.fixture
def cross_confirmation(
    now: datetime, run_key: RunKey, source: SourceVersion
) -> CrossExecutionConfirmation:
    """A→B 계정 쌍을 확인하는 등록 원본."""
    return CrossExecutionConfirmation(
        source=source,
        run_key=run_key,
        resource_ref="res-1",
        operation_ref="op-compare",
        owner_account_ref="acct-a",
        evaluated_account_ref="acct-b",
        valid_until=now + timedelta(minutes=30),
    )


@pytest.fixture
def cross_scope(now: datetime, source: SourceVersion) -> ScopeSnapshot:
    return ScopeSnapshot(
        source=source,
        allowed_origins=("https://app.test",),
        allowed_operation_refs=("op-compare",),
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
    )


@pytest.fixture
def cross_profile(now: datetime, source: SourceVersion) -> ExecutionProfileSnapshot:
    return ExecutionProfileSnapshot(
        source=source,
        allowed_methods=("GET",),
        allowed_purposes=(Purpose.OBSERVE, Purpose.ACCESS_COMPARE),
        allow_redirects=False,
        valid_until=now + timedelta(hours=2),
    )


@pytest.fixture
def cross_operation(source: SourceVersion) -> OperationRegistration:
    return OperationRegistration(
        source=source,
        operation_ref="op-compare",
        allowed_purposes=(Purpose.OBSERVE, Purpose.ACCESS_COMPARE),
        auth_profile_ref=None,
        method="GET",
        origin="https://app.test",
        path_template="/orders/{id}",
        resource_bindings=(
            ResourceBinding(
                resource_binding_ref="rb-1",
                source=source,
                resource_ref="res-1",
                owner_subject_ref="subject-a",
                parameters=(),
            ),
        ),
    )


@pytest.fixture
def cross_policy_input(
    now: datetime,
    run_key: RunKey,
    source: SourceVersion,
    cross_scope: ScopeSnapshot,
    cross_profile: ExecutionProfileSnapshot,
    owner_identity: IdentityBindingSummary,
    expected_policy: ExpectedAccessPolicySnapshot,
    cross_confirmation: CrossExecutionConfirmation,
) -> PolicyInput:
    """평가 주체 B(acct-b/subject-b)가 소유자 A의 자원을 교차 실행하려는 view."""
    return PolicyInput(
        schema_version="policy_input.v1",
        run_key=run_key,
        request_ref="request-x",
        binding_id="binding-x",
        binding_issuer="gateway-1",
        expires_at=now + timedelta(minutes=10),
        origin="https://app.test",
        method="GET",
        operation_ref="op-compare",
        operation_revision=1,
        purpose=Purpose.ACCESS_COMPARE,
        policy_attributes=PolicyAttributes(
            registered_path_matches=True,
            parameter_names=("id",),
            parameters_match_registration=True,
            resource_ref="res-1",
            resource_binding_ref="rb-1",
            resource_binding_revision=1,
            resource_owner_subject_ref="subject-a",
            provenance=source,
        ),
        account_ref="acct-b",
        session_generation=1,
        identity_ref="identity-b",
        subject_ref="subject-b",
        identity_status=PolicyIdentityStatus.VERIFIED,
        owner_identity=owner_identity,
        scope=cross_scope,
        profile=cross_profile,
        budget=BudgetSnapshot(
            source=source, max_attempts=5, max_duration_ms=1000, max_response_bytes=1024
        ),
        expected_policy=expected_policy,
        cross_confirmation=cross_confirmation,
    )


@pytest.fixture
def cross_registration(
    cross_scope: ScopeSnapshot,
    cross_profile: ExecutionProfileSnapshot,
    cross_operation: OperationRegistration,
    expected_policy: ExpectedAccessPolicySnapshot,
    cross_confirmation: CrossExecutionConfirmation,
) -> PolicyRegistration:
    """교차 정책·확인 원본을 담은 등록."""
    return PolicyRegistration(
        scope=cross_scope,
        profile=cross_profile,
        operations=(cross_operation,),
        policy_version=SourceVersion(issuer="iss", source_ref="policy-rules", revision=1),
        expected_policies=(expected_policy,),
        cross_confirmations=(cross_confirmation,),
    )


@pytest.fixture
def gateway_expected() -> Callable[[PolicyDecision, Ref], AuditRecordBinding]:
    """reference Gateway처럼 받은 결정의 업무 필드만으로 expected binding을 독립 계산한다."""

    def build(decision: PolicyDecision, request_ref: Ref) -> AuditRecordBinding:
        return AuditRecordBinding(
            event_kind=AuditEventKind.POLICY_DECISION,
            record_ref=decision.decision_ref,
            record_revision=1,
            record_fingerprint=policy_decision_fingerprint(decision),
            request_ref=request_ref,
            attempt_ref=None,
            binding_id=decision.binding_id,
        )

    return build
