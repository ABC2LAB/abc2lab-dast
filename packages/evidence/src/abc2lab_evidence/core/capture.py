"""실행영역 로컬 캡처 버퍼의 수명·바인딩·동기 소유권 인계를 관리한다.

외부 I/O·네트워크·DB·저장·장시간 계산을 하지 않는다. 원문 응답은 이 저장소의
메모리에만 보관하고 참조·핸들로만 다룬다. capture 결과에는 불투명 참조·상태·사유만
담고 원문·헤더·본문을 반환하지 않는다. `acquire`는 같은 실행영역의 seal/compare만
호출하는 내부 읽기이며 공개 포트·Host·로그로는 원문이 나가지 않는다(s1-api-spec §7,
c3-c4-contract-draft §2).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from abc2lab_contracts.capture import (
    CaptureRequest,
    CaptureResult,
    ExecutedRequestView,
    RawResponse,
    ReleaseCapturesRequest,
)
from abc2lab_contracts.primitives import (
    CloseResult,
    ReasonCode,
    Ref,
    RequestParameter,
    ResultStatus,
    RunKey,
)
from abc2lab_contracts.registration import OperationRegistration

from abc2lab_evidence.ports import CaptureRegistry

# §11의 구성 가능한 초기값. 운영 보장이 아니라 테스트·첫 구현용 기본값이다.
DEFAULT_CAPTURE_TTL_S = 60.0
DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024
DEFAULT_MAX_ACTIVE_CAPTURES = 8


@dataclass(slots=True)
class _CaptureEntry:
    """활성 캡처 하나의 생성 시각과 원문·맥락 요청을 보유하는 내부 상태다."""

    created_monotonic: float
    request: CaptureRequest


def _parameter_key(parameter: RequestParameter) -> tuple[str, str, str]:
    """등록 비교용으로 매개변수를 순서 무관 정렬 키로 변환한다."""
    return (parameter.name, parameter.location.value, parameter.value)


def _capture_size(raw: RawResponse) -> int:
    """계약 정의대로 body와 모든 헤더 name/value의 UTF-8 bytes 합계를 센다."""
    size = len(raw.body)
    for header in raw.headers:
        size += len(header.name.encode("utf-8")) + len(header.value.encode("utf-8"))
    return size


class LocalCaptureStore:
    """Gateway가 인계한 원문을 실행영역 메모리에만 보관하는 동기 캡처 저장소다."""

    def __init__(
        self,
        registry: CaptureRegistry,
        new_capture_ref: Callable[[], Ref],
        monotonic: Callable[[], float],
        *,
        ttl_s: float = DEFAULT_CAPTURE_TTL_S,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_active_captures: int = DEFAULT_MAX_ACTIVE_CAPTURES,
    ) -> None:
        """등록 조회·참조 발급·단조 시계와 유한 한도를 주입받는다."""
        self._registry = registry
        self._new_capture_ref = new_capture_ref
        self._monotonic = monotonic
        self._ttl_s = ttl_s
        self._max_response_bytes = max_response_bytes
        self._max_active_captures = max_active_captures
        self._entries: dict[str, _CaptureEntry] = {}

    def capture(self, request: CaptureRequest) -> CaptureResult:
        """원문 소유권을 인계받거나 바인딩·한도 실패를 보존해 반환한다."""
        self._expire_due()
        mismatch = self._binding_reason(request)
        if mismatch is not None:
            return self._failed(request.run_key, mismatch)
        if _capture_size(request.raw_response) > self._max_response_bytes:
            return self._failed(request.run_key, ReasonCode.RESPONSE_LIMIT_EXCEEDED)
        if self._active_count(request.run_key) >= self._max_active_captures:
            return self._failed(request.run_key, ReasonCode.CAPTURE_UNAVAILABLE)
        capture_ref = self._new_capture_ref()
        # 원문·맥락은 이 저장소 메모리에만 보관한다. 참조·수명으로만 다룬다.
        self._entries[capture_ref] = _CaptureEntry(self._monotonic(), request)
        return CaptureResult(request.run_key, ResultStatus.COMPLETE, capture_ref, ())

    def acquire(self, run_key: RunKey, capture_ref: Ref) -> CaptureRequest | None:
        """같은 실행영역의 seal/compare가 활성 캡처의 원문·맥락을 읽는 내부 포트다.

        만료·부재·run 불일치는 None이다. 반환값은 실행영역 밖으로 내보내지 않는다.
        """
        self._expire_due()
        entry = self._entries.get(capture_ref)
        if entry is None or entry.request.run_key != run_key:
            return None
        return entry.request

    def release_captures(self, request: ReleaseCapturesRequest) -> CloseResult:
        """지정 또는 run 전체 캡처를 멱등으로 해제하고 버퍼 참조를 제거한다."""
        self._expire_due()
        if request.capture_refs:
            targets = [ref for ref in request.capture_refs if self._owned_by(ref, request.run_key)]
        else:
            targets = [
                ref
                for ref, entry in self._entries.items()
                if entry.request.run_key == request.run_key
            ]
        for ref in targets:
            self._entries.pop(ref, None)
        return CloseResult(request.run_key, ResultStatus.COMPLETE, ())

    def active_refs(self, run_key: RunKey) -> tuple[Ref, ...]:
        """현재 활성 캡처 참조만 반환하는 진단용 읽기. 원문은 노출하지 않는다."""
        self._expire_due()
        return tuple(
            ref for ref, entry in self._entries.items() if entry.request.run_key == run_key
        )

    def _binding_reason(self, request: CaptureRequest) -> ReasonCode | None:
        """실행 view의 자기 일관성과 등록 일치를 검사한다."""
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
        declared = (
            view.run_key,
            view.request_ref,
            view.attempt_ref,
            view.operation_ref,
            view.resource_ref,
            view.account_ref,
            view.session_generation,
        )
        if context != declared:
            return ReasonCode.CAPTURE_BINDING_MISMATCH
        operation = self._registry.operation(view.operation_ref)
        if operation is None:
            return ReasonCode.CAPTURE_BINDING_MISMATCH
        if (
            view.method != operation.method
            or view.actual_origin != operation.origin
            or view.purpose not in operation.allowed_purposes
        ):
            return ReasonCode.CAPTURE_BINDING_MISMATCH
        resource_binding_ref = view.resource_binding_ref
        if resource_binding_ref is not None:
            return self._resource_binding_reason(view, operation, resource_binding_ref)
        return None

    def _resource_binding_reason(
        self,
        view: ExecutedRequestView,
        operation: OperationRegistration,
        resource_binding_ref: Ref,
    ) -> ReasonCode | None:
        """자원 바인딩 참조·소유 동작·매개변수가 등록과 일치하는지 검사한다."""
        binding = self._registry.resource_binding(resource_binding_ref)
        if binding is None or view.resource_ref != binding.resource_ref:
            return ReasonCode.CAPTURE_BINDING_MISMATCH
        registered_refs = {item.resource_binding_ref for item in operation.resource_bindings}
        if binding.resource_binding_ref not in registered_refs:
            return ReasonCode.CAPTURE_BINDING_MISMATCH
        actual = sorted(_parameter_key(item) for item in view.actual_parameters)
        registered = sorted(_parameter_key(item) for item in binding.parameters)
        if actual != registered:
            return ReasonCode.CAPTURE_BINDING_MISMATCH
        return None

    def _failed(self, run_key: RunKey, reason: ReasonCode) -> CaptureResult:
        """원문을 보관하지 않고 실패 사유만 담은 결과를 만든다."""
        return CaptureResult(run_key, ResultStatus.FAILED, None, (reason,))

    def _active_count(self, run_key: RunKey) -> int:
        return sum(1 for entry in self._entries.values() if entry.request.run_key == run_key)

    def _owned_by(self, capture_ref: Ref, run_key: RunKey) -> bool:
        entry = self._entries.get(capture_ref)
        return entry is not None and entry.request.run_key == run_key

    def _expire_due(self) -> None:
        """TTL이 지난 캡처를 만료 처리하고 버퍼 참조를 제거한다."""
        now = self._monotonic()
        expired = [
            ref
            for ref, entry in self._entries.items()
            if now - entry.created_monotonic > self._ttl_s
        ]
        for ref in expired:
            self._entries.pop(ref, None)
