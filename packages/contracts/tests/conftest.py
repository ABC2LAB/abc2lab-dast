"""Typed C2 fixtures shared by fingerprint and no-I/O contract tests."""

from datetime import UTC, datetime, timedelta

import pytest
from abc2lab_contracts.audit import (
    AttemptRecord,
    AuditEventKind,
    AuditReceipt,
    AuditRecordBinding,
    PolicyOutcome,
    RequestIntentRecord,
)
from abc2lab_contracts.execution import (
    ExecutionRequest,
    PolicyAttributes,
    PolicyDecision,
    PolicyDecisionContent,
    PolicyIdentityStatus,
    PolicyInput,
    PrivateHttpRequest,
)
from abc2lab_contracts.primitives import (
    CaptureStatus,
    Purpose,
    RunKey,
    SendStatus,
    SourceVersion,
)
from abc2lab_contracts.registration import BudgetSnapshot, ExecutionProfileSnapshot, ScopeSnapshot
from abc2lab_contracts.session import IdentityContent, IdentityResult, IdentityStatus, SessionHandle


def _time(seconds: int = 0) -> datetime:
    return datetime(2026, 10, 21, tzinfo=UTC) + timedelta(seconds=seconds)


@pytest.fixture
def run_key() -> RunKey:
    return RunKey("org-demo", "target-demo", "env-demo", "run-demo")


@pytest.fixture
def source() -> SourceVersion:
    return SourceVersion("app-demo", "source-demo", 1)


@pytest.fixture
def policy_input(run_key: RunKey, source: SourceVersion) -> PolicyInput:
    scope = ScopeSnapshot(
        SourceVersion("app-demo", "scope-demo", 1),
        ("https://target.invalid",),
        ("operation-read",),
        _time(),
        _time(3600),
    )
    profile = ExecutionProfileSnapshot(
        SourceVersion("app-demo", "profile-demo", 1),
        ("GET",),
        (Purpose.OBSERVE,),
        False,
        _time(3600),
    )
    budget = BudgetSnapshot(SourceVersion("app-demo", "budget-demo", 1), 10, 120000, 1048576)
    attributes = PolicyAttributes(
        True,
        ("object_id",),
        True,
        "resource-a",
        "binding-resource-a",
        1,
        "subject-a",
        SourceVersion("app-demo", "registration-demo", 1),
    )
    return PolicyInput(
        "policy_input.v1",
        run_key,
        "request-demo",
        "binding-demo",
        "gateway-demo",
        _time(15),
        "https://target.invalid",
        "GET",
        "operation-read",
        1,
        Purpose.OBSERVE,
        attributes,
        "account-a",
        3,
        "identity-a",
        "subject-a",
        PolicyIdentityStatus.VERIFIED,
        None,
        scope,
        profile,
        budget,
        None,
        None,
    )


@pytest.fixture
def decision_content(
    run_key: RunKey, source: SourceVersion, policy_input: PolicyInput
) -> PolicyDecisionContent:
    return PolicyDecisionContent(
        run_key,
        "decision-demo",
        "binding-demo",
        "8e8a1bd12e3ccde4439bb279d3638bf34a61a66b3dcfb993540666d56e96daad",
        PolicyOutcome.ALLOW,
        SourceVersion("policy-demo", "policy-rules", 2),
        _time(1),
        _time(15),
        (),
    )


def _receipt(
    run_key: RunKey,
    kind: AuditEventKind,
    reference: str,
    fingerprint: str,
    producer: str,
    request_ref: str | None = None,
    binding_id: str | None = None,
) -> AuditReceipt:
    binding = AuditRecordBinding(kind, reference, 1, fingerprint, request_ref, None, binding_id)
    return AuditReceipt(run_key, producer, f"event-{reference}", 1, binding, _time(5))


@pytest.fixture
def decision(run_key: RunKey, decision_content: PolicyDecisionContent) -> PolicyDecision:
    from abc2lab_contracts.fingerprint import policy_decision_content_fingerprint

    fingerprint = policy_decision_content_fingerprint(decision_content)
    return PolicyDecision.from_content(
        decision_content,
        _receipt(
            run_key,
            AuditEventKind.POLICY_DECISION,
            "decision-demo",
            fingerprint,
            "policy-demo",
            "request-demo",
            "binding-demo",
        ),
    )


@pytest.fixture
def identity_content(run_key: RunKey) -> IdentityContent:
    return IdentityContent(
        run_key,
        "identity-a",
        IdentityStatus.VERIFIED,
        "session-a",
        "account-a",
        3,
        "subject-a",
        "evidence-identity-a",
        _time(2),
        _time(32),
        (),
        (),
    )


@pytest.fixture
def identity(run_key: RunKey, identity_content: IdentityContent) -> IdentityResult:
    from abc2lab_contracts.fingerprint import identity_content_fingerprint

    fingerprint = identity_content_fingerprint(identity_content)
    return IdentityResult.from_content(
        identity_content,
        _receipt(run_key, AuditEventKind.IDENTITY, "identity-a", fingerprint, "webdiag-demo"),
    )


@pytest.fixture
def intent(run_key: RunKey) -> RequestIntentRecord:
    return RequestIntentRecord(
        run_key,
        "request-demo",
        "attempt-demo",
        "binding-demo",
        "operation-read",
        1,
        Purpose.OBSERVE,
        "account-a",
        3,
        "decision-demo",
        "8e8a1bd12e3ccde4439bb279d3638bf34a61a66b3dcfb993540666d56e96daad",
        _time(3),
    )


@pytest.fixture
def attempt(run_key: RunKey) -> AttemptRecord:
    return AttemptRecord(
        run_key,
        "request-demo",
        "attempt-demo",
        1,
        "decision-demo",
        "binding-demo",
        "operation-read",
        "account-a",
        3,
        SendStatus.SENT,
        CaptureStatus.CAPTURED,
        _time(4),
        (),
    )


@pytest.fixture
def execution_request(run_key: RunKey) -> ExecutionRequest:
    return ExecutionRequest(
        run_key,
        "request-demo",
        "operation-read",
        1,
        "resource-a",
        "binding-resource-a",
        1,
        Purpose.OBSERVE,
        PrivateHttpRequest("https://target.invalid", "GET", "/objects/7", (), 3000),
        SessionHandle("session-a", run_key, "account-a", 3, _time(300)),
        None,
        1,
        1,
        None,
        None,
    )
