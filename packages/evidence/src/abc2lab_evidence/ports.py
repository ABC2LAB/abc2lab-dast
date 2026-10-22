"""evidence 내부 주입 Protocol.

공개 포트(`LocalCapturePort`·`ExecutionEvidencePort`·`EvidencePort`)와 공유 레코드는
`abc2lab_contracts`가 소유한다. 여기서는 app이 주입하는 evidence 로컬 조회만 둔다.
"""

from __future__ import annotations

from typing import Protocol

from abc2lab_contracts.primitives import Ref
from abc2lab_contracts.registration import OperationRegistration, ResourceBinding


class CaptureRegistry(Protocol):
    """app이 주입하는 등록 조회 뷰. capture 바인딩 검증에만 쓰는 읽기 전용이다."""

    def operation(self, operation_ref: Ref) -> OperationRegistration | None:
        """등록된 동작을 반환하고 없으면 None을 반환한다."""
        ...

    def resource_binding(self, resource_binding_ref: Ref) -> ResourceBinding | None:
        """등록된 자원 바인딩을 반환하고 없으면 None을 반환한다."""
        ...
