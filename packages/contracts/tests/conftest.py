"""Deterministic, credential-free inputs for contract tests."""

import pytest
from abc2lab_contracts import (
    AccountRef,
    AuthorizationRef,
    BudgetRef,
    ExecutionProfileRef,
    RequestBinding,
    RequestPlan,
    RequestPurpose,
    RequestRef,
    RequestSpecRef,
    RunContext,
    RunRef,
    SessionBinding,
    SessionRef,
    TargetScopeRef,
)


@pytest.fixture
def plan() -> RequestPlan:
    """Build one authenticated observation plan without network or registry I/O."""
    account = AccountRef(value="owner")
    return RequestPlan(
        binding=RequestBinding(
            context=RunContext(
                run_ref=RunRef(value="run-1"),
                target_scope_ref=TargetScopeRef(value="target-1", revision="1"),
                authorization_ref=AuthorizationRef(value="authorization-1", revision="1"),
                execution_profile_ref=ExecutionProfileRef(value="read-only", revision="1"),
                budget_ref=BudgetRef(value="budget-1", revision="1"),
            ),
            request_ref=RequestRef(value="request-1"),
            request_spec_ref=RequestSpecRef(value="request-spec-1", revision="1"),
            method="GET",
            purpose=RequestPurpose.OBSERVE,
            account_ref=account,
            session=SessionBinding(
                account_ref=account,
                session_ref=SessionRef(value="session-1"),
                generation=0,
            ),
        )
    )
