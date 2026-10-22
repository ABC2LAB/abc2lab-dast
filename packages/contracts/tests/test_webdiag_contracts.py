"""Host↔WebDiag C4 record의 불변식과 WebDiagPort 구조 적합성을 검사한다."""

from datetime import UTC, datetime

import pytest
from abc2lab_contracts.primitives import ResultStatus, RunKey
from abc2lab_contracts.session import IdentityResult, SessionHandle, SessionResult
from abc2lab_contracts.webdiag import (
    AccessCompareRequest,
    AccessCompareResult,
    DiscoveryRequest,
    DiscoveryResult,
    IdentityRequest,
    ObserveRequest,
    ObserveResult,
    SessionRequest,
    WebDiagPort,
)

_RUN = RunKey(
    organization_ref="org-1",
    target_ref="target-1",
    environment_ref="env-1",
    run_ref="run-1",
)


def _handle() -> SessionHandle:
    return SessionHandle(
        session_ref="session-a",
        run_key=_RUN,
        account_ref="account-a",
        generation=1,
        expires_at=datetime(2026, 10, 22, tzinfo=UTC),
    )


def test_session_and_identity_requests_construct() -> None:
    """최소 인증·주체 확인 요청이 유효하게 구성된다."""
    SessionRequest(run_key=_RUN, account_ref="account-a", auth_profile_ref="auth-1")
    request = IdentityRequest(run_key=_RUN, session=_handle(), identity_profile_ref="id-1")
    assert request.session.account_ref == "account-a"


def test_discovery_request_requires_positive_max() -> None:
    """max_candidates는 양의 정수여야 한다."""
    DiscoveryRequest(
        run_key=_RUN, seed_operation_refs=("op-1",), account_ref="account-a", max_candidates=1
    )
    with pytest.raises(ValueError, match="max_candidates"):
        DiscoveryRequest(
            run_key=_RUN, seed_operation_refs=(), account_ref="account-a", max_candidates=0
        )


def test_discovery_result_failed_cannot_publish_hints() -> None:
    """실패한 발견 결과는 단서를 발행하지 않는다. 빈 단서는 어느 상태든 유효하다."""
    DiscoveryResult(
        run_key=_RUN, status=ResultStatus.FAILED, hints=(), attempt_summaries=(), reason_codes=()
    )
    DiscoveryResult(
        run_key=_RUN, status=ResultStatus.COMPLETE, hints=(), attempt_summaries=(), reason_codes=()
    )


def test_observe_result_observation_only_on_complete() -> None:
    """Observation은 complete에만 존재하고 complete는 관찰·투영을 요구한다."""
    ObserveResult(
        run_key=_RUN,
        status=ResultStatus.FAILED,
        observation=None,
        projection_events=(),
        attempt_summaries=(),
        reason_codes=(),
    )
    with pytest.raises(ValueError, match="complete observe result"):
        ObserveResult(
            run_key=_RUN,
            status=ResultStatus.COMPLETE,
            observation=None,
            projection_events=(),
            attempt_summaries=(),
            reason_codes=(),
        )


def test_access_compare_result_comparison_only_on_complete() -> None:
    """저장 완료 비교는 complete에만 존재한다."""
    AccessCompareResult(
        run_key=_RUN,
        case_ref="case-1",
        status=ResultStatus.FAILED,
        owner_identity=None,
        evaluated_identity=None,
        owner_observation=None,
        stored_comparison=None,
        stored_evidence_refs=(),
        projection_events=(),
        attempt_summaries=(),
        reason_codes=(),
    )
    with pytest.raises(ValueError, match="complete access compare"):
        AccessCompareResult(
            run_key=_RUN,
            case_ref="case-1",
            status=ResultStatus.COMPLETE,
            owner_identity=None,
            evaluated_identity=None,
            owner_observation=None,
            stored_comparison=None,
            stored_evidence_refs=(),
            projection_events=(),
            attempt_summaries=(),
            reason_codes=(),
        )


class _FakeWebDiag:
    """구조적 적합성 확인용 최소 fake다."""

    async def collect(self, request: DiscoveryRequest) -> DiscoveryResult:
        raise NotImplementedError

    async def http_observe(self, request: ObserveRequest) -> ObserveResult:
        raise NotImplementedError

    async def access_compare(self, request: AccessCompareRequest) -> AccessCompareResult:
        raise NotImplementedError

    async def acquire_session(self, request: SessionRequest) -> SessionResult:
        raise NotImplementedError

    async def whoami(self, request: IdentityRequest) -> IdentityResult:
        raise NotImplementedError


def test_fake_satisfies_webdiag_port() -> None:
    """fake는 WebDiagPort를 구조적으로 만족한다."""
    port: WebDiagPort = _FakeWebDiag()
    assert port is not None
