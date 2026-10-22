"""공개 Evidence 저장 서비스의 인메모리 구현(슬라이스·독립 테스트용).

실제 내구성·복구를 증명하지 않는다. 원문·캡처 핸들·HMAC 키를 받지 않고 민감값 제거
자료만 저장한다. content_fingerprint는 공유 C1 codec으로 계산한다(core.fingerprinting).
비교는 기준·교차 근거가 모두 저장된 뒤에만 저장하며, 조회는 run 범위로 격리한다(§7).
"""

from __future__ import annotations

from collections.abc import Callable

from abc2lab_contracts.evidence import (
    ArtifactKind,
    ComparisonPayload,
    EvidenceReadRequest,
    EvidenceReadResult,
    EvidenceSummary,
    RedactedBundle,
    StoredComparison,
    StoreOutcome,
    StoreReceipt,
)
from abc2lab_contracts.fingerprint import comparison_fingerprint, evidence_fingerprint
from abc2lab_contracts.primitives import ReasonCode, Ref, ResultStatus, RunKey, UtcTime


def _status(stored: int, requested: int) -> ResultStatus:
    """요청 대비 저장/조회 성공 수로 완성도를 정한다."""
    if requested == 0 or stored == requested:
        return ResultStatus.COMPLETE
    if stored == 0:
        return ResultStatus.FAILED
    return ResultStatus.PARTIAL


class InMemoryEvidenceStore:
    """민감값 제거 근거·비교를 메모리에 불변 저장하는 공개 Evidence 서비스다."""

    def __init__(self, now: Callable[[], UtcTime]) -> None:
        """감사 시각 공급기를 주입받는다. 외부 I/O·DB는 쓰지 않는다."""
        self._now = now
        self._evidence: dict[str, tuple[EvidenceSummary, StoreReceipt]] = {}
        self._comparisons: dict[str, tuple[ComparisonPayload, StoreReceipt]] = {}

    async def store_evidence(self, request: RedactedBundle) -> StoreOutcome:
        """근거와 (의존성이 충족된) 비교를 저장하고 영수증·사유를 보존한다."""
        receipts: list[StoreReceipt] = []
        reason_codes: list[ReasonCode] = []
        requested = len(request.evidence) + (1 if request.comparison is not None else 0)
        for summary in request.evidence:
            receipt = self._store_summary(request, summary, reason_codes)
            if receipt is not None:
                receipts.append(receipt)
        if request.comparison is not None:
            receipt = self._store_comparison(request, request.comparison, reason_codes)
            if receipt is not None:
                receipts.append(receipt)
        status = _status(len(receipts), requested)
        return StoreOutcome(request.run_key, status, tuple(receipts), tuple(reason_codes))

    async def evidence_read_summary(self, request: EvidenceReadRequest) -> EvidenceReadResult:
        """run 범위로 허용된 근거·비교만 반환하고 누락은 not_found로 남긴다."""
        evidence: list[EvidenceSummary] = []
        comparisons: list[StoredComparison] = []
        reason_codes: list[ReasonCode] = []
        requested = len(request.evidence_refs) + len(request.comparison_refs)
        found = 0
        for ref in request.evidence_refs:
            stored = self._evidence.get(ref)
            if stored is not None and stored[0].run_key == request.run_key:
                evidence.append(stored[0])
                found += 1
            else:
                reason_codes.append(ReasonCode.NOT_FOUND)
        for ref in request.comparison_refs:
            comparison = self._stored_comparison(ref, request.run_key)
            if comparison is not None:
                comparisons.append(comparison)
                found += 1
            else:
                reason_codes.append(ReasonCode.NOT_FOUND)
        status = _status(found, requested)
        return EvidenceReadResult(
            request.run_key, status, tuple(evidence), tuple(comparisons), tuple(reason_codes)
        )

    def _store_summary(
        self, bundle: RedactedBundle, summary: EvidenceSummary, reason_codes: list[ReasonCode]
    ) -> StoreReceipt | None:
        fingerprint = evidence_fingerprint(summary)
        existing = self._evidence.get(summary.evidence_ref)
        if existing is not None:
            if existing[1].content_fingerprint == fingerprint:
                return existing[1]
            reason_codes.append(ReasonCode.IDEMPOTENCY_CONFLICT)
            return None
        receipt = StoreReceipt(
            run_key=bundle.run_key,
            submission_ref=bundle.submission_ref,
            artifact_ref=summary.evidence_ref,
            artifact_kind=ArtifactKind.EVIDENCE,
            source=bundle.source,
            committed_at=self._now(),
            content_fingerprint=fingerprint,
        )
        self._evidence[summary.evidence_ref] = (summary, receipt)
        return receipt

    def _store_comparison(
        self, bundle: RedactedBundle, comparison: ComparisonPayload, reason_codes: list[ReasonCode]
    ) -> StoreReceipt | None:
        if (
            comparison.owner_evidence_ref not in self._evidence
            or comparison.cross_evidence_ref not in self._evidence
        ):
            reason_codes.append(ReasonCode.COMPARISON_INCOMPLETE)
            return None
        fingerprint = comparison_fingerprint(comparison)
        existing = self._comparisons.get(comparison.comparison_ref)
        if existing is not None:
            if existing[1].content_fingerprint == fingerprint:
                return existing[1]
            reason_codes.append(ReasonCode.IDEMPOTENCY_CONFLICT)
            return None
        receipt = StoreReceipt(
            run_key=bundle.run_key,
            submission_ref=bundle.submission_ref,
            artifact_ref=comparison.comparison_ref,
            artifact_kind=ArtifactKind.COMPARISON,
            source=bundle.source,
            committed_at=self._now(),
            content_fingerprint=fingerprint,
        )
        self._comparisons[comparison.comparison_ref] = (comparison, receipt)
        return receipt

    def _stored_comparison(self, comparison_ref: Ref, run_key: RunKey) -> StoredComparison | None:
        item = self._comparisons.get(comparison_ref)
        if item is None or item[0].run_key != run_key:
            return None
        payload, comparison_receipt = item
        owner = self._evidence.get(payload.owner_evidence_ref)
        cross = self._evidence.get(payload.cross_evidence_ref)
        if owner is None or cross is None:
            return None
        return StoredComparison(payload, (owner[1], cross[1], comparison_receipt))
