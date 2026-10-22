"""judge 어댑터 테스트의 공용 fixture. 네트워크·DB 없이 만든다."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from abc2lab_contracts.primitives import RunKey, SourceVersion
from abc2lab_judge.adapters import InMemoryVerdictJournal, VerdictContext, VerdictPublisher
from abc2lab_judge.core.model import CheckState, JudgeReason, OracleVerdict, VerdictValue


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def run_key() -> RunKey:
    return RunKey(
        organization_ref="org-1", target_ref="target-1", environment_ref="env-1", run_ref="run-1"
    )


@pytest.fixture
def oracle_version() -> SourceVersion:
    return SourceVersion(issuer="judge", source_ref="idor-oracle", revision=1)


@pytest.fixture
def confirmed_oracle() -> OracleVerdict:
    """셋 다 YES인 CONFIRMED 판정. 사유는 전부 YES 근거라 wire에서 빠진다."""
    return OracleVerdict(
        value=VerdictValue.CONFIRMED,
        policy_check=CheckState.YES,
        identity_check=CheckState.YES,
        data_check=CheckState.YES,
        reason_codes=(
            JudgeReason.POLICY_DENY_RESOLVED,
            JudgeReason.SUBJECTS_DISTINCT_VERIFIED,
            JudgeReason.DATA_NONTRIVIAL_MATCH,
        ),
    )


@pytest.fixture
def undecidable_mapped_oracle() -> OracleVerdict:
    """정책 미등록(매핑되는 사유)으로 UNDECIDABLE. wire 사유가 하나 남아 발행 가능."""
    return OracleVerdict(
        value=VerdictValue.UNDECIDABLE,
        policy_check=CheckState.UNKNOWN,
        identity_check=CheckState.YES,
        data_check=CheckState.YES,
        reason_codes=(
            JudgeReason.EXPECTED_ACCESS_POLICY_MISSING,
            JudgeReason.SUBJECTS_DISTINCT_VERIFIED,
            JudgeReason.DATA_NONTRIVIAL_MATCH,
        ),
    )


@pytest.fixture
def undecidable_unmapped_oracle() -> OracleVerdict:
    """데이터 검증 불가로 UNDECIDABLE. 유일한 사유 DATA_UNVERIFIABLE가 미대응이라 발행 불가."""
    return OracleVerdict(
        value=VerdictValue.UNDECIDABLE,
        policy_check=CheckState.YES,
        identity_check=CheckState.YES,
        data_check=CheckState.UNKNOWN,
        reason_codes=(
            JudgeReason.POLICY_DENY_RESOLVED,
            JudgeReason.SUBJECTS_DISTINCT_VERIFIED,
            JudgeReason.DATA_UNVERIFIABLE,
        ),
    )


@pytest.fixture
def confirmed_context(run_key: RunKey, oracle_version: SourceVersion) -> VerdictContext:
    """CONFIRMED에 필요한 정책 출처·비교·근거 ref를 갖춘 맥락."""
    return VerdictContext(
        run_key=run_key,
        verdict_ref="verdict-1",
        revision=1,
        case_ref="case-1",
        oracle_version=oracle_version,
        expected_policy_source=SourceVersion(issuer="reg", source_ref="eap", revision=3),
        comparison_ref="comparison-1",
        evidence_refs=("evidence-1",),
    )


@pytest.fixture
def undetermined_context(run_key: RunKey, oracle_version: SourceVersion) -> VerdictContext:
    """미확정 판정용 맥락. 정책·비교·근거 ref는 없어도 된다."""
    return VerdictContext(
        run_key=run_key,
        verdict_ref="verdict-1",
        revision=1,
        case_ref="case-1",
        oracle_version=oracle_version,
    )


@pytest.fixture
def journal(now: datetime) -> InMemoryVerdictJournal:
    return InMemoryVerdictJournal("judge", clock=lambda: now)


@pytest.fixture
def publisher(journal: InMemoryVerdictJournal) -> VerdictPublisher:
    return VerdictPublisher(
        journal, "judge", event_ref_factory=lambda producer, run: f"{producer}:{run.run_ref}:fixed"
    )
