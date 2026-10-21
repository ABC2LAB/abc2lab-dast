"""C3 실행 전용 record의 구조·결과·비노출 보조 장치를 검증한다."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from inspect import iscoroutinefunction
from typing import cast

import pytest
from abc2lab_contracts.capture import (
    CaptureRequest,
    CaptureResult,
    ExecutedRequestView,
    RawHeader,
    RawResponse,
    ReleaseCapturesRequest,
)
from abc2lab_contracts.fingerprint import (
    CanonicalValue,
    _registered_record_fingerprint,
    canonical_json_bytes,
)
from abc2lab_contracts.ports import LocalCapturePort
from abc2lab_contracts.primitives import (
    ParameterLocation,
    Purpose,
    ReasonCode,
    RequestParameter,
    ResultStatus,
    RunKey,
)


def test_capture_and_release_are_synchronous_ports() -> None:
    assert not iscoroutinefunction(LocalCapturePort.capture)
    assert not iscoroutinefunction(LocalCapturePort.release_captures)


def test_capture_values_are_frozen_and_do_not_print_private_data(
    capture_request: CaptureRequest,
) -> None:
    request = replace(
        capture_request,
        executed_request=replace(capture_request.executed_request, actual_path="/secret-canary"),
    )
    records = (
        request.raw_response.headers[0],
        request.raw_response,
        request.executed_request,
        request,
        CaptureResult(request.run_key, ResultStatus.COMPLETE, "secret-canary", ()),
        ReleaseCapturesRequest(request.run_key, ("secret-canary",)),
    )
    for record in records:
        assert "secret-canary" not in repr(record)
        assert not hasattr(record, "__dict__")
    with pytest.raises(AttributeError):
        request.raw_response.body = b"changed"  # type: ignore[misc]
    assert request.raw_response.body == b"secret-canary"


@pytest.mark.parametrize("body", [bytearray(b"secret"), memoryview(b"secret"), "secret"])
def test_raw_response_requires_immutable_bytes(body: object) -> None:
    with pytest.raises(TypeError, match="immutable bytes"):
        RawResponse(200, (), cast(bytes, body))


def test_raw_headers_require_closed_immutable_records() -> None:
    with pytest.raises(TypeError, match="tuple"):
        RawResponse(200, cast(tuple[RawHeader, ...], []), b"")
    with pytest.raises(TypeError, match="contract record"):
        RawResponse(200, (cast(RawHeader, {"name": "Set-Cookie", "value": "secret"}),), b"")
    with pytest.raises(TypeError, match="int"):
        RawResponse(True, (), b"")


def test_capture_normalizes_observation_time_and_rejects_naive_time(
    capture_request: CaptureRequest,
) -> None:
    local = datetime(2026, 10, 21, 9, tzinfo=timezone(timedelta(hours=9)))
    result = replace(capture_request, observed_at=local)
    assert result.observed_at == datetime(2026, 10, 21, tzinfo=UTC)
    assert result.observed_at.tzinfo is UTC
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(capture_request, observed_at=datetime(2026, 10, 21))


def test_executed_view_reuses_registered_path_query_parameters(
    executed_request: ExecutedRequestView,
) -> None:
    parameter = RequestParameter("object_id", ParameterLocation.PATH, "7")
    assert replace(executed_request, actual_parameters=(parameter,)).actual_parameters == (
        parameter,
    )
    with pytest.raises(ValueError, match="path/query"):
        replace(
            executed_request,
            actual_parameters=(RequestParameter("password", ParameterLocation.FORM, "secret"),),
        )


@pytest.mark.parametrize("purpose", [Purpose.AUTHENTICATE, Purpose.IDENTIFY])
def test_authentication_and_identity_views_omit_actual_parameters(
    executed_request: ExecutedRequestView, purpose: Purpose
) -> None:
    assert replace(executed_request, purpose=purpose).actual_parameters == ()
    with pytest.raises(ValueError, match="omit actual parameters"):
        replace(
            executed_request,
            purpose=purpose,
            actual_parameters=(RequestParameter("token", ParameterLocation.QUERY, "secret"),),
        )


def test_post_authentication_can_still_supply_response_evidence(
    capture_request: CaptureRequest,
) -> None:
    view = replace(capture_request.executed_request, method="POST", purpose=Purpose.AUTHENTICATE)
    assert replace(capture_request, executed_request=view).executed_request.actual_parameters == ()


def test_capture_request_requires_nonempty_refs_and_positive_generations(
    capture_request: CaptureRequest,
) -> None:
    with pytest.raises(ValueError, match="non-empty reference"):
        replace(capture_request, attempt_ref="")
    with pytest.raises(ValueError, match="positive"):
        replace(capture_request, session_generation=0)
    with pytest.raises(ValueError, match="positive"):
        replace(capture_request.executed_request, session_generation=0)


@pytest.mark.parametrize(
    ("status", "capture_ref", "reasons"),
    [
        (ResultStatus.COMPLETE, None, ()),
        (ResultStatus.FAILED, "capture-demo", (ReasonCode.CAPTURE_UNAVAILABLE,)),
        (ResultStatus.FAILED, None, ()),
        (ResultStatus.PARTIAL, "capture-demo", (ReasonCode.CAPTURE_UNAVAILABLE,)),
    ],
)
def test_capture_result_requires_complete_handle_or_failed_reason(
    run_key: RunKey,
    status: ResultStatus,
    capture_ref: str | None,
    reasons: tuple[ReasonCode, ...],
) -> None:
    with pytest.raises(ValueError):
        CaptureResult(run_key, status, capture_ref, reasons)


def test_release_request_retains_explicit_scope(run_key: RunKey) -> None:
    assert ReleaseCapturesRequest(run_key, ()).capture_refs == ()
    assert ReleaseCapturesRequest(run_key, ("capture-a",)).capture_refs == ("capture-a",)
    with pytest.raises(ValueError, match="reference"):
        ReleaseCapturesRequest(run_key, ("",))


def test_private_capture_values_cannot_enter_fingerprint_paths(
    capture_request: CaptureRequest,
) -> None:
    private_values = (
        capture_request.raw_response.body,
        capture_request.raw_response.headers[0],
        capture_request.raw_response,
        capture_request.executed_request,
        capture_request,
        CaptureResult(capture_request.run_key, ResultStatus.COMPLETE, "capture-demo", ()),
        ReleaseCapturesRequest(capture_request.run_key, ("capture-demo",)),
    )
    for value in private_values:
        with pytest.raises(TypeError, match="unsupported"):
            canonical_json_bytes(cast(CanonicalValue, value))
        with pytest.raises(ValueError, match="unregistered"):
            _registered_record_fingerprint(value)
