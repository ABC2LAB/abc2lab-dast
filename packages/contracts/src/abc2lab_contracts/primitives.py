"""Shared scalar values and closed enums for the C2 contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from abc2lab_contracts._validation import ContractRecord

Ref = Annotated[str, "opaque non-empty reference"]
Revision = Annotated[int, "positive revision"]
UtcTime = Annotated[datetime, "timezone-aware UTC datetime"]


class ResultStatus(StrEnum):
    """호출 결과의 완성도를 표현한다."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class SendStatus(StrEnum):
    """실제 대상 요청의 전송 확인 상태다."""

    SENT = "sent"
    NOT_SENT = "not_sent"
    UNKNOWN = "unknown"


class CaptureStatus(StrEnum):
    """전송 상태와 별개인 캡처 확보 결과다."""

    CAPTURED = "captured"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"
    INDETERMINATE = "indeterminate"


class CheckState(StrEnum):
    """확인하지 못한 조건을 unknown으로 보존한다."""

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class ResponseClass(StrEnum):
    """등록 규칙으로 분류한 응답 종류다."""

    NORMAL = "normal"
    LOGIN = "login"
    ERROR = "error"
    UNKNOWN = "unknown"


class Purpose(StrEnum):
    """등록 동작에 허용된 요청 목적이다."""

    OBSERVE = "observe"
    AUTHENTICATE = "authenticate"
    IDENTIFY = "identify"
    ACCESS_COMPARE = "access_compare"


class ParameterLocation(StrEnum):
    """Location where a registered request parameter is inserted."""

    PATH = "path"
    QUERY = "query"
    FORM = "form"


class ReasonCode(StrEnum):
    """S1 명세에 등록된 비밀 없는 감사 상태·실패·부분 결과 사유다."""

    CONFIGURATION_MISSING = "configuration_missing"
    NOT_FOUND = "not_found"
    ACCESS_DENIED = "access_denied"
    REVISION_CONFLICT = "revision_conflict"
    REVISION_UNAVAILABLE = "revision_unavailable"
    RESULT_LIMIT_EXCEEDED = "result_limit_exceeded"
    SNAPSHOT_EXPIRED = "snapshot_expired"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    UNSUPPORTED_AUTHENTICATION = "unsupported_authentication"
    QUEUE_FULL = "queue_full"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    POLICY_BLOCKED = "policy_blocked"
    POLICY_VIEW_MISMATCH = "policy_view_mismatch"
    PREPARED_HANDLE_INVALID = "prepared_handle_invalid"
    PREPARED_HANDLE_EXPIRED = "prepared_handle_expired"
    PREPARED_HANDLE_FOREIGN_SCOPE = "prepared_handle_foreign_scope"
    PREPARED_HANDLE_CONSUMED = "prepared_handle_consumed"
    SCOPE_MISMATCH = "scope_mismatch"
    EXPECTED_ACCESS_POLICY_MISSING = "expected_access_policy_missing"
    EXPECTED_ACCESS_POLICY_INVALID = "expected_access_policy_invalid"
    CROSS_CONFIRMATION_MISSING = "cross_confirmation_missing"
    SHARING_OR_DELEGATION_UNKNOWN = "sharing_or_delegation_unknown"
    IDENTITY_UNKNOWN = "identity_unknown"
    IDENTITY_MISMATCH = "identity_mismatch"
    SESSION_EXPIRED = "session_expired"
    SESSION_GENERATION_CHANGED = "session_generation_changed"
    SESSION_BUSY = "session_busy"
    RECOVERY_EXHAUSTED = "recovery_exhausted"
    CANCELLED = "cancelled"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    CLEANUP_TIMEOUT = "cleanup_timeout"
    INTERNAL_ERROR = "internal_error"
    SCHEDULER_FAILED = "scheduler_failed"
    TRANSPORT_NOT_ENTERED = "transport_not_entered"
    SEND_ACKNOWLEDGEMENT_LOST = "send_acknowledgement_lost"
    CAPTURE_UNAVAILABLE = "capture_unavailable"
    CAPTURE_EXPIRED = "capture_expired"
    CAPTURE_BINDING_MISMATCH = "capture_binding_mismatch"
    RESPONSE_LIMIT_EXCEEDED = "response_limit_exceeded"
    EVIDENCE_STORE_FAILED = "evidence_store_failed"
    CROSS_EVIDENCE_STORE_FAILED = "cross_evidence_store_failed"
    COMPARISON_INCOMPLETE = "comparison_incomplete"
    COMPARISON_CANARY_PASSED = "comparison_canary_passed"
    COMPARISON_CANARY_FAILED = "comparison_canary_failed"
    COMPARISON_CANARY_UNKNOWN = "comparison_canary_unknown"
    COMPARISON_SAME_RESOURCE_UNKNOWN = "comparison_same_resource_unknown"
    COMPARISON_SUBJECTS_UNKNOWN = "comparison_subjects_unknown"
    COMPARISON_OWNER_DATA_UNKNOWN = "comparison_owner_data_unknown"
    COMPARISON_CROSS_DATA_UNKNOWN = "comparison_cross_data_unknown"
    COMPARISON_DATA_MATCH_UNKNOWN = "comparison_data_match_unknown"
    COMPARISON_REFLECTION_UNKNOWN = "comparison_reflection_unknown"
    COMPARISON_TEMPLATE_UNKNOWN = "comparison_template_unknown"
    SOURCE_UNVERIFIED = "source_unverified"
    AUDIT_COMMIT_FAILED = "audit_commit_failed"
    AUDIT_VERIFICATION_UNKNOWN = "audit_verification_unknown"
    AUDIT_GAP = "audit_gap"
    RECIPE_MISSING = "recipe_missing"
    RECIPE_UNSUPPORTED = "recipe_unsupported"
    RECIPE_NOT_EXPORTABLE = "recipe_not_exportable"
    RECIPE_BINDING_MISMATCH = "recipe_binding_mismatch"
    POC_EVIDENCE_INCOMPLETE = "poc_evidence_incomplete"
    POC_VERDICT_UNCONFIRMED = "poc_verdict_unconfirmed"
    POC_AUDIT_INCOMPLETE = "poc_audit_incomplete"


@dataclass(frozen=True, slots=True)
class RunKey(ContractRecord):
    """Identify one run in an organization, target, and environment."""

    organization_ref: Ref
    target_ref: Ref
    environment_ref: Ref
    run_ref: Ref


@dataclass(frozen=True, slots=True)
class SourceVersion(ContractRecord):
    """Identify the registered source revision used for a snapshot."""

    issuer: Ref
    source_ref: Ref
    revision: Revision


@dataclass(frozen=True, slots=True)
class ReadContext(ContractRecord):
    """Carry the authenticated caller and authorization reference."""

    caller_ref: Ref
    authorization_ref: Ref


@dataclass(frozen=True, slots=True)
class AuditLink(ContractRecord):
    """Link a result to a producer audit event."""

    producer: Ref
    event_ref: Ref


@dataclass(frozen=True, slots=True)
class RequestParameter(ContractRecord):
    """Represent a registered path, query, or form parameter."""

    name: str
    location: ParameterLocation
    value: str


@dataclass(frozen=True, slots=True)
class AttemptSummary(ContractRecord):
    """Summarize an attempt without exposing transport or capture details."""

    run_key: RunKey
    request_ref: Ref
    attempt_ref: Ref
    send_status: SendStatus
    audit_links: tuple[AuditLink, ...]
    reason_codes: tuple[ReasonCode, ...]


@dataclass(frozen=True, slots=True)
class CloseResult(ContractRecord):
    """Report cleanup completion without changing known send state."""

    run_key: RunKey
    status: ResultStatus
    reason_codes: tuple[ReasonCode, ...]
