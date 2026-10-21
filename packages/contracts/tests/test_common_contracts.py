"""Runtime validation tests for the immutable C2 common contracts."""

from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
from typing import cast

import pytest
from abc2lab_contracts.primitives import (
    AttemptSummary,
    AuditLink,
    CaptureStatus,
    ParameterLocation,
    Purpose,
    RequestParameter,
    ResultStatus,
    RunKey,
    SendStatus,
    SourceVersion,
)
from abc2lab_contracts.registration import (
    BudgetSnapshot,
    ScopeSnapshot,
)


class _ForeignStatus(StrEnum):
    COMPLETE = "complete"


def _source() -> SourceVersion:
    return SourceVersion("issuer", "source", 1)


def _run() -> RunKey:
    return RunKey("org", "target", "env", "run")


def test_common_records_are_frozen_and_validate_refs() -> None:
    record = RunKey("org", "target", "env", "run")
    with pytest.raises(AttributeError):
        record.run_ref = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="reference"):
        RunKey("", "target", "env", "run")
    with pytest.raises(ValueError, match="positive"):
        SourceVersion("issuer", "source", 0)
    with pytest.raises(TypeError, match="int"):
        SourceVersion("issuer", "source", True)
    with pytest.raises(TypeError, match="string reference"):
        RunKey(None, "target", "env", "run")  # type: ignore[arg-type]


def test_records_require_tuples_and_reject_mutable_values() -> None:
    with pytest.raises(TypeError, match="tuple"):
        AttemptSummary(
            _run(), "request", "attempt", SendStatus.NOT_SENT, cast(tuple[AuditLink, ...], []), ()
        )


def test_parameter_and_budget_invariants() -> None:
    assert RequestParameter("id", ParameterLocation.PATH, "7").location is ParameterLocation.PATH
    with pytest.raises(TypeError, match="enum"):
        RequestParameter("id", cast(ParameterLocation, "header"), "7")
    with pytest.raises(ValueError, match="positive"):
        BudgetSnapshot(_source(), 0, 100, 100)


def test_scope_normalizes_and_orders_utc_timestamps() -> None:
    start = datetime(2026, 10, 21, 9, tzinfo=timezone(timedelta(hours=9)))
    end = datetime(2026, 10, 21, 1, tzinfo=UTC)
    scope = ScopeSnapshot(_source(), ("https://example.test",), ("op",), start, end)
    assert scope.valid_from.astimezone(UTC) == datetime(2026, 10, 21, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="ordered"):
        ScopeSnapshot(_source(), (), (), end, start)
    with pytest.raises(ValueError, match="timezone"):
        ScopeSnapshot(_source(), (), (), datetime(2026, 1, 1), end)


def test_attempt_summary_keeps_audit_links_and_enum_values() -> None:
    summary = AttemptSummary(
        _run(),
        "request",
        "attempt",
        SendStatus.UNKNOWN,
        (AuditLink("gateway", "event"),),
        (),
    )
    assert summary.send_status is SendStatus.UNKNOWN
    assert CaptureStatus.CAPTURED.value == "captured"
    assert ResultStatus.COMPLETE.value == "complete"
    assert Purpose.ACCESS_COMPARE.value == "access_compare"


def test_nested_types_are_closed_and_tampering_is_revalidated() -> None:
    with pytest.raises(TypeError, match="enum"):
        AttemptSummary(
            _run(),
            "request",
            "attempt",
            _ForeignStatus.COMPLETE,  # type: ignore[arg-type]
            (),
            (),
        )
    with pytest.raises(TypeError, match="contract record"):
        AttemptSummary("run", "request", "attempt", SendStatus.UNKNOWN, (), ())  # type: ignore[arg-type]
    source = _source()
    object.__setattr__(source, "revision", 0)
    with pytest.raises(ValueError, match="positive revision"):
        BudgetSnapshot(source, 1, 100, 100)
    assert not hasattr(_run(), "__dict__")
