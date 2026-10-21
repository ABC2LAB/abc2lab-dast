"""C3 포트의 무전송 소비자 예제다. 서비스 구현·보안 검증을 대체하지 않는다.

가상 등록 view와 가짜 시계로 결과·해제·수명 약속만 재생한다. 실제 Gateway의 전송 snapshot,
등록 검증, Evidence의 독점 소유권·예외 정리·seal/저장·민감값 제거는 후속 모듈 테스트 대상이다.
"""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from abc2lab_contracts.capture import (
    CaptureRequest,
    CaptureResult,
    ExecutedRequestView,
    RawHeader,
    ReleaseCapturesRequest,
)
from abc2lab_contracts.ports import LocalCapturePort
from abc2lab_contracts.primitives import (
    AttemptSummary,
    CloseResult,
    ParameterLocation,
    ReasonCode,
    RequestParameter,
    ResultStatus,
    SendStatus,
)

_CAPTURE_TTL = timedelta(seconds=60)
_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_ACTIVE_CAPTURES = 8


class _CaptureExample:
    """테스트용 메모리 fake로 동기 인계·정리와 가짜 시계만 재생한다."""

    def __init__(self, registered: ExecutedRequestView, now: datetime) -> None:
        self.registered = registered
        self.now = now
        self.active: dict[str, tuple[datetime, CaptureRequest]] = {}
        self.next_handle = 0

    def _expire(self) -> None:
        for reference, (expires_at, _) in tuple(self.active.items()):
            if self.now >= expires_at:
                del self.active[reference]

    def capture(self, request: CaptureRequest) -> CaptureResult:
        self._expire()
        view = request.executed_request
        context = (
            request.run_key,
            request.request_ref,
            request.attempt_ref,
            request.operation_ref,
            request.resource_ref,
            request.account_ref,
            request.session_generation,
        )
        executed_context = (
            view.run_key,
            view.request_ref,
            view.attempt_ref,
            view.operation_ref,
            view.resource_ref,
            view.account_ref,
            view.session_generation,
        )
        expected = replace(
            self.registered, request_ref=view.request_ref, attempt_ref=view.attempt_ref
        )
        reason: ReasonCode | None = None
        if context != executed_context or view != expected:
            reason = ReasonCode.CAPTURE_BINDING_MISMATCH
        elif _response_size_bytes(request) > _MAX_RESPONSE_BYTES:
            reason = ReasonCode.RESPONSE_LIMIT_EXCEEDED
        elif len(self.active) >= _MAX_ACTIVE_CAPTURES:
            reason = ReasonCode.CAPTURE_UNAVAILABLE
        if reason is not None:
            return CaptureResult(request.run_key, ResultStatus.FAILED, None, (reason,))
        self.next_handle += 1
        reference = f"capture-example-{self.next_handle}"
        self.active[reference] = (self.now + _CAPTURE_TTL, request)
        return CaptureResult(request.run_key, ResultStatus.COMPLETE, reference, ())

    def release_captures(self, request: ReleaseCapturesRequest) -> CloseResult:
        self._expire()
        if request.run_key != self.registered.run_key:
            return CloseResult(request.run_key, ResultStatus.FAILED, (ReasonCode.SCOPE_MISMATCH,))
        references = request.capture_refs or tuple(self.active)
        for reference in references:
            self.active.pop(reference, None)
        return CloseResult(request.run_key, ResultStatus.COMPLETE, ())


def _response_size_bytes(request: CaptureRequest) -> int:
    """캡처 payload의 본문과 헤더 UTF-8 bytes 합계를 계산한다."""
    response = request.raw_response
    return len(response.body) + sum(
        len(header.name.encode("utf-8")) + len(header.value.encode("utf-8"))
        for header in response.headers
    )


async def _summarize_sent_response(
    port: LocalCapturePort, request: CaptureRequest, resume: asyncio.Event
) -> AttemptSummary:
    """이미 전송된 가상 응답을 인계하고 취소·실패에도 그 작업의 핸들만 정리한다."""
    run_key, request_ref, attempt_ref = request.run_key, request.request_ref, request.attempt_ref
    result = port.capture(request)
    del request
    try:
        if result.capture_ref is not None:
            await resume.wait()
        return AttemptSummary(
            run_key, request_ref, attempt_ref, SendStatus.SENT, (), result.reason_codes
        )
    finally:
        if result.capture_ref is not None:
            port.release_captures(ReleaseCapturesRequest(run_key, (result.capture_ref,)))


@pytest.mark.asyncio
async def test_capture_success_is_consumed_then_released(capture_request: CaptureRequest) -> None:
    example = _CaptureExample(capture_request.executed_request, capture_request.observed_at)
    port: LocalCapturePort = example
    resume = asyncio.Event()
    resume.set()
    result = await _summarize_sent_response(port, capture_request, resume)
    assert result.send_status is SendStatus.SENT
    assert not example.active
    assert example.next_handle == 1


@pytest.mark.asyncio
async def test_cancelled_consumer_releases_only_its_capture(
    capture_request: CaptureRequest,
) -> None:
    example = _CaptureExample(capture_request.executed_request, capture_request.observed_at)
    existing = example.capture(capture_request)
    assert existing.capture_ref is not None
    task = asyncio.create_task(_summarize_sent_response(example, capture_request, asyncio.Event()))
    await asyncio.sleep(0)
    assert len(example.active) == 2
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert tuple(example.active) == (existing.capture_ref,)


_CONTEXT_CHANGES: tuple[Callable[[CaptureRequest], CaptureRequest], ...] = (
    lambda request: replace(request, run_key=replace(request.run_key, run_ref="other-run")),
    lambda request: replace(request, request_ref="other-request"),
    lambda request: replace(request, attempt_ref="other-attempt"),
    lambda request: replace(request, operation_ref="other-operation"),
    lambda request: replace(request, resource_ref="other-resource"),
    lambda request: replace(request, account_ref="other-account"),
    lambda request: replace(request, session_generation=4),
)


@pytest.mark.parametrize("change", _CONTEXT_CHANGES)
def test_context_mismatch_is_failed_not_a_constructor_exception(
    capture_request: CaptureRequest, change: Callable[[CaptureRequest], CaptureRequest]
) -> None:
    request = change(capture_request)
    example = _CaptureExample(capture_request.executed_request, capture_request.observed_at)
    result = example.capture(request)
    assert result.status is ResultStatus.FAILED
    assert result.capture_ref is None
    assert result.reason_codes == (ReasonCode.CAPTURE_BINDING_MISMATCH,)
    assert not example.active


_VIEW_CHANGES: tuple[Callable[[ExecutedRequestView], ExecutedRequestView], ...] = (
    lambda view: replace(view, operation_revision=2),
    lambda view: replace(view, resource_binding_ref="other-binding"),
    lambda view: replace(view, resource_binding_revision=2),
    lambda view: replace(view, actual_origin="https://other.invalid"),
    lambda view: replace(view, actual_path="/objects/another"),
    lambda view: replace(view, session_generation=4),
    lambda view: replace(
        view, actual_parameters=(RequestParameter("object_id", ParameterLocation.QUERY, "other"),)
    ),
)


@pytest.mark.parametrize("change", _VIEW_CHANGES)
def test_registration_mismatch_never_yields_capture_handle(
    capture_request: CaptureRequest, change: Callable[[ExecutedRequestView], ExecutedRequestView]
) -> None:
    request = replace(capture_request, executed_request=change(capture_request.executed_request))
    example = _CaptureExample(capture_request.executed_request, capture_request.observed_at)
    result = example.capture(request)
    assert result.status is ResultStatus.FAILED
    assert result.capture_ref is None
    assert result.reason_codes == (ReasonCode.CAPTURE_BINDING_MISMATCH,)
    assert not example.active


@pytest.mark.asyncio
async def test_oversize_capture_keeps_sent_and_other_active_handles(
    capture_request: CaptureRequest,
) -> None:
    example = _CaptureExample(capture_request.executed_request, capture_request.observed_at)
    existing = example.capture(capture_request)
    oversized = replace(
        capture_request,
        raw_response=replace(capture_request.raw_response, body=b"x" * (_MAX_RESPONSE_BYTES + 1)),
    )
    result = await _summarize_sent_response(example, oversized, asyncio.Event())
    assert result.send_status is SendStatus.SENT
    assert result.reason_codes == (ReasonCode.RESPONSE_LIMIT_EXCEEDED,)
    assert tuple(example.active) == (existing.capture_ref,)


def test_fake_enforces_capacity_and_expires_at_ttl(capture_request: CaptureRequest) -> None:
    example = _CaptureExample(capture_request.executed_request, capture_request.observed_at)
    for _ in range(_MAX_ACTIVE_CAPTURES):
        assert example.capture(capture_request).status is ResultStatus.COMPLETE
    assert example.capture(capture_request).status is ResultStatus.FAILED
    example.now += _CAPTURE_TTL
    result = example.capture(capture_request)
    assert result.status is ResultStatus.COMPLETE
    assert len(example.active) == 1
    assert result.capture_ref == "capture-example-9"


@pytest.mark.parametrize("extra_byte", [0, 1])
def test_capture_size_includes_header_utf8_bytes_at_exact_limit(
    capture_request: CaptureRequest, extra_byte: int
) -> None:
    header = RawHeader("X-태그", "비밀")
    header_size = 2 * (len(header.name.encode("utf-8")) + len(header.value.encode("utf-8")))
    response = replace(
        capture_request.raw_response,
        headers=(header, header),
        body=b"x" * (_MAX_RESPONSE_BYTES - header_size + extra_byte),
    )
    example = _CaptureExample(capture_request.executed_request, capture_request.observed_at)
    result = example.capture(replace(capture_request, raw_response=response))
    if extra_byte:
        assert result.status is ResultStatus.FAILED
        assert result.capture_ref is None
        assert result.reason_codes == (ReasonCode.RESPONSE_LIMIT_EXCEEDED,)
        assert not example.active
    else:
        assert result.status is ResultStatus.COMPLETE
        assert result.capture_ref is not None


def test_header_only_response_cannot_exceed_capture_limit(capture_request: CaptureRequest) -> None:
    response = replace(
        capture_request.raw_response,
        headers=(RawHeader("X", "x" * _MAX_RESPONSE_BYTES),),
        body=b"",
    )
    example = _CaptureExample(capture_request.executed_request, capture_request.observed_at)
    result = example.capture(replace(capture_request, raw_response=response))
    assert result.status is ResultStatus.FAILED
    assert result.reason_codes == (ReasonCode.RESPONSE_LIMIT_EXCEEDED,)
    assert not example.active


def test_release_is_idempotent_and_cannot_clear_another_run(
    capture_request: CaptureRequest,
) -> None:
    example = _CaptureExample(capture_request.executed_request, capture_request.observed_at)
    result = example.capture(capture_request)
    assert result.capture_ref is not None
    foreign_run = replace(capture_request.run_key, run_ref="other-run")
    assert (
        example.release_captures(ReleaseCapturesRequest(foreign_run, ())).status
        is ResultStatus.FAILED
    )
    assert tuple(example.active) == (result.capture_ref,)
    release = ReleaseCapturesRequest(capture_request.run_key, (result.capture_ref,))
    assert example.release_captures(release).status is ResultStatus.COMPLETE
    assert example.release_captures(release).status is ResultStatus.COMPLETE
    assert not example.active
    example.capture(capture_request)
    assert (
        example.release_captures(ReleaseCapturesRequest(capture_request.run_key, ())).status
        is ResultStatus.COMPLETE
    )
    assert not example.active
