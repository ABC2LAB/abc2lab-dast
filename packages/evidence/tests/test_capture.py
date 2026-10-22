"""로컬 캡처 저장소의 수명·바인딩·동기 인계를 네트워크·DB 없이 검증한다.

적용 사례: S1-33(바인딩 불일치 거부), S1-04(한도 실패는 원문을 보관하지 않음),
S1-13(결과에 원문·헤더·본문 없음), 캡처 수명(TTL·active 상한)과 멱등 해제.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from abc2lab_contracts.capture import (
    CaptureRequest,
    ExecutedRequestView,
    RawHeader,
    RawResponse,
    ReleaseCapturesRequest,
)
from abc2lab_contracts.primitives import (
    ParameterLocation,
    Purpose,
    ReasonCode,
    Ref,
    RequestParameter,
    ResultStatus,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.registration import OperationRegistration, ResourceBinding
from abc2lab_evidence.core.capture import DEFAULT_MAX_ACTIVE_CAPTURES, LocalCaptureStore

_RUN = RunKey("org-1", "target-1", "env-1", "run-1")
_OTHER_RUN = RunKey("org-1", "target-1", "env-1", "run-2")
_SOURCE = SourceVersion("issuer-1", "registration-1", 1)
_PARAMS = (RequestParameter("id", ParameterLocation.PATH, "42"),)
_BINDING = ResourceBinding(
    resource_binding_ref="binding-1",
    source=_SOURCE,
    resource_ref="resource-1",
    owner_subject_ref="subject-a",
    parameters=_PARAMS,
)
_OPERATION = OperationRegistration(
    source=_SOURCE,
    operation_ref="operation-1",
    allowed_purposes=(Purpose.OBSERVE, Purpose.ACCESS_COMPARE),
    auth_profile_ref=None,
    method="GET",
    origin="https://app.example",
    path_template="/orders/{id}",
    resource_bindings=(_BINDING,),
)


class _FakeRegistry:
    """주입되는 등록 조회 뷰의 로컬 fake. 등록된 하나의 동작·바인딩만 안다."""

    def operation(self, operation_ref: Ref) -> OperationRegistration | None:
        return _OPERATION if operation_ref == _OPERATION.operation_ref else None

    def resource_binding(self, resource_binding_ref: Ref) -> ResourceBinding | None:
        return _BINDING if resource_binding_ref == _BINDING.resource_binding_ref else None


class _Clock:
    """단조 시계 fake. 실제 sleep 없이 경과를 제어한다."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _Refs:
    """결정적 캡처 참조 발급기."""

    def __init__(self) -> None:
        self._count = 0

    def __call__(self) -> Ref:
        self._count += 1
        return f"capture-{self._count}"


def _store(clock: _Clock | None = None) -> LocalCaptureStore:
    return LocalCaptureStore(_FakeRegistry(), _Refs(), clock or _Clock())


def _view(
    *,
    run_key: RunKey = _RUN,
    account_ref: Ref | None = "account-a",
    actual_origin: str = "https://app.example",
    actual_parameters: tuple[RequestParameter, ...] = _PARAMS,
) -> ExecutedRequestView:
    return ExecutedRequestView(
        run_key=run_key,
        request_ref="request-1",
        attempt_ref="attempt-1",
        operation_ref="operation-1",
        operation_revision=1,
        resource_ref="resource-1",
        resource_binding_ref="binding-1",
        resource_binding_revision=1,
        account_ref=account_ref,
        session_generation=1,
        purpose=Purpose.OBSERVE,
        method="GET",
        actual_origin=actual_origin,
        actual_path="/orders/42",
        actual_parameters=actual_parameters,
    )


def _request(
    view: ExecutedRequestView | None = None, body: bytes = b"owner-order-42"
) -> CaptureRequest:
    resolved = view or _view()
    return CaptureRequest(
        run_key=resolved.run_key,
        attempt_ref=resolved.attempt_ref,
        request_ref=resolved.request_ref,
        operation_ref=resolved.operation_ref,
        resource_ref=resolved.resource_ref,
        account_ref=resolved.account_ref,
        session_generation=resolved.session_generation,
        identity_ref="identity-a",
        observed_at=datetime(2026, 10, 21, tzinfo=UTC),
        executed_request=resolved,
        raw_response=RawResponse(200, (RawHeader("content-type", "application/json"),), body),
    )


def test_capture_success_returns_opaque_ref_and_retains_buffer() -> None:
    store = _store()
    result = store.capture(_request())
    assert result.status is ResultStatus.COMPLETE
    assert result.capture_ref == "capture-1"
    assert result.reason_codes == ()
    assert store.active_refs(_RUN) == ("capture-1",)


def test_result_exposes_no_raw_fields() -> None:
    result = _store().capture(_request())
    field_names = {field for field in type(result).__dataclass_fields__}
    assert field_names == {"run_key", "status", "capture_ref", "reason_codes"}


def test_self_binding_mismatch_is_rejected_without_retention() -> None:
    store = _store()
    # 캡처 맥락은 account-a인데 실행 view는 account-b면 자기 일관성 불일치다.
    mismatched = replace(_request(), executed_request=_view(account_ref="account-b"))
    result = store.capture(mismatched)
    assert result.status is ResultStatus.FAILED
    assert result.capture_ref is None
    assert result.reason_codes == (ReasonCode.CAPTURE_BINDING_MISMATCH,)
    assert store.active_refs(_RUN) == ()


def test_registration_origin_mismatch_is_rejected() -> None:
    result = _store().capture(_request(_view(actual_origin="https://evil.example")))
    assert result.reason_codes == (ReasonCode.CAPTURE_BINDING_MISMATCH,)


def test_registration_parameter_mismatch_is_rejected() -> None:
    other = RequestParameter("id", ParameterLocation.PATH, "43")
    result = _store().capture(_request(_view(actual_parameters=(other,))))
    assert result.reason_codes == (ReasonCode.CAPTURE_BINDING_MISMATCH,)


def test_response_over_limit_is_rejected_without_retention() -> None:
    store = LocalCaptureStore(_FakeRegistry(), _Refs(), _Clock(), max_response_bytes=8)
    result = store.capture(_request(body=b"too-large-body"))
    assert result.status is ResultStatus.FAILED
    assert result.reason_codes == (ReasonCode.RESPONSE_LIMIT_EXCEEDED,)
    assert store.active_refs(_RUN) == ()


def test_active_capture_limit_is_enforced() -> None:
    store = _store()
    for _ in range(DEFAULT_MAX_ACTIVE_CAPTURES):
        assert store.capture(_request()).status is ResultStatus.COMPLETE
    overflow = store.capture(_request())
    assert overflow.status is ResultStatus.FAILED
    assert overflow.reason_codes == (ReasonCode.CAPTURE_UNAVAILABLE,)
    assert len(store.active_refs(_RUN)) == DEFAULT_MAX_ACTIVE_CAPTURES


def test_capture_expires_after_ttl() -> None:
    clock = _Clock()
    store = LocalCaptureStore(_FakeRegistry(), _Refs(), clock, ttl_s=60.0)
    store.capture(_request())
    assert store.active_refs(_RUN) == ("capture-1",)
    clock.now += 61.0
    assert store.active_refs(_RUN) == ()


def test_release_specific_ref_is_idempotent() -> None:
    store = _store()
    store.capture(_request())
    first = store.release_captures(ReleaseCapturesRequest(_RUN, ("capture-1",)))
    second = store.release_captures(ReleaseCapturesRequest(_RUN, ("capture-1",)))
    assert first.status is ResultStatus.COMPLETE
    assert second.status is ResultStatus.COMPLETE
    assert store.active_refs(_RUN) == ()


def test_release_all_for_run_leaves_other_runs() -> None:
    store = _store()
    store.capture(_request())
    other_view = _view(run_key=_OTHER_RUN)
    store.capture(_request(other_view))
    result = store.release_captures(ReleaseCapturesRequest(_RUN, ()))
    assert result.status is ResultStatus.COMPLETE
    assert store.active_refs(_RUN) == ()
    assert store.active_refs(_OTHER_RUN) == ("capture-2",)


def test_release_does_not_touch_other_runs_capture_by_ref() -> None:
    store = _store()
    store.capture(_request())
    # run-2가 run-1의 capture-1을 해제 요청해도 소유자가 아니므로 무시한다.
    store.release_captures(ReleaseCapturesRequest(_OTHER_RUN, ("capture-1",)))
    assert store.active_refs(_RUN) == ("capture-1",)
