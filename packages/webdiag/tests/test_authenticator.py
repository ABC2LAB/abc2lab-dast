"""whoami — identify→주체확인→근거 봉인→감사 commit→IdentityResult를 검사한다."""

from datetime import UTC, datetime

import pytest
from abc2lab_contracts.audit import AuditEventKind, AuditReceipt, AuditRecordBinding
from abc2lab_contracts.evidence import (
    ArtifactKind,
    EvidenceSummary,
    SealRequest,
    SealResult,
    StoreReceipt,
)
from abc2lab_contracts.execution import (
    AttemptResult,
    ExecutionRequest,
    PolicyAttributes,
    PolicyDecisionResult,
    PolicyIdentityStatus,
    PolicyInput,
    PrepareResult,
)
from abc2lab_contracts.fingerprint import evidence_fingerprint
from abc2lab_contracts.primitives import (
    CaptureStatus,
    Purpose,
    ReasonCode,
    Ref,
    ResponseClass,
    ResultStatus,
    RunKey,
    SendStatus,
    SourceVersion,
)
from abc2lab_contracts.registration import (
    BudgetSnapshot,
    ComparisonRules,
    ExecutionProfileSnapshot,
    OperationRegistration,
    ScopeSnapshot,
)
from abc2lab_contracts.session import (
    AuthSignal,
    AuthSignalKind,
    AuthSignalState,
    IdentityStatus,
    SessionHandle,
)
from abc2lab_contracts.webdiag import IdentityRequest
from abc2lab_webdiag.core.authenticator import SessionAuthenticator
from abc2lab_webdiag.core.identity_ports import IdentityCommit, IdentityProfile

_RUN = RunKey(
    organization_ref="org-1", target_ref="target-1", environment_ref="env-1", run_ref="run-1"
)
_SRC = SourceVersion(issuer="issuer-1", source_ref="src-1", revision=1)
_NOW = datetime(2026, 10, 23, 0, 0, 0, tzinfo=UTC)
_T1 = datetime(2026, 10, 23, 1, 0, 0, tzinfo=UTC)
_SESSION = SessionHandle(
    session_ref="session-a", run_key=_RUN, account_ref="account-a", generation=1, expires_at=_T1
)


def _operation() -> OperationRegistration:
    return OperationRegistration(
        source=_SRC,
        operation_ref="op-id",
        allowed_purposes=(Purpose.IDENTIFY,),
        auth_profile_ref="auth-1",
        method="GET",
        origin="https://app.example",
        path_template="/me",
        resource_bindings=(),
    )


def _profile() -> IdentityProfile:
    return IdentityProfile(
        operation=_operation(),
        expected_subject_ref="subject-a",
        scope_revision=1,
        profile_revision=1,
        timeout_ms=5000,
        identity_ttl_ms=30000,
        rules=ComparisonRules(
            source=_SRC, normalizer_ref="n-1", oracle_ref="o-1", canary_profile_ref="c-1"
        ),
    )


def _policy_input() -> PolicyInput:
    return PolicyInput(
        schema_version="policy_input.v1",
        run_key=_RUN,
        request_ref="request-1",
        binding_id="binding-1",
        binding_issuer="gateway-1",
        expires_at=_T1,
        origin="https://app.example",
        method="GET",
        operation_ref="op-id",
        operation_revision=1,
        purpose=Purpose.IDENTIFY,
        policy_attributes=PolicyAttributes(
            registered_path_matches=True,
            parameter_names=(),
            parameters_match_registration=True,
            resource_ref=None,
            resource_binding_ref=None,
            resource_binding_revision=None,
            resource_owner_subject_ref=None,
            provenance=_SRC,
        ),
        account_ref="account-a",
        session_generation=1,
        identity_ref=None,
        subject_ref=None,
        identity_status=PolicyIdentityStatus.UNKNOWN,
        owner_identity=None,
        scope=ScopeSnapshot(
            source=_SRC,
            allowed_origins=("https://app.example",),
            allowed_operation_refs=("op-id",),
            valid_from=_NOW,
            valid_until=_T1,
        ),
        profile=ExecutionProfileSnapshot(
            source=_SRC,
            allowed_methods=("GET",),
            allowed_purposes=(Purpose.IDENTIFY,),
            allow_redirects=False,
            valid_until=_T1,
        ),
        budget=BudgetSnapshot(
            source=_SRC, max_attempts=10, max_duration_ms=1000, max_response_bytes=1048576
        ),
        expected_policy=None,
        cross_confirmation=None,
    )


def _attempt(*, state: AuthSignalState, subject: str | None, captured: bool) -> AttemptResult:
    return AttemptResult(
        run_key=_RUN,
        request_ref="request-1",
        attempt_ref="attempt-1",
        decision_ref=None,
        binding_id=None,
        send_status=SendStatus.SENT,
        capture_status=CaptureStatus.CAPTURED if captured else CaptureStatus.UNAVAILABLE,
        capture_ref="cap-1" if captured else None,
        auth_signal=AuthSignal(kind=AuthSignalKind.IDENTITY, state=state, subject_ref=subject),
        audit_links=(),
        reason_codes=(),
    )


def _evidence_summary() -> EvidenceSummary:
    from abc2lab_contracts.primitives import AuditLink

    return EvidenceSummary(
        run_key=_RUN,
        evidence_ref="evid-1",
        attempt_ref="attempt-1",
        operation_ref="op-id",
        resource_ref=None,
        account_ref="account-a",
        session_generation=1,
        identity_ref=None,
        response_class=ResponseClass.NORMAL,
        http_status=200,
        observed_at=_NOW,
        redaction_version=_SRC,
        source_event=AuditLink(producer="evidence", event_ref="ev-e"),
        request_recipe=None,
        recipe_reason_codes=(ReasonCode.RECIPE_NOT_EXPORTABLE,),
    )


def _seal_complete() -> SealResult:
    summary = _evidence_summary()
    receipt = StoreReceipt(
        run_key=_RUN,
        submission_ref="submission-2",
        artifact_ref="evid-1",
        artifact_kind=ArtifactKind.EVIDENCE,
        source=_SRC,
        committed_at=_NOW,
        content_fingerprint=evidence_fingerprint(summary),
    )
    return SealResult(
        run_key=_RUN,
        status=ResultStatus.COMPLETE,
        evidence=summary,
        receipts=(receipt,),
        reason_codes=(),
    )


def _audit_receipt() -> AuditReceipt:
    return AuditReceipt(
        run_key=_RUN,
        producer="webdiag",
        event_ref="idev-1",
        sequence=1,
        binding=AuditRecordBinding(
            event_kind=AuditEventKind.IDENTITY,
            record_ref="identity-3",
            record_revision=1,
            record_fingerprint="a" * 64,
            request_ref=None,
            attempt_ref=None,
            binding_id=None,
        ),
        committed_at=_NOW,
    )


class _FakeClock:
    def __init__(self) -> None:
        self._n = 0

    def now(self) -> datetime:
        return _NOW

    def new_ref(self, label: str) -> Ref:
        self._n += 1
        return f"{label}-{self._n}"


class _FakeRegistry:
    def __init__(self, profile: IdentityProfile | None) -> None:
        self._profile = profile

    def resolve(self, identity_profile_ref: Ref) -> IdentityProfile | None:
        return self._profile


class _FakeGateway:
    def __init__(self, attempt: AttemptResult) -> None:
        self._attempt = attempt
        self.prepared = 0

    async def prepare(self, request: ExecutionRequest) -> PrepareResult:
        self.prepared += 1
        return PrepareResult(
            run_key=_RUN,
            status=ResultStatus.COMPLETE,
            prepared_handle="handle-1",
            policy_input=_policy_input(),
            reason_codes=(),
        )

    async def execute(self, request: object) -> AttemptResult:
        return self._attempt


class _FakePolicy:
    async def evaluate(self, request: PolicyInput) -> PolicyDecisionResult:
        return PolicyDecisionResult(
            run_key=_RUN, status=ResultStatus.FAILED, decision=None, reason_codes=()
        )


class _FakeSealer:
    def __init__(self, result: SealResult) -> None:
        self._result = result
        self.calls = 0

    async def seal(self, request: SealRequest) -> SealResult:
        self.calls += 1
        return self._result


class _FakeJournal:
    def __init__(self, commit: IdentityCommit) -> None:
        self._commit = commit
        self.calls = 0

    async def commit_identity(self, content: object) -> IdentityCommit:
        self.calls += 1
        return self._commit


def _authenticator(
    *,
    profile: IdentityProfile | None,
    attempt: AttemptResult,
    seal: SealResult,
    commit: IdentityCommit,
) -> tuple[SessionAuthenticator, _FakeSealer, _FakeJournal]:
    sealer = _FakeSealer(seal)
    journal = _FakeJournal(commit)
    authenticator = SessionAuthenticator(
        registry=_FakeRegistry(profile),
        clock=_FakeClock(),
        gateway=_FakeGateway(attempt),
        policy=_FakePolicy(),
        evidence=sealer,
        journal=journal,
    )
    return authenticator, sealer, journal


_REQUEST = IdentityRequest(run_key=_RUN, session=_SESSION, identity_profile_ref="id-profile-1")


@pytest.mark.asyncio
async def test_unsupported_profile_is_unknown() -> None:
    """미등록 프로필은 UNKNOWN·unsupported_authentication으로 남긴다."""
    auth, sealer, journal = _authenticator(
        profile=None,
        attempt=_attempt(state=AuthSignalState.ACCEPTED, subject="subject-a", captured=True),
        seal=_seal_complete(),
        commit=IdentityCommit(receipt=_audit_receipt(), reason_codes=()),
    )
    result = await auth.whoami(_REQUEST)
    assert result.status is IdentityStatus.UNKNOWN
    assert ReasonCode.UNSUPPORTED_AUTHENTICATION in result.reason_codes
    assert sealer.calls == 0


@pytest.mark.asyncio
async def test_subject_mismatch_does_not_seal_or_commit() -> None:
    """다른 주체가 확인되면 MISMATCH이고 근거 봉인·감사를 수행하지 않는다."""
    auth, sealer, journal = _authenticator(
        profile=_profile(),
        attempt=_attempt(state=AuthSignalState.ACCEPTED, subject="subject-b", captured=True),
        seal=_seal_complete(),
        commit=IdentityCommit(receipt=_audit_receipt(), reason_codes=()),
    )
    result = await auth.whoami(_REQUEST)
    assert result.status is IdentityStatus.MISMATCH
    assert result.subject_ref == "subject-b"
    assert result.audit_receipt is None
    assert sealer.calls == 0
    assert journal.calls == 0


@pytest.mark.asyncio
async def test_verified_identity_seals_and_commits() -> None:
    """주체 일치 시 근거를 봉인하고 감사 commit 후 VERIFIED IdentityResult를 발행한다."""
    auth, sealer, journal = _authenticator(
        profile=_profile(),
        attempt=_attempt(state=AuthSignalState.ACCEPTED, subject="subject-a", captured=True),
        seal=_seal_complete(),
        commit=IdentityCommit(receipt=_audit_receipt(), reason_codes=()),
    )
    result = await auth.whoami(_REQUEST)
    assert result.status is IdentityStatus.VERIFIED
    assert result.subject_ref == "subject-a"
    assert result.evidence_ref == "evid-1"
    assert result.audit_receipt is not None
    assert result.verified_at == _NOW
    assert sealer.calls == 1
    assert journal.calls == 1


@pytest.mark.asyncio
async def test_seal_failure_leaves_unverified_without_commit() -> None:
    """근거 봉인이 실패하면 VERIFIED를 발행하지 않고 감사도 호출하지 않는다."""
    failed_seal = SealResult(
        run_key=_RUN,
        status=ResultStatus.FAILED,
        evidence=None,
        receipts=(),
        reason_codes=(ReasonCode.EVIDENCE_STORE_FAILED,),
    )
    auth, sealer, journal = _authenticator(
        profile=_profile(),
        attempt=_attempt(state=AuthSignalState.ACCEPTED, subject="subject-a", captured=True),
        seal=failed_seal,
        commit=IdentityCommit(receipt=_audit_receipt(), reason_codes=()),
    )
    result = await auth.whoami(_REQUEST)
    assert result.status is IdentityStatus.UNKNOWN
    assert ReasonCode.EVIDENCE_STORE_FAILED in result.reason_codes
    assert result.audit_receipt is None
    assert sealer.calls == 1
    assert journal.calls == 0
