"""C4 operational fingerprints for Knowledge-facing records."""

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import TypedDict, cast

import pytest
from abc2lab_contracts.audit import AuditEventKind, AuditReceipt, AuditRecordBinding
from abc2lab_contracts.fingerprint import (
    _REGISTERED_RECORDS,
    _registered_record_envelope,
    canonical_json_bytes,
    expected_policy_fingerprint,
    freeze_object,
    observation_fingerprint,
    verdict_fingerprint,
)
from abc2lab_contracts.observation import Observation
from abc2lab_contracts.primitives import (
    AuditLink,
    CheckState,
    ReasonCode,
    ResponseClass,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.projection import VerdictProjected
from abc2lab_contracts.registration import (
    ExpectedAccess,
    ExpectedAccessPolicySnapshot,
    ResolutionState,
)
from abc2lab_contracts.verdict import Verdict, VerdictValue


class _Vector(TypedDict):
    id: str
    validation_path: str
    record_kind: str
    schema_version: str
    canonical_utf8: str
    sha256: str


VECTORS = cast(
    list[_Vector],
    json.loads(
        (
            Path(__file__).resolve().parents[3] / "docs/examples/fingerprint-v1-vectors.json"
        ).read_text(encoding="utf-8")
    )["vectors"],
)


def _vector(vector_id: str) -> _Vector:
    return next(vector for vector in VECTORS if vector["id"] == vector_id)


def _c4_run() -> RunKey:
    return RunKey("org-c4", "target-c4", "env-c4", "run-c4")


def _c4_observation() -> Observation:
    return Observation(
        _c4_run(),
        "observation-a",
        "candidate-a",
        "resource-a",
        "op-read",
        "account-owner",
        2,
        "identity-owner",
        ResponseClass.NORMAL,
        "evidence-owner",
        AuditLink("webdiag-producer", "event-observation"),
        datetime(2026, 10, 21, tzinfo=UTC),
        (),
    )


def _c4_verdict() -> Verdict:
    return Verdict(
        _c4_run(),
        "verdict-a",
        3,
        "case-a",
        VerdictValue.UNDECIDABLE,
        CheckState.UNKNOWN,
        CheckState.YES,
        CheckState.UNKNOWN,
        None,
        "comparison-a",
        ("evidence-owner", "evidence-cross"),
        SourceVersion("app", "comparison-rules", 2),
        AuditLink("judge-producer", "event-verdict"),
        (ReasonCode.COMPARISON_INCOMPLETE,),
    )


def _c4_policy() -> ExpectedAccessPolicySnapshot:
    return ExpectedAccessPolicySnapshot(
        SourceVersion("app", "expected-policy", 2),
        "policy-a",
        "target-c4",
        "env-c4",
        "resource-a",
        "op-read",
        "subject-owner",
        "subject-cross",
        ExpectedAccess.DENY,
        ResolutionState.RESOLVED_NONE,
        ResolutionState.RESOLVED_NONE,
        datetime(2026, 10, 21, tzinfo=UTC),
        datetime(2026, 10, 21, 1, tzinfo=UTC),
    )


def _run() -> RunKey:
    return RunKey("org", "target", "environment", "run")


def _observation() -> Observation:
    return Observation(
        _run(),
        "observation-1",
        "candidate-1",
        "resource-1",
        "operation-1",
        "account-1",
        1,
        "identity-1",
        ResponseClass.NORMAL,
        "evidence-1",
        AuditLink("webdiag", "event-1"),
        datetime(2026, 10, 21, tzinfo=UTC),
        (ReasonCode.CONFIGURATION_MISSING,),
    )


def _verdict() -> Verdict:
    return Verdict(
        _run(),
        "verdict-1",
        2,
        "case-1",
        VerdictValue.SUSPECTED,
        CheckState.UNKNOWN,
        CheckState.YES,
        CheckState.YES,
        None,
        "comparison-1",
        ("evidence-owner", "evidence-cross"),
        SourceVersion("judge", "oracle", 4),
        AuditLink("judge", "event-2"),
        (ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,),
    )


def _policy() -> ExpectedAccessPolicySnapshot:
    return ExpectedAccessPolicySnapshot(
        SourceVersion("registration", "policy", 3),
        "policy-1",
        "target",
        "environment",
        "resource-1",
        "operation-1",
        "owner-subject",
        "evaluated-subject",
        ExpectedAccess.DENY,
        ResolutionState.RESOLVED_NONE,
        ResolutionState.RESOLVED_NONE,
        datetime(2026, 10, 21, tzinfo=UTC),
        datetime(2026, 10, 22, tzinfo=UTC),
    )


class _ObservationSubclass(Observation):
    pass


class _VerdictSubclass(Verdict):
    pass


class _PolicySubclass(ExpectedAccessPolicySnapshot):
    pass


@pytest.mark.parametrize(
    ("fingerprint", "value", "subclass"),
    [
        (observation_fingerprint, _observation(), _ObservationSubclass),
        (verdict_fingerprint, _verdict(), _VerdictSubclass),
        (expected_policy_fingerprint, _policy(), _PolicySubclass),
    ],
)
def test_fingerprint_requires_exact_registered_type(
    fingerprint: Callable[[object], str], value: object, subclass: type[object]
) -> None:
    with pytest.raises(TypeError, match="exact|Expected|Observation|Verdict"):
        fingerprint(object.__new__(subclass))


def test_observation_fingerprint_changes_for_nested_and_scalar_tampering() -> None:
    value = _observation()
    digest = observation_fingerprint(value)
    forged_source = replace(value, source_event=AuditLink("forged", "event-1"))
    assert observation_fingerprint(forged_source) != digest
    assert observation_fingerprint(replace(value, reason_codes=())) != digest
    shifted = replace(value, observed_at=value.observed_at + timedelta(seconds=1))
    assert observation_fingerprint(shifted) != digest


def test_verdict_fingerprint_distinguishes_null_from_present_optional_fields() -> None:
    value = replace(_c4_verdict(), comparison_ref=None)
    absent_digest = verdict_fingerprint(value)
    present = replace(value, expected_policy_source=SourceVersion("registration", "policy", 3))
    assert verdict_fingerprint(present) != absent_digest
    assert verdict_fingerprint(replace(value, comparison_ref="comparison-1")) != absent_digest


def test_policy_fingerprint_normalizes_equivalent_utc_offsets_and_rejects_naive_time() -> None:
    value = _policy()
    shifted = replace(
        value,
        valid_from=datetime(2026, 10, 21, 9, tzinfo=timezone(timedelta(hours=9))),
    )
    assert expected_policy_fingerprint(shifted) == expected_policy_fingerprint(value)
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(value, valid_from=datetime(2026, 10, 21))


def test_fingerprint_detects_mutation_even_when_frozen_record_is_bypassed() -> None:
    value = _observation()
    digest = observation_fingerprint(value)
    object.__setattr__(value, "evidence_ref", "evidence-forged")
    assert observation_fingerprint(value) != digest


def test_fingerprint_rejects_missing_nullable_field_and_nested_type_tampering() -> None:
    verdict = _c4_verdict()
    object.__delattr__(verdict, "expected_policy_source")
    with pytest.raises(TypeError, match="missing"):
        verdict_fingerprint(verdict)
    policy = _c4_policy()
    object.__setattr__(policy.source, "revision", True)
    with pytest.raises(TypeError, match="integer revision"):
        expected_policy_fingerprint(policy)
    observation = _c4_observation()
    object.__setattr__(observation, "reason_codes", [])
    with pytest.raises(TypeError, match="tuple"):
        observation_fingerprint(observation)


@pytest.mark.parametrize(
    ("vector_id", "factory", "fingerprint", "kind", "version"),
    [
        ("observation-v1-c4", _c4_observation, observation_fingerprint, "observation", "v1"),
        ("verdict-v2-c4", _c4_verdict, verdict_fingerprint, "verdict", "v2"),
        ("expected-policy-v1-c4", _c4_policy, expected_policy_fingerprint, "expected_policy", "v1"),
    ],
)
def test_c4_golden_vectors_pin_canonical_bytes_and_wrapper_digest(
    vector_id: str,
    factory: Callable[[], object],
    fingerprint: Callable[[object], str],
    kind: str,
    version: str,
) -> None:
    vector = _vector(vector_id)
    assert vector["validation_path"] == "production_adapter"
    assert vector["record_kind"] == kind
    assert vector["schema_version"] == f"{kind}.{version}"
    record = factory()
    canonical = canonical_json_bytes(_registered_record_envelope(record))
    assert canonical.decode("utf-8") == vector["canonical_utf8"]
    assert sha256(canonical).hexdigest() == vector["sha256"]
    assert fingerprint(record) == vector["sha256"]


def test_verdict_has_only_one_operational_version_and_golden_vector() -> None:
    registrations = [
        (item.schema_version, item.record_type)
        for item in _REGISTERED_RECORDS
        if item.record_kind == "verdict"
    ]
    assert registrations == [("verdict.v2", Verdict)]
    assert [item["id"] for item in VECTORS if item["record_kind"] == "verdict"] == ["verdict-v2-c4"]


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("run_key", RunKey("org", "target", "environment", "other-run")),
        ("verdict_ref", "other-verdict"),
        ("revision", 3),
        ("case_ref", "other-case"),
        ("value", VerdictValue.UNDECIDABLE),
        ("expected_policy_source", SourceVersion("app", "policy", 2)),
        ("comparison_ref", "other-comparison"),
        ("evidence_refs", ("other-evidence",)),
        ("oracle_version", SourceVersion("judge", "oracle", 5)),
        ("source_event", AuditLink("other-producer", "event-2")),
        ("source_event", AuditLink("judge", "other-event")),
        ("reason_codes", (ReasonCode.DATA_UNVERIFIABLE,)),
    ],
)
def test_verdict_fingerprint_covers_business_fields(field: str, replacement: object) -> None:
    verdict = _verdict()
    changed = replace(verdict, **{field: replacement})  # type: ignore[arg-type]
    assert verdict_fingerprint(changed) != verdict_fingerprint(verdict)


@pytest.mark.parametrize("field", ["policy_check", "identity_check", "data_check"])
def test_verdict_fingerprint_covers_each_check(field: str) -> None:
    verdict = _c4_verdict()
    changed = replace(verdict, **{field: CheckState.NO})  # type: ignore[arg-type]
    assert verdict_fingerprint(changed) != verdict_fingerprint(verdict)


def test_verdict_fingerprint_rejects_dict_other_record_and_invalid_bypassed_content() -> None:
    invalid: tuple[object, ...] = ({}, _observation())
    for value in invalid:
        with pytest.raises(TypeError, match="exact Verdict"):
            verdict_fingerprint(cast(Verdict, value))
    verdict = _verdict()
    object.__setattr__(verdict, "data_check", CheckState.UNKNOWN)
    with pytest.raises(ValueError, match="suspected"):
        verdict_fingerprint(verdict)


def test_verdict_projection_rejects_same_payload_with_legacy_v1_digest() -> None:
    verdict = _c4_verdict()
    # A downgraded envelope is test data only; production exposes no v1 wrapper.
    old_envelope = dict(_registered_record_envelope(verdict).entries)
    old_envelope["schema_version"] = "verdict.v1"
    old_digest = sha256(canonical_json_bytes(freeze_object(old_envelope))).hexdigest()
    assert old_digest != verdict_fingerprint(verdict)
    binding = AuditRecordBinding(
        AuditEventKind.VERDICT, verdict.verdict_ref, verdict.revision, old_digest, None, None, None
    )
    receipt = AuditReceipt(
        verdict.run_key,
        verdict.source_event.producer,
        verdict.source_event.event_ref,
        1,
        binding,
        datetime(2026, 10, 21, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="binding mismatch"):
        VerdictProjected(
            AuditEventKind.VERDICT,
            verdict.source_event.event_ref,
            verdict.run_key,
            verdict.source_event.producer,
            verdict.revision,
            receipt,
            verdict,
        )
