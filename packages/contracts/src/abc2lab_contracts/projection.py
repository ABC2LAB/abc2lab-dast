"""Closed producer-event union and local payload/receipt consistency checks.

These checks do not prove a producer commit or authorize graph writes. Knowledge
must use its injected producer verifiers and Evidence reader independently.
"""

from __future__ import annotations

from dataclasses import dataclass

from abc2lab_contracts._validation import ContractRecord
from abc2lab_contracts.audit import AuditEventKind, AuditReceipt
from abc2lab_contracts.evidence import ComparisonProjected
from abc2lab_contracts.observation import Observation
from abc2lab_contracts.primitives import AuditLink, Ref, Revision, RunKey
from abc2lab_contracts.registration import ExpectedAccessPolicySnapshot
from abc2lab_contracts.verdict import Verdict


@dataclass(frozen=True, slots=True)
class ObservationProjected(ContractRecord):
    """Bind a WebDiag observation to its original immutable audit receipt."""

    kind: AuditEventKind
    event_ref: Ref
    run_key: RunKey
    producer: Ref
    source_revision: Revision
    source_receipt: AuditReceipt
    observation: Observation

    def _validate_invariants(self) -> None:
        if self.kind is not AuditEventKind.OBSERVATION:
            raise ValueError("projection kind must be observation")
        if self.observation.run_key != self.run_key or self.observation.source_event != AuditLink(
            self.producer, self.event_ref
        ):
            raise ValueError("observation projection source/run mismatch")
        from abc2lab_contracts.fingerprint import observation_fingerprint

        _validate_binding(
            self, self.observation.observation_ref, 1, observation_fingerprint(self.observation)
        )


@dataclass(frozen=True, slots=True)
class VerdictProjected(ContractRecord):
    """Preserve the Judge verdict revision, source event and committed digest."""

    kind: AuditEventKind
    event_ref: Ref
    run_key: RunKey
    producer: Ref
    source_revision: Revision
    source_receipt: AuditReceipt
    verdict: Verdict

    def _validate_invariants(self) -> None:
        if self.kind is not AuditEventKind.VERDICT:
            raise ValueError("projection kind must be verdict")
        if self.verdict.run_key != self.run_key or self.verdict.source_event != AuditLink(
            self.producer, self.event_ref
        ):
            raise ValueError("verdict projection source/run mismatch")
        from abc2lab_contracts.fingerprint import verdict_fingerprint

        _validate_binding(
            self, self.verdict.verdict_ref, self.verdict.revision, verdict_fingerprint(self.verdict)
        )


@dataclass(frozen=True, slots=True)
class PolicyRegistered(ContractRecord):
    """Carry a committed expected-policy registration without granting authority."""

    kind: AuditEventKind
    event_ref: Ref
    run_key: RunKey
    producer: Ref
    source_revision: Revision
    source_receipt: AuditReceipt
    policy: ExpectedAccessPolicySnapshot

    def _validate_invariants(self) -> None:
        if self.kind is not AuditEventKind.EXPECTED_POLICY:
            raise ValueError("projection kind must be expected_policy")
        if (
            self.policy.target_ref != self.run_key.target_ref
            or self.policy.environment_ref != self.run_key.environment_ref
        ):
            raise ValueError("policy registration target/environment mismatch")
        from abc2lab_contracts.fingerprint import expected_policy_fingerprint

        _validate_binding(
            self,
            self.policy.policy_ref,
            self.policy.source.revision,
            expected_policy_fingerprint(self.policy),
        )


ProjectionEvent = ObservationProjected | ComparisonProjected | VerdictProjected | PolicyRegistered


def _validate_binding(
    event: ObservationProjected | VerdictProjected | PolicyRegistered,
    record_ref: Ref,
    record_revision: Revision,
    fingerprint: str,
) -> None:
    receipt = event.source_receipt
    if (
        receipt.run_key != event.run_key
        or receipt.event_ref != event.event_ref
        or receipt.producer != event.producer
        or event.source_revision != record_revision
        or receipt.binding.event_kind is not event.kind
        or receipt.binding.record_ref != record_ref
        or receipt.binding.record_revision != record_revision
        or receipt.binding.record_fingerprint != fingerprint
    ):
        raise ValueError("projection audit binding mismatch")
