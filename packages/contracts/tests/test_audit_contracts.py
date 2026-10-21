"""Runtime checks for C2 audit records."""

from datetime import UTC, datetime

import pytest
from abc2lab_contracts.audit import (
    AttemptRecord,
    AuditEvent,
    AuditEventKind,
    AuditPage,
    AuditReadRequest,
    AuditReceipt,
    AuditRecordBinding,
    PolicyOutcome,
    RequestIntentRecord,
)
from abc2lab_contracts.primitives import (
    AuditLink,
    CaptureStatus,
    Purpose,
    ReadContext,
    ResultStatus,
    RunKey,
    SendStatus,
)

NOW = datetime(2026, 10, 21, tzinfo=UTC)


def _run_key() -> RunKey:
    return RunKey("org", "target", "env", "run")


def _binding() -> AuditRecordBinding:
    return AuditRecordBinding(
        event_kind=AuditEventKind.POLICY_DECISION,
        record_ref="decision-1",
        record_revision=1,
        record_fingerprint="a" * 64,
        request_ref="request-1",
        attempt_ref="attempt-1",
        binding_id="binding-1",
    )


def _receipt() -> AuditReceipt:
    return AuditReceipt(_run_key(), "policy", "event-1", 1, _binding(), NOW)


def test_attempt_requires_documented_send_capture_pair() -> None:
    AttemptRecord(
        _run_key(),
        "request-1",
        "attempt-1",
        1,
        "decision-1",
        "binding-1",
        "operation-1",
        "account-1",
        2,
        SendStatus.SENT,
        CaptureStatus.CAPTURED,
        NOW,
        (),
    )
    with pytest.raises(ValueError, match="send and capture"):
        AttemptRecord(
            _run_key(),
            "request-1",
            "attempt-1",
            1,
            None,
            None,
            None,
            None,
            None,
            SendStatus.NOT_SENT,
            CaptureStatus.INDETERMINATE,
            NOW,
            (),
        )


def test_audit_event_preserves_links_and_rejects_negative_elapsed() -> None:
    event = AuditEvent(
        _receipt(),
        (AuditLink("gateway", "event-0"),),
        None,
        "task-1",
        None,
        "account-1",
        2,
        (),
        (),
        NOW,
        NOW,
        "gateway-instance-1",
        0,
        PolicyOutcome.ALLOW,
        SendStatus.SENT,
        (),
    )
    assert event.receipt.binding.record_fingerprint == "a" * 64
    with pytest.raises(ValueError, match="must not be negative"):
        AuditEvent(
            _receipt(),
            (),
            None,
            None,
            None,
            None,
            None,
            (),
            (),
            NOW,
            NOW,
            "gateway-instance-1",
            -1,
            None,
            None,
            (),
        )


def test_audit_read_cursor_requires_snapshot_and_limit() -> None:
    context = ReadContext("caller", "authorization")
    with pytest.raises(ValueError, match="requires a snapshot"):
        AuditReadRequest(_run_key(), context, "gateway", "cursor-1", None, 10)
    with pytest.raises(ValueError, match="between one"):
        AuditReadRequest(_run_key(), context, "gateway", None, None, 101)


def test_complete_empty_page_uses_explicit_zero_watermarks() -> None:
    page = AuditPage(_run_key(), ResultStatus.COMPLETE, "gateway", (), None, "snap", None, 0, 0, ())
    assert page.terminal_sequence == 0
    with pytest.raises(ValueError, match="sealed empty|first sequence"):
        AuditPage(_run_key(), ResultStatus.COMPLETE, "gateway", (), None, "snap", 1, 0, 0, ())
    failed = AuditPage(_run_key(), ResultStatus.FAILED, "gateway", (), None, None, 1, 2, None, ())
    assert failed.status is ResultStatus.FAILED


def test_request_intent_is_immutable_and_revision_is_one() -> None:
    record = RequestIntentRecord(
        _run_key(),
        "request-1",
        "attempt-1",
        "binding-1",
        "operation-1",
        7,
        Purpose.OBSERVE,
        None,
        None,
        "decision-1",
        "b" * 64,
        NOW,
    )
    assert record.created_at == NOW
    open_page = AuditPage(
        _run_key(), ResultStatus.COMPLETE, "gateway", (), None, "snap", None, None, None, ()
    )
    assert open_page.terminal_sequence is None


@pytest.mark.parametrize("first, committed, terminal", [(0, 1, 1), (2, 1, 2), (None, 0, None)])
def test_audit_page_rejects_impossible_or_unknown_zero_watermarks(
    first: int | None, committed: int | None, terminal: int | None
) -> None:
    with pytest.raises(ValueError):
        AuditPage(
            _run_key(),
            ResultStatus.COMPLETE,
            "gateway",
            (),
            None,
            "snap",
            first,
            committed,
            terminal,
            (),
        )


def test_audit_page_next_cursor_requires_snapshot() -> None:
    with pytest.raises(ValueError, match="requires a snapshot"):
        AuditPage(_run_key(), ResultStatus.COMPLETE, "gateway", (), "cursor", None, 1, 2, None, ())
