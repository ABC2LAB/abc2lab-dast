"""검증된 정책·신원·비교가 같은 case·자원·동작·주체를 가리키는지 대조한다.

어긋나면 정상적인 근거 부족이 아니라 출처 불일치이므로 `CallFailure`로 올린다(C4-B 계약 §2
"run/case/resource/subject 불일치 → FAILED"). 확인할 짝이 없는 값(미공급 신원 등)은 대조하지 않고
판정 단계의 정상 UNDECIDABLE 경로로 남긴다.
"""

from __future__ import annotations

from dataclasses import dataclass

from abc2lab_contracts.primitives import CheckState, ReasonCode, Ref
from abc2lab_contracts.registration import ComparisonRules, ExpectedAccessPolicySnapshot
from abc2lab_contracts.session import IdentityResult

from abc2lab_judge.adapters.attestation import LoadedComparison, source_mismatch


@dataclass(frozen=True, slots=True)
class CaseRecords:
    """대조할 한 case의 검증된 레코드 묶음."""

    case_ref: Ref
    policy: ExpectedAccessPolicySnapshot | None
    owner_identity: IdentityResult | None
    evaluated_identity: IdentityResult | None
    comparison: LoadedComparison | None
    expected_rules: ComparisonRules


def check_correspondence(records: CaseRecords) -> None:
    """정책·신원·비교의 case·자원·동작·주체 대응을 확인한다. 어긋나면 `CallFailure`."""
    _check_policy_subjects(records)
    comparison = records.comparison
    if comparison is None:
        return
    _check_comparison_scope(records, comparison)
    _check_identity_links(records, comparison)
    _check_distinct_signal(records, comparison)


def _check_policy_subjects(records: CaseRecords) -> None:
    policy = records.policy
    if policy is None:
        return
    pairs = (
        (records.owner_identity, policy.owner_subject_ref),
        (records.evaluated_identity, policy.evaluated_subject_ref),
    )
    for identity, policy_subject in pairs:
        if identity is not None and identity.subject_ref is not None:
            if identity.subject_ref != policy_subject:
                raise source_mismatch(
                    "identity subject differs from policy", ReasonCode.IDENTITY_MISMATCH
                )


def _check_comparison_scope(records: CaseRecords, comparison: LoadedComparison) -> None:
    payload = comparison.payload
    if payload.case_ref != records.case_ref:
        raise source_mismatch("comparison belongs to another case")
    if payload.rules != records.expected_rules:
        raise source_mismatch("comparison used unregistered rules")
    for summary in (comparison.owner, comparison.cross):
        if summary.operation_ref != payload.operation_ref or (
            summary.resource_ref != payload.resource_ref
        ):
            raise source_mismatch("evidence operation/resource differs from comparison")
    policy = records.policy
    if policy is not None and (
        policy.resource_ref != payload.resource_ref or policy.operation_ref != payload.operation_ref
    ):
        raise source_mismatch("policy resource/operation differs from comparison")


def _check_identity_links(records: CaseRecords, comparison: LoadedComparison) -> None:
    payload = comparison.payload
    links = (
        (comparison.owner, payload.owner_identity_ref, records.owner_identity),
        (comparison.cross, payload.evaluated_identity_ref, records.evaluated_identity),
    )
    for summary, identity_ref, identity in links:
        if summary.identity_ref != identity_ref:
            raise source_mismatch(
                "evidence identity differs from comparison", ReasonCode.IDENTITY_MISMATCH
            )
        if identity is None:
            continue
        if (
            identity.identity_ref != identity_ref
            or identity.account_ref != summary.account_ref
            or identity.generation != summary.session_generation
        ):
            raise source_mismatch(
                "identity differs from evidence session", ReasonCode.IDENTITY_MISMATCH
            )


def _check_distinct_signal(records: CaseRecords, comparison: LoadedComparison) -> None:
    owner, evaluated = records.owner_identity, records.evaluated_identity
    if owner is None or evaluated is None or owner.subject_ref is None:
        return
    if evaluated.subject_ref is None:
        return
    same_subject = owner.subject_ref == evaluated.subject_ref
    signal = comparison.payload.signals.distinct_verified_subjects
    if (same_subject and signal is CheckState.YES) or (
        not same_subject and signal is CheckState.NO
    ):
        raise source_mismatch("comparison subject signal contradicts verified identities")
