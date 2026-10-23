"""`GatewaySessionContexts`(SessionContextPort 제공자) 테스트. 네트워크·DB 없이 실행한다.

account 스코프 검증(스푸핑 차단), 같은 세션/generation open 멱등, close 정리·멱등·run 격리를 본다.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from abc2lab_contracts.primitives import ReasonCode, Ref, ResultStatus, RunKey
from abc2lab_contracts.registration import AccountRegistration
from abc2lab_contracts.session import (
    SessionContextCloseRequest,
    SessionContextRequest,
)
from abc2lab_gateway.adapters import (
    GatewaySessionContexts,
    InMemoryAccountRegistrations,
)

_RUN = RunKey(
    organization_ref="org-1", target_ref="target-1", environment_ref="env-1", run_ref="run-1"
)
_PROFILE = "auth-prof-eval"


def _counter() -> Callable[[], Ref]:
    state = {"n": 0}

    def _next() -> Ref:
        state["n"] += 1
        return f"ctx-{state['n']}"

    return _next


def _account(account_ref: Ref, auth_profile_ref: Ref) -> AccountRegistration:
    return AccountRegistration(
        account_ref=account_ref,
        expected_subject_ref=f"subject-{account_ref}",
        auth_profile_ref=auth_profile_ref,
        identity_profile_ref=f"idp-{account_ref}",
    )


def _request(
    *, account_ref: str = "acct-eval", auth_profile_ref: str = _PROFILE, generation: int = 2
) -> SessionContextRequest:
    return SessionContextRequest(
        run_key=_RUN,
        session_ref="sess-eval",
        account_ref=account_ref,
        generation=generation,
        auth_profile_ref=auth_profile_ref,
    )


def _accounts() -> InMemoryAccountRegistrations:
    store = InMemoryAccountRegistrations()
    store.register(_RUN, _account("acct-eval", _PROFILE))
    store.register(_RUN, _account("acct-owner", "auth-prof-owner"))
    return store


def _contexts() -> GatewaySessionContexts:
    return GatewaySessionContexts(_accounts(), context_factory=_counter())


@pytest.mark.asyncio
async def test_registered_account_opens_context() -> None:
    result = await _contexts().open_session_context(_request())
    assert result.status is ResultStatus.COMPLETE
    assert result.transport_context_ref == "ctx-1"
    assert result.reason_codes == ()


@pytest.mark.asyncio
async def test_open_is_idempotent_per_session_generation() -> None:
    contexts = _contexts()
    first = await contexts.open_session_context(_request())
    again = await contexts.open_session_context(_request())
    assert again.transport_context_ref == first.transport_context_ref  # 같은 세션/generation 재사용
    newer = await contexts.open_session_context(_request(generation=3))
    assert (
        newer.transport_context_ref != first.transport_context_ref
    )  # 다른 generation은 새 context


@pytest.mark.asyncio
async def test_other_accounts_profile_is_denied() -> None:
    # acct-eval이 acct-owner의 auth profile로 context를 열려 하면 거부(계정 스코프).
    result = await _contexts().open_session_context(_request(auth_profile_ref="auth-prof-owner"))
    assert result.status is ResultStatus.FAILED
    assert result.transport_context_ref is None
    assert result.reason_codes == (ReasonCode.CONFIGURATION_MISSING,)


@pytest.mark.asyncio
async def test_unregistered_account_is_denied() -> None:
    result = await _contexts().open_session_context(_request(account_ref="acct-ghost"))
    assert result.status is ResultStatus.FAILED
    assert result.transport_context_ref is None
    assert result.reason_codes == (ReasonCode.CONFIGURATION_MISSING,)


@pytest.mark.asyncio
async def test_close_clears_context_and_mints_new_on_reopen() -> None:
    contexts = _contexts()
    opened = await contexts.open_session_context(_request())
    assert opened.transport_context_ref is not None
    closed = await contexts.close_session_context(
        SessionContextCloseRequest(_RUN, opened.transport_context_ref)
    )
    assert closed.status is ResultStatus.COMPLETE
    reopened = await contexts.open_session_context(_request())
    assert reopened.transport_context_ref != opened.transport_context_ref  # 정리됐으니 새 ref


@pytest.mark.asyncio
async def test_close_unknown_ref_is_idempotent() -> None:
    result = await _contexts().close_session_context(SessionContextCloseRequest(_RUN, "ctx-absent"))
    assert result.status is ResultStatus.COMPLETE


@pytest.mark.asyncio
async def test_close_from_other_run_does_not_clear() -> None:
    contexts = _contexts()
    opened = await contexts.open_session_context(_request())
    assert opened.transport_context_ref is not None
    other_run = RunKey(
        organization_ref="org-1", target_ref="target-1", environment_ref="env-1", run_ref="run-2"
    )
    await contexts.close_session_context(
        SessionContextCloseRequest(other_run, opened.transport_context_ref)
    )
    # 다른 run의 close는 이 context를 지우지 않는다 → 재open이 같은 ref를 돌려준다.
    again = await contexts.open_session_context(_request())
    assert again.transport_context_ref == opened.transport_context_ref
