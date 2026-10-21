"""기본 거부 정책 평가의 단위 테스트. 네트워크·DB·브라우저 없이 실행한다."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from abc2lab_policy.core import (
    AuthorizationContext,
    EvaluationRequest,
    IdentityStatus,
    Outcome,
    PolicyReason,
    Purpose,
    RegisteredOperation,
    evaluate,
)

_NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)

_OPERATION = RegisteredOperation(
    operation_ref="operation-observe",
    source="orders.v1",
    origin="https://app.test",
    method="GET",
    allowed_purposes=(Purpose.OBSERVE, Purpose.ACCESS_COMPARE),
    is_business_write=False,
)

_AUTHORIZATION = AuthorizationContext(
    registered_operations={_OPERATION.operation_ref: _OPERATION},
    in_scope_operation_refs=frozenset({_OPERATION.operation_ref}),
    read_only_profile=True,
    is_revoked=False,
    configuration_expires_at=_NOW + timedelta(hours=1),
)

_REQUEST = EvaluationRequest(
    run_key="run-1",
    request_ref="request-1",
    binding_id="binding-1",
    view_fingerprint="a" * 64,
    origin="https://app.test",
    method="GET",
    operation_ref=_OPERATION.operation_ref,
    operation_source="orders.v1",
    purpose=Purpose.OBSERVE,
    identity_status=IdentityStatus.VERIFIED,
    binding_expires_at=_NOW + timedelta(minutes=10),
)


def _with_operation(operation: RegisteredOperation) -> AuthorizationContext:
    """단일 등록 동작을 바꾼 authorization을 만든다."""
    return replace(_AUTHORIZATION, registered_operations={operation.operation_ref: operation})


def test_allows_registered_in_scope_verified_observe() -> None:
    result = evaluate(_REQUEST, _AUTHORIZATION, _NOW)
    assert result.outcome is Outcome.ALLOW
    assert result.is_allow
    assert result.reason_codes == (PolicyReason.ALLOWED,)


def test_preserves_binding_on_allow() -> None:
    result = evaluate(_REQUEST, _AUTHORIZATION, _NOW)
    assert result.binding_id == "binding-1"
    assert result.view_fingerprint == "a" * 64
    assert result.run_key == "run-1"
    assert result.request_ref == "request-1"


def test_defaults_to_block_for_unregistered_operation() -> None:
    authorization = replace(_AUTHORIZATION, registered_operations={})
    result = evaluate(_REQUEST, authorization, _NOW)
    assert result.outcome is Outcome.BLOCK
    assert result.reason_codes == (PolicyReason.OPERATION_UNREGISTERED,)


def test_preserves_binding_on_block() -> None:
    authorization = replace(_AUTHORIZATION, registered_operations={})
    result = evaluate(_REQUEST, authorization, _NOW)
    assert not result.is_allow
    assert result.binding_id == "binding-1"
    assert result.view_fingerprint == "a" * 64


def test_revoked_authorization_wins_over_later_checks() -> None:
    # 취소이면서 미등록이어도 순서상 취소 사유로 거부한다.
    authorization = replace(_AUTHORIZATION, is_revoked=True, registered_operations={})
    result = evaluate(_REQUEST, authorization, _NOW)
    assert result.reason_codes == (PolicyReason.AUTHORIZATION_REVOKED,)


def test_blocks_expired_configuration() -> None:
    authorization = replace(_AUTHORIZATION, configuration_expires_at=_NOW - timedelta(seconds=1))
    result = evaluate(_REQUEST, authorization, _NOW)
    assert result.reason_codes == (PolicyReason.CONFIGURATION_EXPIRED,)


def test_blocks_at_binding_expiry_instant() -> None:
    request = replace(_REQUEST, binding_expires_at=_NOW)
    result = evaluate(request, _AUTHORIZATION, _NOW)
    assert result.reason_codes == (PolicyReason.BINDING_EXPIRED,)


def test_blocks_operation_source_mismatch() -> None:
    request = replace(_REQUEST, operation_source="orders.v2")
    result = evaluate(request, _AUTHORIZATION, _NOW)
    assert result.reason_codes == (PolicyReason.OPERATION_SOURCE_MISMATCH,)


def test_blocks_origin_mismatch() -> None:
    request = replace(_REQUEST, origin="https://evil.test")
    result = evaluate(request, _AUTHORIZATION, _NOW)
    assert result.reason_codes == (PolicyReason.ORIGIN_MISMATCH,)


def test_blocks_method_mismatch() -> None:
    request = replace(_REQUEST, method="POST")
    result = evaluate(request, _AUTHORIZATION, _NOW)
    assert result.reason_codes == (PolicyReason.METHOD_MISMATCH,)


def test_blocks_out_of_scope_operation() -> None:
    authorization = replace(_AUTHORIZATION, in_scope_operation_refs=frozenset())
    result = evaluate(_REQUEST, authorization, _NOW)
    assert result.reason_codes == (PolicyReason.OUT_OF_SCOPE,)


def test_blocks_purpose_not_in_allowed_purposes() -> None:
    request = replace(_REQUEST, purpose=Purpose.IDENTIFY)
    result = evaluate(request, _AUTHORIZATION, _NOW)
    assert result.reason_codes == (PolicyReason.PURPOSE_NOT_ALLOWED,)


def test_blocks_business_write_under_read_only_profile() -> None:
    authorization = _with_operation(replace(_OPERATION, is_business_write=True))
    result = evaluate(_REQUEST, authorization, _NOW)
    assert result.reason_codes == (PolicyReason.BUSINESS_WRITE_BLOCKED,)


def test_business_write_not_blocked_when_profile_not_read_only() -> None:
    authorization = _with_operation(replace(_OPERATION, is_business_write=True))
    authorization = replace(authorization, read_only_profile=False)
    result = evaluate(_REQUEST, authorization, _NOW)
    assert result.outcome is Outcome.ALLOW


def test_allows_authenticate_purpose_without_verified_identity() -> None:
    authorization = _with_operation(replace(_OPERATION, allowed_purposes=(Purpose.AUTHENTICATE,)))
    request = replace(
        _REQUEST, purpose=Purpose.AUTHENTICATE, identity_status=IdentityStatus.ANONYMOUS
    )
    result = evaluate(request, authorization, _NOW)
    assert result.outcome is Outcome.ALLOW


def test_blocks_observe_without_verified_identity() -> None:
    request = replace(_REQUEST, identity_status=IdentityStatus.UNKNOWN)
    result = evaluate(request, _AUTHORIZATION, _NOW)
    assert result.reason_codes == (PolicyReason.IDENTITY_NOT_VERIFIED,)


def test_blocks_missing_required_cross_confirmation() -> None:
    request = replace(_REQUEST, requires_cross_confirmation=True, has_cross_confirmation=False)
    result = evaluate(request, _AUTHORIZATION, _NOW)
    assert result.reason_codes == (PolicyReason.CROSS_CONFIRMATION_MISSING,)


def test_allows_when_required_cross_confirmation_present() -> None:
    request = replace(_REQUEST, requires_cross_confirmation=True, has_cross_confirmation=True)
    result = evaluate(request, _AUTHORIZATION, _NOW)
    assert result.outcome is Outcome.ALLOW


def test_access_compare_requires_cross_confirmation_regardless_of_flag() -> None:
    request = replace(
        _REQUEST,
        purpose=Purpose.ACCESS_COMPARE,
        requires_cross_confirmation=False,
        has_cross_confirmation=False,
    )
    result = evaluate(request, _AUTHORIZATION, _NOW)
    assert result.reason_codes == (PolicyReason.CROSS_CONFIRMATION_MISSING,)


def test_access_compare_allows_with_cross_confirmation() -> None:
    request = replace(_REQUEST, purpose=Purpose.ACCESS_COMPARE, has_cross_confirmation=True)
    result = evaluate(request, _AUTHORIZATION, _NOW)
    assert result.outcome is Outcome.ALLOW


def test_operation_ref_mismatch_rejected() -> None:
    # 매핑 키는 요청 ref지만 등록 객체의 operation_ref가 다르면 거부한다.
    mismatched = replace(_OPERATION, operation_ref="other-operation")
    authorization = replace(
        _AUTHORIZATION, registered_operations={_REQUEST.operation_ref: mismatched}
    )
    result = evaluate(_REQUEST, authorization, _NOW)
    assert result.reason_codes == (PolicyReason.OPERATION_REF_MISMATCH,)
