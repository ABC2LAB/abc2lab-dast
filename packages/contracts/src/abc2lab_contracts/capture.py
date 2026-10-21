"""C3 실행 메모리 전용 캡처 계약이다.

원문·실제 경로·파라미터·캡처 핸들은 Gateway/로컬 Evidence 경계 안에서만 사용한다.
JSON·MCP·로그·fingerprint·공개 저장에 전달하지 않는다. repr도 이 값을 출력하지 않는다.
이는 접근 통제나 메모리 소거를 구현하지 않으며, 소유권·수명은 포트 구현이 관리한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from abc2lab_contracts._validation import ContractRecord, require_positive
from abc2lab_contracts.primitives import (
    ParameterLocation,
    Purpose,
    ReasonCode,
    Ref,
    RequestParameter,
    ResultStatus,
    Revision,
    RunKey,
    UtcTime,
)


@dataclass(frozen=True, slots=True, repr=False)
class RawHeader(ContractRecord):
    """비밀을 포함할 수 있는 원문 응답 헤더를 실행 메모리에만 둔다."""

    name: str
    value: str


@dataclass(frozen=True, slots=True, repr=False)
class RawResponse(ContractRecord):
    """원문 응답을 불변 메모리 값으로 인계하며 공개 직렬화하지 않는다.

    캡처 크기는 body bytes와 모든 헤더 name/value의 UTF-8 bytes 길이 합계다.
    Python 객체 오버헤드·HTTP framing은 제외하며 한도 초과는 capture가 실패로 보고한다.
    """

    status_code: int
    headers: tuple[RawHeader, ...]
    body: bytes


@dataclass(frozen=True, slots=True, repr=False)
class ExecutedRequestView(ContractRecord):
    """실제 전송 snapshot에서 유래한 요청 최소 view를 로컬 비교기에 인계한다."""

    run_key: RunKey
    request_ref: Ref
    attempt_ref: Ref
    operation_ref: Ref
    operation_revision: Revision
    resource_ref: Ref | None
    resource_binding_ref: Ref | None
    resource_binding_revision: Revision | None
    account_ref: Ref | None
    session_generation: int | None
    purpose: Purpose
    method: str
    actual_origin: str
    actual_path: str
    actual_parameters: tuple[RequestParameter, ...]

    def _validate_invariants(self) -> None:
        if self.session_generation is not None:
            require_positive("session_generation", self.session_generation)
        if any(
            parameter.location not in (ParameterLocation.PATH, ParameterLocation.QUERY)
            for parameter in self.actual_parameters
        ):
            raise ValueError("executed request parameters must use path/query locations")
        object_get = self.method == "GET" and self.purpose in (
            Purpose.OBSERVE,
            Purpose.ACCESS_COMPARE,
        )
        if not object_get and self.actual_parameters:
            raise ValueError("non-object requests must omit actual parameters")


@dataclass(frozen=True, slots=True, repr=False)
class CaptureRequest(ContractRecord):
    """원문과 실행 view의 소유권을 동기로 인계하는 실행 전용 입력이다."""

    run_key: RunKey
    attempt_ref: Ref
    request_ref: Ref
    operation_ref: Ref
    resource_ref: Ref | None
    account_ref: Ref | None
    session_generation: int | None
    identity_ref: Ref | None
    observed_at: UtcTime
    executed_request: ExecutedRequestView
    raw_response: RawResponse

    def _validate_invariants(self) -> None:
        if self.session_generation is not None:
            require_positive("session_generation", self.session_generation)
        # 맥락·등록 불일치와 응답 한도는 capture가 failed/None으로 보고한다.
        # 생성자에서 교차 대조하면 이 실패 결과·정리 경로를 호출할 수 없게 된다.


@dataclass(frozen=True, slots=True, repr=False)
class CaptureResult(ContractRecord):
    """인계 완료 핸들 또는 실패 사유를 반환하며 실제 전송 상태는 바꾸지 않는다."""

    run_key: RunKey
    status: ResultStatus
    capture_ref: Ref | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.PARTIAL:
            raise ValueError("capture result does not support partial")
        if (self.status is ResultStatus.COMPLETE) != (self.capture_ref is not None):
            raise ValueError("capture result status/output mismatch")
        if self.status is ResultStatus.FAILED and not self.reason_codes:
            raise ValueError("failed capture requires a reason")


@dataclass(frozen=True, slots=True, repr=False)
class ReleaseCapturesRequest(ContractRecord):
    """지정 run의 핸들을 해제하며 빈 tuple은 run 종료 시 전체 active를 뜻한다."""

    run_key: RunKey
    capture_refs: tuple[Ref, ...]
