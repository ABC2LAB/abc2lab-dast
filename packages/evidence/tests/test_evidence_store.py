"""공개 Evidence 저장/조회의 fingerprint·멱등·의존성·run 격리를 검증한다.

네트워크·DB 없이 인메모리 구현으로 실행한다. 적용 사례: S1-06(의존성 미충족 비교),
S1-13(결과에 원문 없음), 멱등/충돌·run 격리.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from abc2lab_contracts.evidence import (
    ComparisonPayload,
    ComparisonSignals,
    EvidenceReadRequest,
    EvidenceSummary,
    RedactedBundle,
)
from abc2lab_contracts.primitives import (
    AuditLink,
    CheckState,
    ReadContext,
    ReasonCode,
    Ref,
    ResponseClass,
    ResultStatus,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.registration import ComparisonRules
from abc2lab_evidence.adapters.memory_store import InMemoryEvidenceStore

_RUN = RunKey("org-1", "target-1", "env-1", "run-1")
_OTHER_RUN = RunKey("org-1", "target-1", "env-1", "run-2")
_SOURCE = SourceVersion("issuer-1", "redaction-1", 1)
_RULES = ComparisonRules(_SOURCE, "normalizer-1", "oracle-1", "canary-1")
_CONTEXT = ReadContext("caller-1", "authorization-1")


def _now() -> datetime:
    return datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC)


def _store() -> InMemoryEvidenceStore:
    return InMemoryEvidenceStore(_now)


def _summary(
    evidence_ref: str = "evidence-owner",
    *,
    run_key: RunKey = _RUN,
    http_status: int = 200,
) -> EvidenceSummary:
    return EvidenceSummary(
        run_key=run_key,
        evidence_ref=evidence_ref,
        attempt_ref="attempt-1",
        operation_ref="operation-1",
        resource_ref="resource-1",
        account_ref="account-a",
        session_generation=1,
        identity_ref="identity-a",
        response_class=ResponseClass.NORMAL,
        http_status=http_status,
        observed_at=datetime(2026, 10, 21, tzinfo=UTC),
        redaction_version=_SOURCE,
        source_event=AuditLink("evidence", f"event-{evidence_ref}"),
        request_recipe=None,
        recipe_reason_codes=(ReasonCode.RECIPE_UNSUPPORTED,),
    )


def _signals() -> ComparisonSignals:
    return ComparisonSignals(
        same_resource=CheckState.YES,
        distinct_verified_subjects=CheckState.YES,
        owner_normal_data=CheckState.YES,
        cross_normal_data=CheckState.YES,
        nontrivial_data_match=CheckState.YES,
        reflection_excluded=CheckState.YES,
        template_excluded=CheckState.YES,
    )


def _payload(
    owner: str = "evidence-owner", cross: str = "evidence-cross", *, run_key: RunKey = _RUN
) -> ComparisonPayload:
    return ComparisonPayload(
        run_key=run_key,
        comparison_ref="comparison-1",
        case_ref="case-1",
        resource_ref="resource-1",
        operation_ref="operation-1",
        owner_evidence_ref=owner,
        cross_evidence_ref=cross,
        owner_identity_ref="identity-a",
        evaluated_identity_ref="identity-b",
        signals=_signals(),
        rules=_RULES,
    )


def _bundle(
    summaries: tuple[EvidenceSummary, ...],
    comparison: ComparisonPayload | None = None,
    *,
    submission_ref: Ref = "submission-1",
) -> RedactedBundle:
    return RedactedBundle(_RUN, submission_ref, summaries, comparison, _SOURCE)


@pytest.mark.asyncio
async def test_store_and_read_evidence_summary() -> None:
    store = _store()
    outcome = await store.store_evidence(_bundle((_summary(),)))
    assert outcome.status is ResultStatus.COMPLETE
    assert len(outcome.receipts) == 1
    assert len(outcome.receipts[0].content_fingerprint) == 64

    read = await store.evidence_read_summary(
        EvidenceReadRequest(_RUN, _CONTEXT, ("evidence-owner",), ())
    )
    assert read.status is ResultStatus.COMPLETE
    assert tuple(item.evidence_ref for item in read.evidence) == ("evidence-owner",)
    assert read.comparisons == ()


@pytest.mark.asyncio
async def test_store_is_idempotent_for_same_content() -> None:
    store = _store()
    first = await store.store_evidence(_bundle((_summary(),)))
    second = await store.store_evidence(_bundle((_summary(),)))
    assert second.status is ResultStatus.COMPLETE
    assert second.receipts[0].content_fingerprint == first.receipts[0].content_fingerprint


@pytest.mark.asyncio
async def test_store_conflicts_on_changed_content_for_same_ref() -> None:
    store = _store()
    await store.store_evidence(_bundle((_summary(http_status=200),)))
    outcome = await store.store_evidence(_bundle((_summary(http_status=500),)))
    assert outcome.status is ResultStatus.FAILED
    assert outcome.receipts == ()
    assert ReasonCode.IDEMPOTENCY_CONFLICT in outcome.reason_codes


@pytest.mark.asyncio
async def test_comparison_without_dependencies_is_incomplete() -> None:
    store = _store()
    outcome = await store.store_evidence(_bundle((), _payload()))
    assert outcome.status is ResultStatus.FAILED
    assert ReasonCode.COMPARISON_INCOMPLETE in outcome.reason_codes


@pytest.mark.asyncio
async def test_store_bundle_with_comparison_and_read_stored_comparison() -> None:
    store = _store()
    summaries = (_summary("evidence-owner"), _summary("evidence-cross"))
    outcome = await store.store_evidence(_bundle(summaries, _payload()))
    assert outcome.status is ResultStatus.COMPLETE
    assert len(outcome.receipts) == 3

    read = await store.evidence_read_summary(
        EvidenceReadRequest(_RUN, _CONTEXT, (), ("comparison-1",))
    )
    assert read.status is ResultStatus.COMPLETE
    assert len(read.comparisons) == 1
    # StoredComparison은 기준·교차 근거와 비교 receipt 3개가 모두 있어야 한다.
    assert len(read.comparisons[0].receipts) == 3


@pytest.mark.asyncio
async def test_read_missing_ref_is_not_found() -> None:
    store = _store()
    read = await store.evidence_read_summary(
        EvidenceReadRequest(_RUN, _CONTEXT, ("evidence-missing",), ())
    )
    assert read.status is ResultStatus.FAILED
    assert read.evidence == ()
    assert ReasonCode.NOT_FOUND in read.reason_codes


@pytest.mark.asyncio
async def test_read_isolates_other_run() -> None:
    store = _store()
    await store.store_evidence(_bundle((_summary(),)))
    # 같은 evidence_ref라도 다른 run으로는 조회되지 않는다(멀티테넌트 격리).
    read = await store.evidence_read_summary(
        EvidenceReadRequest(_OTHER_RUN, _CONTEXT, ("evidence-owner",), ())
    )
    assert read.evidence == ()
    assert ReasonCode.NOT_FOUND in read.reason_codes
