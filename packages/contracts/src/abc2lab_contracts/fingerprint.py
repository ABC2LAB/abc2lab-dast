"""결정적 정규 JSON 인코딩과 운영 fingerprint 등록 경계를 정의한다."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from types import MappingProxyType
from typing import cast

from abc2lab_contracts._validation import ContractRecord, validate_record
from abc2lab_contracts.audit import (
    AttemptRecord,
    AuditReceipt,
    AuditRecordBinding,
    PolicyOutcome,
    RequestIntentRecord,
)
from abc2lab_contracts.execution import (
    PolicyAttributes,
    PolicyDecision,
    PolicyDecisionContent,
    PolicyIdentityStatus,
    PolicyInput,
)
from abc2lab_contracts.primitives import (
    AttemptSummary,
    AuditLink,
    CaptureStatus,
    Purpose,
    ReasonCode,
    RunKey,
    SendStatus,
    SourceVersion,
)
from abc2lab_contracts.registration import (
    BudgetSnapshot,
    CrossExecutionConfirmation,
    ExecutionProfileSnapshot,
    ExpectedAccess,
    ExpectedAccessPolicySnapshot,
    ResolutionState,
    ScopeSnapshot,
)
from abc2lab_contracts.session import (
    IdentityBindingSummary,
    IdentityContent,
    IdentityResult,
    IdentityStatus,
)

CODEC_VERSION = "canonical-json.v1"
_MIN_INT64 = -(2**63)
_MAX_INT64 = 2**63 - 1


@dataclass(frozen=True, slots=True)
class CanonicalObject:
    """외부 매핑과 참조를 공유하지 않는 불변 JSON object다."""

    entries: tuple[tuple[str, CanonicalValue], ...]

    def __post_init__(self) -> None:
        """필드 중복과 가변 값을 거부하고 중첩 값을 고정한다."""
        if type(self.entries) is not tuple:
            raise TypeError("canonical object entries must be a tuple")
        seen_keys: set[str] = set()
        frozen_entries: list[tuple[str, CanonicalValue]] = []
        for entry in self.entries:
            if type(entry) is not tuple or len(entry) != 2:
                raise TypeError("canonical object entry must be a key-value tuple")
            key, value = entry
            if type(key) is not str:
                raise TypeError("mapping keys must be strings")
            key.encode("utf-8", errors="strict")
            if key in seen_keys:
                raise ValueError("duplicate canonical object key")
            seen_keys.add(key)
            frozen_entries.append((key, _freeze_value(value, set(), allow_mappings=False)))
        object.__setattr__(self, "entries", tuple(sorted(frozen_entries)))


# C1은 이 폐쇄형 자료형만 직렬화한다. 업무 record 변환은 C2 adapter가 맡는다.
type CanonicalValue = (
    str | bool | None | int | datetime | tuple[CanonicalValue, ...] | CanonicalObject
)
type _JsonValue = str | bool | None | int | list[_JsonValue] | dict[str, _JsonValue]


@dataclass(frozen=True, slots=True)
class _RecordRegistration:
    """운영 레코드와 명시적 payload adapter를 결합하는 고정 계약이다."""

    codec_version: str
    record_kind: str
    schema_version: str
    record_type: type[ContractRecord]
    payload_adapter: Callable[[object], CanonicalValue]


# Explicit versioned field sets must not be inferred from today's dataclass definitions.
# This is validation only; each payload below still maps its own fields explicitly.
_RECORD_FIELDS: Mapping[type[ContractRecord], str] = MappingProxyType(
    {
        RunKey: "organization_ref target_ref environment_ref run_ref",
        SourceVersion: "issuer source_ref revision",
        AuditLink: "producer event_ref",
        ScopeSnapshot: "source allowed_origins allowed_operation_refs valid_from valid_until",
        ExecutionProfileSnapshot: (
            "source allowed_methods allowed_purposes allow_redirects valid_until"
        ),
        BudgetSnapshot: "source max_attempts max_duration_ms max_response_bytes",
        PolicyAttributes: (
            "registered_path_matches parameter_names parameters_match_registration resource_ref "
            "resource_binding_ref resource_binding_revision resource_owner_subject_ref provenance"
        ),
        ExpectedAccessPolicySnapshot: (
            "source policy_ref target_ref environment_ref resource_ref operation_ref "
            "owner_subject_ref evaluated_subject_ref expected_access sharing delegation "
            "valid_from valid_until"
        ),
        CrossExecutionConfirmation: (
            "source run_key resource_ref operation_ref owner_account_ref "
            "evaluated_account_ref valid_until"
        ),
        IdentityBindingSummary: (
            "identity_ref session_ref account_ref subject_ref generation verified_at valid_until"
        ),
        AttemptSummary: "run_key request_ref attempt_ref send_status audit_links reason_codes",
        AuditRecordBinding: (
            "event_kind record_ref record_revision record_fingerprint "
            "request_ref attempt_ref binding_id"
        ),
        AuditReceipt: "run_key producer event_ref sequence binding committed_at",
        PolicyInput: (
            "schema_version run_key request_ref binding_id binding_issuer expires_at origin method "
            "operation_ref operation_revision purpose policy_attributes account_ref "
            "session_generation identity_ref subject_ref identity_status owner_identity "
            "scope profile budget expected_policy cross_confirmation"
        ),
        PolicyDecisionContent: (
            "run_key decision_ref binding_id evaluated_view_fingerprint outcome policy_version "
            "issued_at expires_at reason_codes"
        ),
        PolicyDecision: (
            "run_key decision_ref binding_id evaluated_view_fingerprint outcome policy_version "
            "issued_at expires_at audit_receipt reason_codes"
        ),
        IdentityContent: (
            "run_key identity_ref status session_ref account_ref generation "
            "subject_ref evidence_ref verified_at valid_until attempt_summaries reason_codes"
        ),
        IdentityResult: (
            "run_key identity_ref status session_ref account_ref generation "
            "subject_ref evidence_ref verified_at valid_until audit_receipt "
            "attempt_summaries reason_codes"
        ),
        RequestIntentRecord: (
            "run_key request_ref attempt_ref binding_id operation_ref operation_revision purpose "
            "account_ref session_generation decision_ref evaluated_view_fingerprint created_at"
        ),
        AttemptRecord: (
            "run_key request_ref attempt_ref revision decision_ref binding_id operation_ref "
            "account_ref session_generation send_status capture_status occurred_at reason_codes"
        ),
    }
)


def _validate_field_shapes(record: ContractRecord) -> None:
    if not is_dataclass(record):
        raise TypeError("operational record must be a dataclass")
    expected = _RECORD_FIELDS.get(type(record))
    if expected is None or {field.name for field in fields(record)} != set(expected.split()):
        raise TypeError("operational record field shape mismatch")
    for field in fields(record):
        value = getattr(record, field.name)
        if isinstance(value, ContractRecord):
            _validate_field_shapes(value)
        elif isinstance(value, tuple):
            for item in value:
                if isinstance(item, ContractRecord):
                    _validate_field_shapes(item)


def _run_key(value: RunKey) -> dict[str, object]:
    if type(value) is not RunKey:
        raise TypeError("expected RunKey")
    return {
        "organization_ref": value.organization_ref,
        "target_ref": value.target_ref,
        "environment_ref": value.environment_ref,
        "run_ref": value.run_ref,
    }


def _source(value: SourceVersion) -> dict[str, object]:
    if type(value) is not SourceVersion:
        raise TypeError("expected SourceVersion")
    return {"issuer": value.issuer, "source_ref": value.source_ref, "revision": value.revision}


def _enum(value: Enum, expected: type[Enum]) -> str:
    if type(value) is not expected:
        raise TypeError("unexpected enum type")
    if not isinstance(value.value, str):
        raise TypeError("enum value must be a string")
    return value.value


def _policy_input_payload(value: PolicyInput) -> CanonicalValue:
    if type(value) is not PolicyInput:
        raise TypeError("expected PolicyInput")
    attributes = value.policy_attributes
    policy = value.expected_policy
    confirmation = value.cross_confirmation
    owner = value.owner_identity
    scope = value.scope
    profile = value.profile
    budget = value.budget
    return freeze_object(
        {
            "account_ref": value.account_ref,
            "binding_id": value.binding_id,
            "binding_issuer": value.binding_issuer,
            "budget": {
                "max_attempts": budget.max_attempts,
                "max_duration_ms": budget.max_duration_ms,
                "max_response_bytes": budget.max_response_bytes,
                "source": _source(budget.source),
            },
            "cross_confirmation": (
                None if confirmation is None else _cross_confirmation(confirmation)
            ),
            "expected_policy": None if policy is None else _expected_policy(policy),
            "expires_at": value.expires_at,
            "identity_ref": value.identity_ref,
            "identity_status": _enum(value.identity_status, PolicyIdentityStatus),
            "method": value.method,
            "operation_ref": value.operation_ref,
            "operation_revision": value.operation_revision,
            "origin": value.origin,
            "owner_identity": None if owner is None else _identity_summary(owner),
            "policy_attributes": {
                "parameter_names": attributes.parameter_names,
                "parameters_match_registration": attributes.parameters_match_registration,
                "provenance": _source(attributes.provenance),
                "registered_path_matches": attributes.registered_path_matches,
                "resource_binding_ref": attributes.resource_binding_ref,
                "resource_binding_revision": attributes.resource_binding_revision,
                "resource_owner_subject_ref": attributes.resource_owner_subject_ref,
                "resource_ref": attributes.resource_ref,
            },
            "profile": {
                "allow_redirects": profile.allow_redirects,
                "allowed_methods": profile.allowed_methods,
                "allowed_purposes": tuple(
                    _enum(item, Purpose) for item in profile.allowed_purposes
                ),
                "source": _source(profile.source),
                "valid_until": profile.valid_until,
            },
            "purpose": _enum(value.purpose, Purpose),
            "request_ref": value.request_ref,
            "run_key": _run_key(value.run_key),
            "schema_version": value.schema_version,
            "scope": {
                "allowed_operation_refs": scope.allowed_operation_refs,
                "allowed_origins": scope.allowed_origins,
                "source": _source(scope.source),
                "valid_from": scope.valid_from,
                "valid_until": scope.valid_until,
            },
            "session_generation": value.session_generation,
            "subject_ref": value.subject_ref,
        }
    )


def _decision_payload(value: PolicyDecision | PolicyDecisionContent) -> CanonicalValue:
    if type(value) not in (PolicyDecision, PolicyDecisionContent):
        raise TypeError("expected PolicyDecision or PolicyDecisionContent")
    return freeze_object(
        {
            "binding_id": value.binding_id,
            "decision_ref": value.decision_ref,
            "evaluated_view_fingerprint": value.evaluated_view_fingerprint,
            "expires_at": value.expires_at,
            "issued_at": value.issued_at,
            "outcome": _enum(value.outcome, PolicyOutcome),
            "policy_version": _source(value.policy_version),
            "reason_codes": tuple(_enum(item, ReasonCode) for item in value.reason_codes),
            "run_key": _run_key(value.run_key),
        }
    )


def _identity_payload(value: IdentityContent | IdentityResult) -> CanonicalValue:
    if type(value) not in (IdentityContent, IdentityResult):
        raise TypeError("expected IdentityContent or IdentityResult")
    return freeze_object(
        {
            "account_ref": value.account_ref,
            "attempt_summaries": tuple(_attempt_summary(item) for item in value.attempt_summaries),
            "evidence_ref": value.evidence_ref,
            "generation": value.generation,
            "identity_ref": value.identity_ref,
            "reason_codes": tuple(_enum(item, ReasonCode) for item in value.reason_codes),
            "run_key": _run_key(value.run_key),
            "session_ref": value.session_ref,
            "status": _enum(value.status, IdentityStatus),
            "subject_ref": value.subject_ref,
            "valid_until": value.valid_until,
            "verified_at": value.verified_at,
        }
    )


def _intent_payload(value: RequestIntentRecord) -> CanonicalValue:
    if type(value) is not RequestIntentRecord:
        raise TypeError("expected RequestIntentRecord")
    return freeze_object(
        {
            "account_ref": value.account_ref,
            "attempt_ref": value.attempt_ref,
            "binding_id": value.binding_id,
            "created_at": value.created_at,
            "decision_ref": value.decision_ref,
            "evaluated_view_fingerprint": value.evaluated_view_fingerprint,
            "operation_ref": value.operation_ref,
            "operation_revision": value.operation_revision,
            "purpose": _enum(value.purpose, Purpose),
            "request_ref": value.request_ref,
            "run_key": _run_key(value.run_key),
            "session_generation": value.session_generation,
        }
    )


def _attempt_payload(value: AttemptRecord) -> CanonicalValue:
    if type(value) is not AttemptRecord:
        raise TypeError("expected AttemptRecord")
    return freeze_object(
        {
            "account_ref": value.account_ref,
            "attempt_ref": value.attempt_ref,
            "binding_id": value.binding_id,
            "capture_status": _enum(value.capture_status, CaptureStatus),
            "decision_ref": value.decision_ref,
            "occurred_at": value.occurred_at,
            "operation_ref": value.operation_ref,
            "reason_codes": tuple(_enum(item, ReasonCode) for item in value.reason_codes),
            "request_ref": value.request_ref,
            "revision": value.revision,
            "run_key": _run_key(value.run_key),
            "send_status": _enum(value.send_status, SendStatus),
            "session_generation": value.session_generation,
        }
    )


def _attempt_summary(value: AttemptSummary) -> dict[str, object]:
    return {
        "run_key": _run_key(value.run_key),
        "request_ref": value.request_ref,
        "attempt_ref": value.attempt_ref,
        "send_status": _enum(value.send_status, SendStatus),
        "audit_links": tuple(
            {"producer": item.producer, "event_ref": item.event_ref} for item in value.audit_links
        ),
        "reason_codes": tuple(_enum(item, ReasonCode) for item in value.reason_codes),
    }


def _expected_policy(value: ExpectedAccessPolicySnapshot) -> dict[str, object]:
    return {
        "source": _source(value.source),
        "policy_ref": value.policy_ref,
        "target_ref": value.target_ref,
        "environment_ref": value.environment_ref,
        "resource_ref": value.resource_ref,
        "operation_ref": value.operation_ref,
        "owner_subject_ref": value.owner_subject_ref,
        "evaluated_subject_ref": value.evaluated_subject_ref,
        "expected_access": _enum(value.expected_access, ExpectedAccess),
        "sharing": _enum(value.sharing, ResolutionState),
        "delegation": _enum(value.delegation, ResolutionState),
        "valid_from": value.valid_from,
        "valid_until": value.valid_until,
    }


def _cross_confirmation(value: CrossExecutionConfirmation) -> dict[str, object]:
    return {
        "source": _source(value.source),
        "run_key": _run_key(value.run_key),
        "resource_ref": value.resource_ref,
        "operation_ref": value.operation_ref,
        "owner_account_ref": value.owner_account_ref,
        "evaluated_account_ref": value.evaluated_account_ref,
        "valid_until": value.valid_until,
    }


def _identity_summary(value: IdentityBindingSummary) -> dict[str, object]:
    return {
        "identity_ref": value.identity_ref,
        "session_ref": value.session_ref,
        "account_ref": value.account_ref,
        "subject_ref": value.subject_ref,
        "generation": value.generation,
        "verified_at": value.verified_at,
        "valid_until": value.valid_until,
    }


def _freeze_mapping(source: Mapping[str, object], active: set[int]) -> CanonicalObject:
    """현재 매핑을 재귀 복사하며 입력 객체 순환을 거부한다."""
    source_id = id(source)
    if source_id in active:
        raise ValueError("cyclic canonical input")
    active.add(source_id)
    try:
        entries = tuple(
            (key, _freeze_value(item, active, allow_mappings=True)) for key, item in source.items()
        )
        return CanonicalObject(entries)
    finally:
        active.remove(source_id)


def _freeze_value(value: object, active: set[int], *, allow_mappings: bool) -> CanonicalValue:
    """지원하는 값만 검증하고 변경 가능한 입력 참조를 제거한다."""
    if value is None:
        return None
    if isinstance(value, bool):
        if type(value) is not bool:
            raise TypeError("unsupported boolean subclass")
        return value
    if isinstance(value, str):
        if type(value) is not str:
            raise TypeError("unsupported string subclass")
        value.encode("utf-8", errors="strict")
        return value
    if isinstance(value, int):
        if type(value) is not int:
            raise TypeError("unsupported integer subclass")
        if not _MIN_INT64 <= value <= _MAX_INT64:
            raise ValueError("integer is outside signed 64-bit range")
        return value
    if isinstance(value, datetime):
        if type(value) is not datetime:
            raise TypeError("unsupported datetime subclass")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(UTC)
    if isinstance(value, CanonicalObject):
        if type(value) is not CanonicalObject:
            raise TypeError("unsupported canonical object subclass")
        return value
    if isinstance(value, tuple):
        if type(value) is not tuple:
            raise TypeError("unsupported tuple subclass")
        value_id = id(value)
        if value_id in active:
            raise ValueError("cyclic canonical input")
        active.add(value_id)
        try:
            return tuple(
                _freeze_value(item, active, allow_mappings=allow_mappings) for item in value
            )
        finally:
            active.remove(value_id)
    if isinstance(value, (dict, MappingProxyType)) and allow_mappings:
        if type(value) not in (dict, MappingProxyType):
            raise TypeError("unsupported mapping subclass")
        return _freeze_mapping(value, active)
    raise TypeError("unsupported canonical value type")


def freeze_object(source: Mapping[str, object]) -> CanonicalObject:
    """명시적으로 허용한 매핑을 재귀 복사해 불변 snapshot을 만든다."""
    if type(source) not in (dict, MappingProxyType):
        raise TypeError("snapshot source must be a dict or mapping proxy")
    return _freeze_mapping(source, set())


def _canonicalize_value(value: CanonicalValue) -> _JsonValue:
    """정규 인코딩 가능한 JSON 자료형만 구성한다."""
    if value is None:
        return None
    if isinstance(value, (bool, str)):
        if type(value) not in (bool, str):
            raise TypeError("unsupported canonical scalar subclass")
        return value
    if isinstance(value, int):
        if type(value) is not int:
            raise TypeError("unsupported integer subclass")
        if not _MIN_INT64 <= value <= _MAX_INT64:
            raise ValueError("integer is outside signed 64-bit range")
        return value
    if isinstance(value, datetime):
        if type(value) is not datetime:
            raise TypeError("unsupported datetime subclass")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        normalized = value.astimezone(UTC)
        return normalized.isoformat(timespec="microseconds").removesuffix("+00:00") + "Z"
    if isinstance(value, tuple):
        if type(value) is not tuple:
            raise TypeError("unsupported tuple subclass")
        return [_canonicalize_value(item) for item in value]
    if isinstance(value, CanonicalObject):
        if type(value) is not CanonicalObject:
            raise TypeError("unsupported canonical object subclass")
        return {key: _canonicalize_value(item) for key, item in value.entries}
    raise TypeError("unsupported canonical value type")


def canonical_json_bytes(value: CanonicalValue) -> bytes:
    """불변 값을 canonical-json.v1 UTF-8 바이트로 인코딩한다."""
    frozen = _freeze_value(value, set(), allow_mappings=False)
    normalized = _canonicalize_value(frozen)
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return encoded.encode("utf-8", errors="strict")


_REGISTERED_RECORDS: tuple[_RecordRegistration, ...] = (
    _RecordRegistration(
        CODEC_VERSION,
        "policy_input",
        "policy_input.v1",
        PolicyInput,
        cast(Callable[[object], CanonicalValue], _policy_input_payload),
    ),
    _RecordRegistration(
        CODEC_VERSION,
        "policy_decision",
        "policy_decision.v1",
        PolicyDecisionContent,
        cast(Callable[[object], CanonicalValue], _decision_payload),
    ),
    _RecordRegistration(
        CODEC_VERSION,
        "policy_decision",
        "policy_decision.v1",
        PolicyDecision,
        cast(Callable[[object], CanonicalValue], _decision_payload),
    ),
    _RecordRegistration(
        CODEC_VERSION,
        "identity",
        "identity.v1",
        IdentityContent,
        cast(Callable[[object], CanonicalValue], _identity_payload),
    ),
    _RecordRegistration(
        CODEC_VERSION,
        "identity",
        "identity.v1",
        IdentityResult,
        cast(Callable[[object], CanonicalValue], _identity_payload),
    ),
    _RecordRegistration(
        CODEC_VERSION,
        "request_intent",
        "request_intent.v1",
        RequestIntentRecord,
        cast(Callable[[object], CanonicalValue], _intent_payload),
    ),
    _RecordRegistration(
        CODEC_VERSION,
        "attempt",
        "attempt.v1",
        AttemptRecord,
        cast(Callable[[object], CanonicalValue], _attempt_payload),
    ),
)


def _registered_record_fingerprint(record: object) -> str:
    """등록된 정확한 업무 타입만 fingerprint로 변환한다."""
    return sha256(canonical_json_bytes(_registered_record_envelope(record))).hexdigest()


def _registered_record_envelope(record: object) -> CanonicalObject:
    """Build the validated fixed envelope used by operational fingerprints."""
    for registration in _REGISTERED_RECORDS:
        if type(record) is not registration.record_type:
            continue
        if registration.codec_version != CODEC_VERSION:
            raise ValueError("unsupported fingerprint codec version")
        validate_record(record)
        _validate_field_shapes(record)
        payload = registration.payload_adapter(record)
        return freeze_object(
            {
                "codec_version": registration.codec_version,
                "record_kind": registration.record_kind,
                "schema_version": registration.schema_version,
                "payload": payload,
            }
        )
    raise ValueError("unregistered fingerprint record")


def policy_input_fingerprint(value: PolicyInput) -> str:
    """Fingerprint an exact PolicyInput using the policy_input.v1 envelope."""
    if type(value) is not PolicyInput:
        raise TypeError("expected exact PolicyInput")
    return _registered_record_fingerprint(value)


def policy_decision_fingerprint(value: PolicyDecision) -> str:
    """Fingerprint an exact committed PolicyDecision."""
    if type(value) is not PolicyDecision:
        raise TypeError("expected exact PolicyDecision")
    return _registered_record_fingerprint(value)


def policy_decision_content_fingerprint(value: PolicyDecisionContent) -> str:
    """Fingerprint receipt-free PolicyDecisionContent before commit."""
    if type(value) is not PolicyDecisionContent:
        raise TypeError("expected exact PolicyDecisionContent")
    return _registered_record_fingerprint(value)


def identity_fingerprint(value: IdentityResult) -> str:
    """Fingerprint an exact IdentityResult without including its receipt."""
    if type(value) is not IdentityResult:
        raise TypeError("expected exact IdentityResult")
    return _registered_record_fingerprint(value)


def identity_content_fingerprint(value: IdentityContent) -> str:
    """Fingerprint receipt-free IdentityContent before commit."""
    if type(value) is not IdentityContent:
        raise TypeError("expected exact IdentityContent")
    return _registered_record_fingerprint(value)


def request_intent_fingerprint(value: RequestIntentRecord) -> str:
    """Fingerprint an exact RequestIntentRecord."""
    if type(value) is not RequestIntentRecord:
        raise TypeError("expected exact RequestIntentRecord")
    return _registered_record_fingerprint(value)


def attempt_fingerprint(value: AttemptRecord) -> str:
    """Fingerprint an exact AttemptRecord."""
    if type(value) is not AttemptRecord:
        raise TypeError("expected exact AttemptRecord")
    return _registered_record_fingerprint(value)
