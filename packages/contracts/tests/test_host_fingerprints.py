"""Frozen canonical bytes and digest vectors for Host run.v1/task.v1 records."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from abc2lab_contracts.audit import AuditEventKind, AuditReceipt, AuditRecordBinding
from abc2lab_contracts.fingerprint import (
    _registered_record_envelope,
    canonical_json_bytes,
    run_fingerprint,
    task_fingerprint,
)
from abc2lab_contracts.host import RunState, TaskKind, TaskState
from abc2lab_contracts.host_audit import RunAuditRecord, TaskAuditRecord
from abc2lab_contracts.primitives import (
    AttemptSummary,
    AuditLink,
    ReasonCode,
    RunKey,
    SendStatus,
)

_VECTORS = {
    item["id"]: item
    for item in json.loads(
        (
            Path(__file__).resolve().parents[3] / "docs/examples/host-fingerprint-vectors.json"
        ).read_text(encoding="utf-8")
    )["vectors"]
}


def _time() -> datetime:
    return datetime(2026, 10, 22, 8, 0, tzinfo=UTC)


def _run_key() -> RunKey:
    return RunKey("org-demo", "target-demo", "env-demo", "run-demo")


def _run_record() -> RunAuditRecord:
    return RunAuditRecord(
        _run_key(), "registration-demo", "submission-demo", 1, RunState.QUEUED, _time(), _time(), ()
    )


def _task_record() -> TaskAuditRecord:
    attempt = AttemptSummary(
        _run_key(),
        "request-demo",
        "attempt-demo",
        SendStatus.UNKNOWN,
        (AuditLink("gateway", "event-demo"),),
        (ReasonCode.AUDIT_GAP,),
    )
    return TaskAuditRecord(
        _run_key(),
        "task-demo",
        2,
        TaskKind.COMPARE,
        "case-demo",
        TaskState.PARTIAL,
        (attempt,),
        _time(),
        _time(),
        (ReasonCode.AUDIT_GAP,),
    )


@pytest.mark.parametrize("vector_id", ["run-audit-v1", "task-audit-v1"])
def test_golden_bytes_and_hash(vector_id: str) -> None:
    record: RunAuditRecord | TaskAuditRecord
    if vector_id == "run-audit-v1":
        record = _run_record()
        digest = run_fingerprint(record)
    elif vector_id == "task-audit-v1":
        record = _task_record()
        digest = task_fingerprint(record)
    else:
        raise AssertionError(f"unexpected vector: {vector_id}")
    vector = _VECTORS[vector_id]
    assert vector["codec_version"] == "canonical-json.v1"
    assert canonical_json_bytes(_registered_record_envelope(record)) == vector[
        "canonical_utf8"
    ].encode("utf-8")
    assert digest == vector["sha256"]


def test_run_business_revision_and_scope_change_digest() -> None:
    record = _run_record()
    assert run_fingerprint(replace(record, revision=2)) != run_fingerprint(record)
    assert run_fingerprint(replace(record, registration_ref="other")) != run_fingerprint(record)
    assert run_fingerprint(replace(record, state=RunState.RUNNING)) != run_fingerprint(record)
    offset = timezone(timedelta(hours=9))
    assert run_fingerprint(
        replace(record, created_at=record.created_at.astimezone(offset))
    ) == run_fingerprint(record)


def test_task_metadata_change_creates_new_digest() -> None:
    record = _task_record()
    assert task_fingerprint(replace(record, revision=3)) != task_fingerprint(record)
    assert task_fingerprint(replace(record, state=TaskState.FAILED)) != task_fingerprint(record)
    attempt = record.attempt_summaries[0]
    modified = replace(attempt, audit_links=(AuditLink("gateway", "other-event"),))
    assert task_fingerprint(replace(record, attempt_summaries=(modified,))) != task_fingerprint(
        record
    )
    assert task_fingerprint(
        replace(record, reason_codes=(ReasonCode.CANCELLED,))
    ) != task_fingerprint(record)


def test_fingerprint_rejects_unregistered_and_mutated_records() -> None:
    with pytest.raises(TypeError):
        run_fingerprint(_task_record())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        task_fingerprint(_run_record())  # type: ignore[arg-type]
    run = _run_record()
    object.__setattr__(run, "revision", True)
    with pytest.raises(TypeError):
        run_fingerprint(run)
    task = _task_record()
    object.__setattr__(task.attempt_summaries[0], "reason_codes", [ReasonCode.AUDIT_GAP])
    with pytest.raises(TypeError):
        task_fingerprint(task)


def test_fingerprints_require_exact_registered_types_and_complete_fields() -> None:
    class RunSubclass(RunAuditRecord):
        pass

    class TaskSubclass(TaskAuditRecord):
        pass

    run_subclass = object.__new__(RunSubclass)
    task_subclass = object.__new__(TaskSubclass)
    with pytest.raises(TypeError):
        run_fingerprint(run_subclass)
    with pytest.raises(TypeError):
        task_fingerprint(task_subclass)
    with pytest.raises(TypeError):
        run_fingerprint({"run_key": _run_key()})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        task_fingerprint({"task_ref": "task-demo"})  # type: ignore[arg-type]

    broken = object.__new__(RunAuditRecord)
    fields = (
        "run_key",
        "registration_ref",
        "submission_ref",
        "state",
        "created_at",
        "updated_at",
        "reason_codes",
    )
    for field in fields:
        object.__setattr__(broken, field, getattr(_run_record(), field))
    with pytest.raises((TypeError, AttributeError)):
        run_fingerprint(broken)


def test_run_fingerprint_changes_for_each_business_field() -> None:
    record = _run_record()
    changed = (
        replace(record, run_key=RunKey("other-org", "target-demo", "env-demo", "run-demo")),
        replace(record, registration_ref="registration-other"),
        replace(record, submission_ref="submission-other"),
        replace(record, revision=2),
        replace(record, state=RunState.RUNNING),
        replace(record, created_at=record.created_at - timedelta(seconds=1)),
        replace(record, updated_at=record.updated_at + timedelta(seconds=1)),
        replace(record, reason_codes=(ReasonCode.AUDIT_GAP,)),
    )
    assert all(run_fingerprint(item) != run_fingerprint(record) for item in changed)


def test_task_fingerprint_changes_for_each_business_field_and_nested_attempt_field() -> None:
    record = _task_record()
    attempt = record.attempt_summaries[0]
    other_run = RunKey("other-org", "target-demo", "env-demo", "run-demo")
    changed = (
        replace(
            record,
            run_key=other_run,
            attempt_summaries=(replace(attempt, run_key=other_run),),
        ),
        replace(record, task_ref="task-other"),
        replace(record, revision=3),
        replace(record, kind=TaskKind.JUDGE),
        replace(record, case_ref="case-other"),
        replace(record, state=TaskState.FAILED),
        replace(record, created_at=record.created_at - timedelta(seconds=1)),
        replace(record, updated_at=record.updated_at + timedelta(seconds=1)),
        replace(record, reason_codes=(ReasonCode.CANCELLED,)),
        replace(record, attempt_summaries=(replace(attempt, request_ref="request-other"),)),
        replace(record, attempt_summaries=(replace(attempt, attempt_ref="attempt-other"),)),
        replace(record, attempt_summaries=(replace(attempt, send_status=SendStatus.SENT),)),
        replace(
            record,
            attempt_summaries=(replace(attempt, audit_links=(AuditLink("other", "event"),)),),
        ),
        replace(
            record,
            attempt_summaries=(replace(attempt, reason_codes=(ReasonCode.CANCELLED,)),),
        ),
    )
    assert all(task_fingerprint(item) != task_fingerprint(record) for item in changed)


def test_host_vectors_pin_record_kind_and_schema_version_without_changing_other_vectors() -> None:
    assert _VECTORS["run-audit-v1"]["record_kind"] == "run"
    assert _VECTORS["run-audit-v1"]["schema_version"] == "run.v1"
    assert _VECTORS["task-audit-v1"]["record_kind"] == "task"
    assert _VECTORS["task-audit-v1"]["schema_version"] == "task.v1"
    task = _task_record()
    object.__setattr__(task, "reason_codes", (ReasonCode.QUEUE_FULL, ReasonCode.AUDIT_GAP))
    with pytest.raises(ValueError, match="normalized"):
        task_fingerprint(task)
    task = _task_record()
    object.__setattr__(task, "state", "partial")
    with pytest.raises(TypeError):
        task_fingerprint(task)


@pytest.mark.parametrize("kind", (AuditEventKind.RUN, AuditEventKind.TASK))
def test_host_record_binding_uses_business_revision_not_journal_sequence(
    kind: AuditEventKind,
) -> None:
    record: RunAuditRecord | TaskAuditRecord
    if kind is AuditEventKind.RUN:
        record = _run_record()
        record_ref = record.run_key.run_ref
        digest = run_fingerprint(record)
    else:
        record = _task_record()
        record_ref = record.task_ref
        digest = task_fingerprint(record)
    binding = AuditRecordBinding(kind, record_ref, record.revision, digest, None, None, None)
    receipt = AuditReceipt(record.run_key, "host", "host-event", 17, binding, _time())
    assert receipt.binding.event_kind is kind
    assert receipt.binding.record_ref == record_ref
    assert receipt.binding.record_revision == record.revision
    assert receipt.binding.record_fingerprint == digest
    assert receipt.sequence != receipt.binding.record_revision
    assert replace(receipt, sequence=18).binding == binding
