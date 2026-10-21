"""C2 변환 어댑터의 단위 테스트. 네트워크·DB 없이 실행한다."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from abc2lab_contracts.audit import PolicyOutcome
from abc2lab_contracts.execution import PolicyAttributes, PolicyIdentityStatus, PolicyInput
from abc2lab_contracts.primitives import Purpose, ReasonCode, RunKey, SourceVersion
from abc2lab_contracts.registration import (
    BudgetSnapshot,
    ExecutionProfileSnapshot,
    OperationRegistration,
    ScopeSnapshot,
)
from abc2lab_policy.adapters import (
    build_authorization_context,
    build_evaluation_request,
    source_version_key,
    to_contract_reasons,
    to_policy_outcome,
)
from abc2lab_policy.core import IdentityStatus, Outcome, PolicyReason, evaluate
from abc2lab_policy.core import Purpose as CorePurpose

_NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)
_SOURCE = SourceVersion(issuer="iss", source_ref="orders", revision=1)
_RUN_KEY = RunKey(organization_ref="org", target_ref="tgt", environment_ref="env", run_ref="run-1")

_SCOPE = ScopeSnapshot(
    source=_SOURCE,
    allowed_origins=("https://app.test",),
    allowed_operation_refs=("op-observe",),
    valid_from=_NOW - timedelta(hours=1),
    valid_until=_NOW + timedelta(hours=1),
)

_PROFILE = ExecutionProfileSnapshot(
    source=_SOURCE,
    allowed_methods=("GET",),
    allowed_purposes=(Purpose.OBSERVE, Purpose.ACCESS_COMPARE),
    allow_redirects=False,
    valid_until=_NOW + timedelta(hours=2),
)

_OPERATION = OperationRegistration(
    source=_SOURCE,
    operation_ref="op-observe",
    allowed_purposes=(Purpose.OBSERVE, Purpose.ACCESS_COMPARE),
    auth_profile_ref=None,
    method="GET",
    origin="https://app.test",
    path_template="/orders/{id}",
    resource_bindings=(),
)

_ATTRIBUTES = PolicyAttributes(
    registered_path_matches=True,
    parameter_names=("id",),
    parameters_match_registration=True,
    resource_ref="res-1",
    resource_binding_ref="rb-1",
    resource_binding_revision=1,
    resource_owner_subject_ref="subject-a",
    provenance=_SOURCE,
)

_BUDGET = BudgetSnapshot(
    source=_SOURCE, max_attempts=5, max_duration_ms=1000, max_response_bytes=1024
)

_POLICY_INPUT = PolicyInput(
    schema_version="policy_input.v1",
    run_key=_RUN_KEY,
    request_ref="request-1",
    binding_id="binding-1",
    binding_issuer="issuer-1",
    expires_at=_NOW + timedelta(minutes=10),
    origin="https://app.test",
    method="GET",
    operation_ref="op-observe",
    operation_revision=1,
    purpose=Purpose.OBSERVE,
    policy_attributes=_ATTRIBUTES,
    account_ref="acct-a",
    session_generation=1,
    identity_ref="id-a",
    subject_ref="subject-a",
    identity_status=PolicyIdentityStatus.VERIFIED,
    owner_identity=None,
    scope=_SCOPE,
    profile=_PROFILE,
    budget=_BUDGET,
    expected_policy=None,
    cross_confirmation=None,
)


def test_source_version_key_is_stable() -> None:
    assert source_version_key(_SOURCE) == "iss:orders:1"


def test_build_evaluation_request_maps_view_fields() -> None:
    request = build_evaluation_request(_POLICY_INPUT, "a" * 64)
    assert request.run_key == "run-1"
    assert request.request_ref == "request-1"
    assert request.binding_id == "binding-1"
    assert request.origin == "https://app.test"
    assert request.method == "GET"
    assert request.operation_ref == "op-observe"
    assert request.operation_source == "iss:orders:1"
    assert request.purpose is CorePurpose.OBSERVE
    assert request.identity_status is IdentityStatus.VERIFIED
    assert request.view_fingerprint == "a" * 64
    assert request.binding_expires_at == _POLICY_INPUT.expires_at
    assert request.has_cross_confirmation is False


def test_build_authorization_context_intersects_purposes() -> None:
    context = build_authorization_context(_SCOPE, _PROFILE, (_OPERATION,))
    operation = context.registered_operations["op-observe"]
    assert operation.allowed_purposes == (CorePurpose.OBSERVE, CorePurpose.ACCESS_COMPARE)
    assert operation.source == "iss:orders:1"
    assert context.in_scope_operation_refs == frozenset({"op-observe"})
    assert context.configuration_expires_at == _SCOPE.valid_until
    assert context.is_revoked is False


def test_build_authorization_context_drops_purposes_outside_profile() -> None:
    narrow_profile = replace(_PROFILE, allowed_purposes=(Purpose.ACCESS_COMPARE,))
    context = build_authorization_context(_SCOPE, narrow_profile, (_OPERATION,))
    operation = context.registered_operations["op-observe"]
    assert operation.allowed_purposes == (CorePurpose.ACCESS_COMPARE,)


def test_to_policy_outcome_maps_values() -> None:
    assert to_policy_outcome(Outcome.ALLOW) is PolicyOutcome.ALLOW
    assert to_policy_outcome(Outcome.BLOCK) is PolicyOutcome.BLOCK


def test_to_contract_reasons_drops_allowed_and_maps() -> None:
    assert to_contract_reasons((PolicyReason.ALLOWED,)) == ()
    assert to_contract_reasons((PolicyReason.OUT_OF_SCOPE,)) == (ReasonCode.SCOPE_MISMATCH,)
    assert to_contract_reasons((PolicyReason.CROSS_CONFIRMATION_MISSING,)) == (
        ReasonCode.CROSS_CONFIRMATION_MISSING,
    )


def test_distilled_happy_path_allows() -> None:
    request = build_evaluation_request(_POLICY_INPUT, "a" * 64)
    authorization = build_authorization_context(_SCOPE, _PROFILE, (_OPERATION,))
    result = evaluate(request, authorization, _NOW)
    assert result.outcome is Outcome.ALLOW
