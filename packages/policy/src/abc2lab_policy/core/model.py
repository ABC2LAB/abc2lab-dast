"""Policy 결정의 내부 도메인 모델.

공개 계약(`PolicyInput`/`PolicyDecision`)으로 변환되기 전의 모듈 내부 타입이다. 공개 계약을
대신하거나 그 사본으로 쓰지 않으며, 공개 포트·fingerprint 입력으로 노출하지 않는다. C2는
병합됐으며(PR #20), `adapters`가 `PolicyInput` → 이 모델, 이 모델의 판정 → `PolicyDecision`으로
변환하는 책임을 진다. C2엔 읽기전용 불리언이 없고 목적 allowlist로 표현하므로, adapter에서 쓰기
차단을 `PURPOSE_NOT_ALLOWED`로 흡수하도록 정렬한다.

시각은 timezone-aware UTC를 가정한다. 가변 예산·permit·실제 전송 상태는 포함하지 않으며, 그
소비·차감은 전송 직전 Gateway가 담당한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Outcome(StrEnum):
    """정책 판정 결과. 공개 계약 outcome의 allow/block과 같은 값을 쓴다."""

    ALLOW = "allow"
    BLOCK = "block"


class Purpose(StrEnum):
    """요청 목적. 등록 동작의 허용 목적과 대조한다."""

    OBSERVE = "observe"
    ACCESS_COMPARE = "access_compare"
    AUTHENTICATE = "authenticate"
    IDENTIFY = "identify"


class IdentityStatus(StrEnum):
    """전송 직전 신원 축약 상태."""

    VERIFIED = "verified"
    UNKNOWN = "unknown"
    ANONYMOUS = "anonymous"


class PolicyReason(StrEnum):
    """판정 사유 코드. C2 병합 시 contracts `ReasonCode`로 매핑한다."""

    ALLOWED = "allowed"
    AUTHORIZATION_REVOKED = "authorization_revoked"
    CONFIGURATION_EXPIRED = "configuration_expired"
    BINDING_EXPIRED = "binding_expired"
    OPERATION_UNREGISTERED = "operation_unregistered"
    OPERATION_REF_MISMATCH = "operation_ref_mismatch"
    OPERATION_SOURCE_MISMATCH = "operation_source_mismatch"
    ORIGIN_MISMATCH = "origin_mismatch"
    METHOD_MISMATCH = "method_mismatch"
    OUT_OF_SCOPE = "out_of_scope"
    PURPOSE_NOT_ALLOWED = "purpose_not_allowed"
    BUSINESS_WRITE_BLOCKED = "business_write_blocked"
    IDENTITY_NOT_VERIFIED = "identity_not_verified"
    CROSS_CONFIRMATION_MISSING = "cross_confirmation_missing"


@dataclass(frozen=True, slots=True)
class RegisteredOperation:
    """등록 동작의 정책 판정용 축약. app이 주입한 등록에서 파생한다."""

    operation_ref: str
    source: str
    origin: str
    method: str
    allowed_purposes: tuple[Purpose, ...]
    is_business_write: bool


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    """app이 주입한 등록·범위·프로필의 내부 판정 뷰."""

    registered_operations: Mapping[str, RegisteredOperation]
    in_scope_operation_refs: frozenset[str]
    read_only_profile: bool
    is_revoked: bool
    configuration_expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    """한 요청을 판정하기 위한 입력 사실.

    `binding_id`와 `view_fingerprint`는 판정에 그대로 보존하며 값 자체를 해석하지 않는다.
    """

    run_key: str
    request_ref: str
    binding_id: str
    view_fingerprint: str
    origin: str
    method: str
    operation_ref: str
    operation_source: str
    purpose: Purpose
    identity_status: IdentityStatus
    binding_expires_at: datetime
    requires_cross_confirmation: bool = False
    has_cross_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    """내부 판정 결과. 입력 binding을 보존한다. 감사·발급은 adapter가 담당한다."""

    outcome: Outcome
    reason_codes: tuple[PolicyReason, ...]
    run_key: str
    request_ref: str
    binding_id: str
    view_fingerprint: str

    @property
    def is_allow(self) -> bool:
        """허용 판정이면 True."""
        return self.outcome is Outcome.ALLOW
