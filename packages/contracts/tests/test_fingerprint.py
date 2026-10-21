"""canonical-json.v1 정규 바이트와 C1 운영 거부 경계를 검사한다."""

import json
from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import TypedDict, cast

import pytest
from abc2lab_contracts.fingerprint import (
    CODEC_VERSION,
    CanonicalObject,
    CanonicalValue,
    _registered_record_fingerprint,
    canonical_json_bytes,
    freeze_object,
)

_VECTOR_FILE = Path(__file__).resolve().parents[3] / "docs/examples/fingerprint-v1-vectors.json"


class _Vector(TypedDict):
    """저장소에서 제공하는 고정 벡터의 검사 대상 필드."""

    id: str
    validation_path: str
    canonical_utf8: str
    sha256: str


class _VectorFile(TypedDict):
    """고정 벡터 파일의 상위 구조."""

    codec_version: str
    vectors: list[_Vector]


def _primitive_envelope() -> CanonicalObject:
    """demo.record의 실제 Python tuple과 불변 객체를 구성한다."""
    return freeze_object(
        {
            "codec_version": CODEC_VERSION,
            "record_kind": "demo.record",
            "schema_version": "demo.v1",
            "payload": {
                "attributes": {"enabled": True, "labels": ("가", "A"), "optional": None},
                "schema_version": "demo.v1",
                "source": {"issuer": "발급자", "revision": 1, "source_ref": "정책-α"},
            },
        }
    )


def test_primitive_golden_vector_canonical_bytes_and_sha256() -> None:
    """C1 demo 벡터는 저수준 bytes 경로에서만 검증한다."""
    vectors = cast(_VectorFile, json.loads(_VECTOR_FILE.read_text(encoding="utf-8")))
    assert vectors["codec_version"] == CODEC_VERSION
    matching = [vector for vector in vectors["vectors"] if vector["id"] == "primitive-v1"]
    assert len(matching) == 1
    vector = matching[0]
    assert vector["validation_path"] == "canonical_bytes_only"

    encoded = canonical_json_bytes(_primitive_envelope())
    assert encoded == vector["canonical_utf8"].encode("utf-8")
    assert sha256(encoded).hexdigest() == vector["sha256"]
    assert not encoded.startswith(b"\xef\xbb\xbf")
    assert not encoded.endswith(b"\n")


def test_mapping_insertion_order_does_not_change_bytes() -> None:
    """중첩 매핑의 선언·삽입 순서가 정규 바이트를 바꾸지 않는다."""
    first = freeze_object({"z": {"b": 2, "a": 1}, "a": (1, 2)})
    second = freeze_object({"a": (1, 2), "z": {"a": 1, "b": 2}})
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first == second


def test_tuple_order_and_source_revision_change_bytes() -> None:
    """목록 원소 순서와 출처 revision은 fingerprint 입력의 일부다."""
    source_one = freeze_object({"issuer": "origin", "source_ref": "scope", "revision": 1})
    source_two = freeze_object({"revision": 2, "source_ref": "scope", "issuer": "origin"})
    assert canonical_json_bytes(("a", "b")) != canonical_json_bytes(("b", "a"))
    assert canonical_json_bytes(source_one) != canonical_json_bytes(source_two)


def test_none_is_not_an_omitted_field() -> None:
    """None이 있는 필드와 생략된 필드를 구분한다."""
    assert canonical_json_bytes(freeze_object({"value": None})) != canonical_json_bytes(
        freeze_object({})
    )


def test_exact_timestamp_format_and_utc_normalization() -> None:
    """동일 시각은 타임존과 무관하게 동일한 UTC 바이트로 직렬화한다."""
    utc = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC)
    offset = datetime(2026, 10, 21, 9, 0, 0, tzinfo=timezone(timedelta(hours=9)))
    assert canonical_json_bytes(utc) == b'"2026-10-21T00:00:00.000000Z"'
    assert canonical_json_bytes(utc) == canonical_json_bytes(offset)


@pytest.mark.parametrize("year", [1, 9, 99, 999, 1000])
def test_utc_year_has_four_digits(year: int) -> None:
    """1~9999년의 UTC 정규 문자열은 연도를 항상 네 자리로 표현한다."""
    timestamp = datetime(year, 1, 2, 3, 4, 5, 6, tzinfo=UTC)
    expected = f'"{year:04d}-01-02T03:04:05.000006Z"'.encode("ascii")
    assert canonical_json_bytes(timestamp) == expected
    assert canonical_json_bytes(freeze_object({"at": timestamp})) == (b'{"at":' + expected + b"}")


def test_unicode_codepoints_are_not_normalized() -> None:
    """동등해 보이는 Unicode 문자열도 코드 포인트가 다르면 구별한다."""
    assert canonical_json_bytes("é") != canonical_json_bytes("e\u0301")
    assert canonical_json_bytes("가") == '"가"'.encode()


def test_signed_64_bit_integer_boundaries() -> None:
    """정수는 signed 64-bit 범위에서만 허용한다."""
    assert canonical_json_bytes(-(2**63)) == b"-9223372036854775808"
    assert canonical_json_bytes(2**63 - 1) == b"9223372036854775807"
    for invalid in (-(2**63) - 1, 2**63):
        with pytest.raises(ValueError, match="signed 64-bit"):
            canonical_json_bytes(invalid)


class _DemoEnum(StrEnum):
    """업무 enum의 저수준 인코딩 우회를 검사한다."""

    VALUE = "demo"


@dataclass(frozen=True)
class _DemoRecord:
    """업무 dataclass의 저수준 인코딩 우회를 검사한다."""

    name: str


@pytest.mark.parametrize(
    "invalid",
    [
        1.2,
        float("nan"),
        float("inf"),
        float("-inf"),
        [],
        ["a", "b"],
        {"x"},
        {"name": "value"},
        b"raw",
        Decimal("1.5"),
        datetime(2026, 10, 21),
        _DemoEnum.VALUE,
        _DemoRecord("demo"),
        MappingProxyType({"value": 1}),
    ],
)
def test_reject_unsupported_values(invalid: object) -> None:
    """비허용 타입과 시간은 재귀 통과 또는 암묵적 변환 없이 거부한다."""
    with pytest.raises((TypeError, ValueError)):
        canonical_json_bytes(cast(CanonicalValue, invalid))


def test_reject_nested_mutable_value_and_nonstring_key() -> None:
    """불변 객체 생성 및 저수준 경로에서 가변 값과 비문자 키를 거부한다."""
    with pytest.raises(TypeError, match="unsupported canonical value"):
        freeze_object({"nested": [1, 2]})
    with pytest.raises(TypeError, match="unsupported canonical value"):
        canonical_json_bytes(cast(CanonicalValue, ("nested", [1, 2])))
    with pytest.raises(TypeError, match="mapping keys must be strings"):
        freeze_object(cast(dict[str, object], {1: "value"}))


def test_reject_lone_unicode_surrogates() -> None:
    """UTF-8로 온전히 표현할 수 없는 문자열과 키를 거부한다."""
    with pytest.raises(UnicodeEncodeError):
        canonical_json_bytes("\ud800")
    with pytest.raises(UnicodeEncodeError):
        freeze_object({"\udfff": "x"})


def test_c1_rejects_demo_and_operational_records() -> None:
    """등록 목록이 비어 있으므로 운영 fingerprint를 발행할 수 없다."""
    for record in (_primitive_envelope(), _DemoRecord("demo"), object()):
        with pytest.raises(ValueError, match="unregistered fingerprint record"):
            _registered_record_fingerprint(record)


def test_freeze_object_is_independent_of_nested_dict_changes() -> None:
    """완료된 불변 snapshot은 외부 중첩 딕셔너리 수정을 관찰하지 않는다."""
    original: dict[str, object] = {
        "resource": {"owner": "a", "revision": 1},
        "events": ({"action": "read"}, {"action": "compare"}),
    }
    frozen = freeze_object(original)
    before = canonical_json_bytes(frozen)

    resource = cast(dict[str, object], original["resource"])
    resource["revision"] = 2
    original["resource"] = {"owner": "b", "revision": 3}
    events = cast(tuple[dict[str, str], ...], original["events"])
    events[0]["action"] = "modify"

    assert canonical_json_bytes(frozen) == before
    assert before == canonical_json_bytes(
        freeze_object(
            {
                "resource": {"owner": "a", "revision": 1},
                "events": ({"action": "read"}, {"action": "compare"}),
            }
        )
    )


def test_freeze_object_is_independent_of_mapping_proxy_origin() -> None:
    """읽기 전용 프록시 원본의 후속 변경도 snapshot에 전파되지 않는다."""
    original: dict[str, object] = {"revision": 1, "nested": {"flag": True}}
    snapshot = freeze_object(MappingProxyType(original))
    expected = canonical_json_bytes(snapshot)
    original["revision"] = 2
    nested = cast(dict[str, bool], original["nested"])
    nested["flag"] = False
    assert canonical_json_bytes(snapshot) == expected


def test_canonical_object_is_frozen_and_rejects_duplicate_keys() -> None:
    """직접 생성해도 불변성·중복 키 검증이 유지된다."""
    snapshot = CanonicalObject((("revision", 1),))
    with pytest.raises(FrozenInstanceError):
        snapshot.entries = (("revision", 2),)  # type: ignore[misc]
    assert snapshot.entries == (("revision", 1),)
    with pytest.raises(ValueError, match="duplicate"):
        CanonicalObject((("x", 1), ("x", 2)))
    with pytest.raises(TypeError, match="unsupported canonical value"):
        CanonicalObject((("value", cast(CanonicalValue, {"mutable": 1})),))


def test_freeze_object_rejects_cyclic_input() -> None:
    """자기 참조하는 입력은 재귀 오류 대신 명시적 오류로 거부한다."""
    original: dict[str, object] = {}
    original["self"] = original
    with pytest.raises(ValueError, match="cyclic canonical input"):
        freeze_object(original)


def test_freeze_object_normalizes_datetime_during_snapshot() -> None:
    """완료된 snapshot의 datetime은 UTC로 고정된다."""
    date = datetime(2026, 10, 21, 9, tzinfo=timezone(timedelta(hours=9)))
    snapshot = freeze_object({"date": date})
    assert canonical_json_bytes(snapshot) == b'{"date":"2026-10-21T00:00:00.000000Z"}'
    assert snapshot.entries[0][1] == datetime(2026, 10, 21, tzinfo=UTC)


def test_freeze_object_does_not_relabel_operational_records() -> None:
    """명시적인 스냅샷 생성은 운영 등록 우회를 허용하지 않는다."""
    snapshot = freeze_object({"record_kind": "policy_input", "schema_version": "policy_input.v1"})
    with pytest.raises(ValueError, match="unregistered fingerprint record"):
        _registered_record_fingerprint(snapshot)
