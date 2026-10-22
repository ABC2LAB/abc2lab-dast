"""C4 closed projection event and receipt binding tests."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from abc2lab_contracts.audit import AuditEventKind, AuditReceipt, AuditRecordBinding
from abc2lab_contracts.capture import RawResponse
from abc2lab_contracts.evidence import (
    ArtifactKind,
    ComparisonPayload,
    ComparisonProjected,
    ComparisonSignals,
    StoredComparison,
    StoreReceipt,
)
from abc2lab_contracts.fingerprint import (
    comparison_fingerprint,
    expected_policy_fingerprint,
    observation_fingerprint,
    verdict_fingerprint,
)
from abc2lab_contracts.knowledge import CaseReadResult, ProjectionSubmission
from abc2lab_contracts.observation import Observation
from abc2lab_contracts.primitives import (
    AuditLink,
    CheckState,
    ReasonCode,
    ResponseClass,
    ResultStatus,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.projection import (
    ObservationProjected,
    PolicyRegistered,
    ProjectionEvent,
    VerdictProjected,
)
from abc2lab_contracts.registration import (
    ComparisonRules,
    ExpectedAccess,
    ExpectedAccessPolicySnapshot,
    ResolutionState,
)
from abc2lab_contracts.verdict import Verdict, VerdictValue

STAMP = datetime(2026, 10, 21, tzinfo=UTC)


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
        AuditLink("webdiag", "observation-event"),
        STAMP,
        (),
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
        CheckState.UNKNOWN,
        None,
        None,
        (),
        SourceVersion("judge", "oracle", 4),
        AuditLink("judge", "verdict-event"),
        (ReasonCode.POC_VERDICT_UNCONFIRMED,),
    )


def _confirmed_verdict() -> Verdict:
    return Verdict(
        _run(),
        "verdict-confirmed",
        3,
        "case-1",
        VerdictValue.CONFIRMED,
        CheckState.YES,
        CheckState.YES,
        CheckState.YES,
        SourceVersion("registration", "policy", 2),
        "comparison-1",
        ("evidence-owner",),
        SourceVersion("judge", "oracle", 4),
        AuditLink("judge", "confirmed-event"),
        (),
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
        STAMP,
        datetime(2026, 10, 22, tzinfo=UTC),
    )


def _receipt(
    kind: AuditEventKind,
    record_ref: str,
    revision: int,
    digest: str,
    producer: str,
    event_ref: str,
) -> AuditReceipt:
    binding = AuditRecordBinding(kind, record_ref, revision, digest, None, None, None)
    return AuditReceipt(_run(), producer, event_ref, 99, binding, STAMP)


def _observation_event() -> ObservationProjected:
    observation = _observation()
    return ObservationProjected(
        AuditEventKind.OBSERVATION,
        "observation-event",
        _run(),
        "webdiag",
        1,
        _receipt(
            AuditEventKind.OBSERVATION,
            "observation-1",
            1,
            observation_fingerprint(observation),
            "webdiag",
            "observation-event",
        ),
        observation,
    )


def _new_events() -> tuple[ObservationProjected, VerdictProjected, PolicyRegistered]:
    observation_event = _observation_event()
    verdict = _verdict()
    verdict_event = VerdictProjected(
        AuditEventKind.VERDICT,
        "verdict-event",
        _run(),
        "judge",
        2,
        _receipt(
            AuditEventKind.VERDICT,
            "verdict-1",
            2,
            verdict_fingerprint(verdict),
            "judge",
            "verdict-event",
        ),
        verdict,
    )
    policy = _policy()
    policy_event = PolicyRegistered(
        AuditEventKind.EXPECTED_POLICY,
        "policy-event",
        _run(),
        "registration",
        3,
        _receipt(
            AuditEventKind.EXPECTED_POLICY,
            "policy-1",
            3,
            expected_policy_fingerprint(policy),
            "registration",
            "policy-event",
        ),
        policy,
    )
    return observation_event, verdict_event, policy_event


def test_projection_events_bind_payload_kind_run_producer_ref_revision_and_digest() -> None:
    observation_event, verdict_event, policy_event = _new_events()
    assert (
        observation_event.source_receipt.sequence,
        verdict_event.source_revision,
        policy_event.kind,
    ) == (99, 2, AuditEventKind.EXPECTED_POLICY)


def _comparison_event() -> ComparisonProjected:
    source = SourceVersion("registration", "comparison-rules", 1)
    payload = ComparisonPayload(
        _run(),
        "comparison",
        "case-1",
        "resource-1",
        "operation-1",
        "owner-evidence",
        "cross-evidence",
        "owner-identity",
        "cross-identity",
        ComparisonSignals(
            CheckState.YES,
            CheckState.YES,
            CheckState.YES,
            CheckState.YES,
            CheckState.UNKNOWN,
            CheckState.YES,
            CheckState.UNKNOWN,
        ),
        ComparisonRules(source, "normalizer", "oracle", "canary"),
    )
    digest = comparison_fingerprint(payload)
    # Owner/cross contents are absent from StoredComparison; the service verifies them.
    receipts = (
        StoreReceipt(
            _run(), "owner-sub", "owner-evidence", ArtifactKind.EVIDENCE, source, STAMP, "a" * 64
        ),
        StoreReceipt(
            _run(), "cross-sub", "cross-evidence", ArtifactKind.EVIDENCE, source, STAMP, "b" * 64
        ),
        StoreReceipt(
            _run(), "compare-sub", "comparison", ArtifactKind.COMPARISON, source, STAMP, digest
        ),
    )
    return ComparisonProjected(
        AuditEventKind.COMPARISON,
        "comparison-event",
        _run(),
        "evidence",
        1,
        _receipt(
            AuditEventKind.COMPARISON, "comparison", 1, digest, "evidence", "comparison-event"
        ),
        StoredComparison(payload, receipts),
    )


@pytest.mark.parametrize("event", (*_new_events(), _comparison_event()))
def test_all_four_source_variants_work_in_knowledge_requests_and_results(
    event: ProjectionEvent,
) -> None:
    assert ProjectionSubmission(_run(), event).source_event is event
    result = CaseReadResult(_run(), ResultStatus.COMPLETE, (), (event,), 8, False, ())
    assert result.events == (event,)


def test_confirmed_verdict_requires_three_yes_checks_and_all_supporting_refs() -> None:
    verdict = _confirmed_verdict()
    assert verdict.value is VerdictValue.CONFIRMED
    for field in ("policy_check", "identity_check", "data_check"):
        with pytest.raises(ValueError, match="all three checks"):
            if field == "policy_check":
                replace(verdict, policy_check=CheckState.UNKNOWN)
            elif field == "identity_check":
                replace(verdict, identity_check=CheckState.UNKNOWN)
            else:
                replace(verdict, data_check=CheckState.UNKNOWN)
    with pytest.raises(ValueError, match="policy, comparison and Evidence"):
        replace(verdict, comparison_ref=None)
    with pytest.raises(ValueError, match="policy, comparison and Evidence"):
        replace(verdict, evidence_refs=())


@pytest.mark.parametrize("field", ["run_key", "verdict_ref", "revision"])
def test_verdict_projection_rejects_payload_identity_tampering(field: str) -> None:
    verdict = _verdict()
    event = VerdictProjected(
        AuditEventKind.VERDICT,
        "verdict-event",
        _run(),
        "judge",
        2,
        _receipt(
            AuditEventKind.VERDICT,
            "verdict-1",
            2,
            verdict_fingerprint(verdict),
            "judge",
            "verdict-event",
        ),
        verdict,
    )
    with pytest.raises(ValueError, match="binding|source/run"):
        if field == "run_key":
            replace(
                event,
                verdict=replace(verdict, run_key=RunKey("org", "target", "environment", "other")),
            )
        elif field == "verdict_ref":
            replace(event, verdict=replace(verdict, verdict_ref="forged-verdict"))
        else:
            replace(event, verdict=replace(verdict, revision=3))


def test_verdict_projection_rejects_forged_digest() -> None:
    verdict = _verdict()
    event = VerdictProjected(
        AuditEventKind.VERDICT,
        "verdict-event",
        _run(),
        "judge",
        2,
        _receipt(
            AuditEventKind.VERDICT,
            "verdict-1",
            2,
            verdict_fingerprint(verdict),
            "judge",
            "verdict-event",
        ),
        verdict,
    )
    binding = replace(event.source_receipt.binding, record_fingerprint="0" * 64)
    with pytest.raises(ValueError, match="binding"):
        replace(event, source_receipt=replace(event.source_receipt, binding=binding))


@pytest.mark.parametrize("field", ["target_ref", "policy_ref", "source_revision"])
def test_policy_projection_rejects_payload_identity_tampering(field: str) -> None:
    policy = _policy()
    event = PolicyRegistered(
        AuditEventKind.EXPECTED_POLICY,
        "policy-event",
        _run(),
        "registration",
        3,
        _receipt(
            AuditEventKind.EXPECTED_POLICY,
            "policy-1",
            3,
            expected_policy_fingerprint(policy),
            "registration",
            "policy-event",
        ),
        policy,
    )
    if field == "target_ref":
        forged = replace(policy, target_ref="other-target")
    elif field == "policy_ref":
        forged = replace(policy, policy_ref="forged-policy")
    else:
        with pytest.raises(ValueError, match="binding"):
            replace(event, source_revision=4)
        return
    with pytest.raises(ValueError, match="binding|target/environment"):
        replace(event, policy=forged)


def test_policy_projection_rejects_forged_digest() -> None:
    policy = _policy()
    event = PolicyRegistered(
        AuditEventKind.EXPECTED_POLICY,
        "policy-event",
        _run(),
        "registration",
        3,
        _receipt(
            AuditEventKind.EXPECTED_POLICY,
            "policy-1",
            3,
            expected_policy_fingerprint(policy),
            "registration",
            "policy-event",
        ),
        policy,
    )
    binding = replace(event.source_receipt.binding, record_fingerprint="0" * 64)
    with pytest.raises(ValueError, match="binding"):
        replace(event, source_receipt=replace(event.source_receipt, binding=binding))


@pytest.mark.parametrize("field", ["kind", "event_ref", "producer", "source_revision"])
def test_projection_rejects_outer_binding_tampering(field: str) -> None:
    event = _observation_event()
    with pytest.raises(ValueError, match="projection|binding|kind"):
        if field == "kind":
            replace(event, kind=AuditEventKind.VERDICT)
        elif field == "event_ref":
            replace(event, event_ref="forged")
        elif field == "producer":
            replace(event, producer="forged")
        else:
            replace(event, source_revision=2)


def test_projection_rejects_nested_payload_or_receipt_digest_tampering() -> None:
    event = _observation_event()
    forged_observation = replace(event.observation, evidence_ref="evidence-forged")
    with pytest.raises(ValueError, match="binding"):
        replace(event, observation=forged_observation)
    forged_binding = replace(event.source_receipt.binding, record_fingerprint="0" * 64)
    forged_receipt = replace(event.source_receipt, binding=forged_binding)
    with pytest.raises(ValueError, match="binding"):
        replace(event, source_receipt=forged_receipt)


def test_projection_union_rejects_raw_response_and_wrong_event_kind() -> None:
    with pytest.raises(TypeError, match="contract record"):
        ObservationProjected(
            AuditEventKind.OBSERVATION,
            "event",
            _run(),
            "webdiag",
            1,
            _receipt(AuditEventKind.OBSERVATION, "observation-1", 1, "0" * 64, "webdiag", "event"),
            RawResponse(200, (), b"raw"),  # type: ignore[arg-type]
        )
    observation = _observation()
    with pytest.raises(ValueError, match="projection kind"):
        ObservationProjected(
            AuditEventKind.VERDICT,
            "observation-event",
            _run(),
            "webdiag",
            1,
            _receipt(
                AuditEventKind.OBSERVATION,
                "observation-1",
                1,
                observation_fingerprint(observation),
                "webdiag",
                "observation-event",
            ),
            observation,
        )
