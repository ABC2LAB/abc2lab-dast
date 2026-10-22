"""C4-B Judge values and its separately injected registration-read boundary.

Constructors check immutable shapes and local consistency. They do not authorize
callers, authenticate policy/case provenance or prove a producer journal commit.
"""

from dataclasses import dataclass

from abc2lab_contracts._validation import ContractRecord
from abc2lab_contracts.primitives import ReadContext, ReasonCode, Ref, ResultStatus, RunKey
from abc2lab_contracts.projection import VerdictProjected
from abc2lab_contracts.registration import ExpectedAccessPolicySnapshot
from abc2lab_contracts.session import IdentityResult
from abc2lab_contracts.verdict import Verdict


@dataclass(frozen=True, slots=True)
class JudgeRequest(ContractRecord):
    """Request a case verdict with optional evidence and a policy consistency hint."""

    run_key: RunKey
    context: ReadContext
    case_ref: Ref
    submission_ref: Ref
    expected_policy: ExpectedAccessPolicySnapshot | None
    owner_identity: IdentityResult | None
    evaluated_identity: IdentityResult | None
    comparison_ref: Ref | None

    def _validate_invariants(self) -> None:
        _validate_policy_scope(self.run_key, self.expected_policy)
        for identity in (self.owner_identity, self.evaluated_identity):
            if identity is not None and identity.run_key != self.run_key:
                raise ValueError("Judge identity run mismatch")


@dataclass(frozen=True, slots=True)
class JudgeResult(ContractRecord):
    """Publish a verdict and matching source projection, or a reasoned call failure."""

    run_key: RunKey
    status: ResultStatus
    verdict: Verdict | None
    projection_event: VerdictProjected | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.PARTIAL:
            raise ValueError("Judge result does not support partial")
        if self.status is ResultStatus.COMPLETE:
            if self.verdict is None or self.projection_event is None:
                raise ValueError("complete Judge result requires verdict and projection")
            if self.reason_codes:
                raise ValueError("complete Judge result cannot contain call failure reasons")
            if (
                self.verdict.run_key != self.run_key
                or self.projection_event.run_key != self.run_key
                or self.projection_event.verdict != self.verdict
            ):
                raise ValueError("Judge result run or verdict/projection mismatch")
        else:
            if self.verdict is not None or self.projection_event is not None:
                raise ValueError("failed Judge result cannot publish verdict or projection")
            if not self.reason_codes:
                raise ValueError("failed Judge result requires a reason")


@dataclass(frozen=True, slots=True)
class JudgePolicyReadRequest(ContractRecord):
    """Resolve a registered case policy after verifying an optional supplied hint."""

    run_key: RunKey
    context: ReadContext
    case_ref: Ref
    expected_policy: ExpectedAccessPolicySnapshot | None

    def _validate_invariants(self) -> None:
        _validate_policy_scope(self.run_key, self.expected_policy)


@dataclass(frozen=True, slots=True)
class JudgePolicyReadResult(ContractRecord):
    """Distinguish a case's canonical policy, known absence and failed source reads."""

    run_key: RunKey
    case_ref: Ref
    status: ResultStatus
    expected_policy: ExpectedAccessPolicySnapshot | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.PARTIAL:
            raise ValueError("Judge policy read does not support partial")
        if self.status is ResultStatus.FAILED:
            if self.expected_policy is not None:
                raise ValueError("failed Judge policy read cannot publish a policy")
            if not self.reason_codes:
                raise ValueError("failed Judge policy read requires a reason")
        elif self.expected_policy is None:
            if ReasonCode.EXPECTED_ACCESS_POLICY_MISSING not in self.reason_codes:
                raise ValueError("known policy absence requires expected_access_policy_missing")
        else:
            _validate_policy_scope(self.run_key, self.expected_policy)
            if self.reason_codes:
                raise ValueError("complete Judge policy read with a policy cannot contain reasons")


def _validate_policy_scope(run_key: RunKey, policy: ExpectedAccessPolicySnapshot | None) -> None:
    if policy is not None and (
        policy.target_ref != run_key.target_ref or policy.environment_ref != run_key.environment_ref
    ):
        raise ValueError("Judge policy target/environment mismatch")
