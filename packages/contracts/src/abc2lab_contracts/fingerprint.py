"""결정적 정규 JSON 인코딩과 운영 fingerprint 등록 경계를 정의한다."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from types import MappingProxyType

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
    record_type: type[object]
    payload_adapter: Callable[[object], CanonicalValue]


# C1의 등록 목록은 비어 있다. C2에서 타입과 adapter를 함께 추가한다.
_REGISTERED_RECORDS: tuple[_RecordRegistration, ...] = ()


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


def _registered_record_fingerprint(record: object) -> str:
    """등록된 정확한 업무 타입만 fingerprint로 변환한다."""
    for registration in _REGISTERED_RECORDS:
        if type(record) is not registration.record_type:
            continue
        if registration.codec_version != CODEC_VERSION:
            raise ValueError("unsupported fingerprint codec version")
        payload = registration.payload_adapter(record)
        envelope = freeze_object(
            {
                "codec_version": registration.codec_version,
                "record_kind": registration.record_kind,
                "schema_version": registration.schema_version,
                "payload": payload,
            }
        )
        return sha256(canonical_json_bytes(envelope)).hexdigest()
    raise ValueError("unregistered fingerprint record")
