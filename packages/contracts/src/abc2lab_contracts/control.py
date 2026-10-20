"""Immutable Policy inputs and decisions for the first controlled execution slice."""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from abc2lab_contracts.references import (
    AccountRef,
    AuthorizationRef,
    BudgetRef,
    ExecutionProfileRef,
    PolicyDecisionRef,
    ReasonCode,
    RequestRef,
    RequestSpecRef,
    RunRef,
    SessionBinding,
    TargetScopeRef,
)

_HTTP_METHOD_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Z-]+", re.ASCII)


class RequestPurpose(StrEnum):
    """Distinguish observation from registered authentication flows in this slice."""

    OBSERVE = "observe"
    AUTHENTICATE = "authenticate"


@dataclass(frozen=True, slots=True, kw_only=True)
class RunContext:
    """Bind a run to revisions of its scope, authorization, profile and budget."""

    run_ref: RunRef
    target_scope_ref: TargetScopeRef
    authorization_ref: AuthorizationRef
    execution_profile_ref: ExecutionProfileRef
    budget_ref: BudgetRef


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestBinding:
    """Bind every policy-relevant request input using immutable registered references."""

    context: RunContext
    request_ref: RequestRef
    request_spec_ref: RequestSpecRef
    method: str
    purpose: RequestPurpose
    account_ref: AccountRef | None
    session: SessionBinding | None

    def __post_init__(self) -> None:
        if not _HTTP_METHOD_TOKEN.fullmatch(self.method):
            raise ValueError("method must be an uppercase HTTP token")
        if not isinstance(self.purpose, RequestPurpose):
            raise ValueError("purpose must be a RequestPurpose")
        if self.session is not None and self.session.account_ref != self.account_ref:
            raise ValueError("session account must match account_ref")
        if self.purpose is RequestPurpose.AUTHENTICATE and self.account_ref is None:
            raise ValueError("authentication requires an account_ref")


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestPlan:
    """Describe a request to evaluate, without transmitting or granting authorization."""

    binding: RequestBinding


class PolicyOutcome(StrEnum):
    """Represent the policy gate; allow alone never proves a request was sent."""

    ALLOW = "allow"
    BLOCK = "block"


class RequestBindingError(ValueError):
    """Signal a decision/plan mismatch that must be rejected before transmission."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyDecision:
    """Record a policy outcome for exactly one request binding, without granting trust."""

    decision_ref: PolicyDecisionRef
    binding: RequestBinding
    outcome: PolicyOutcome
    reason_code: ReasonCode

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, PolicyOutcome):
            raise ValueError("outcome must be a PolicyOutcome")

    def validate_binding(self, plan: RequestPlan) -> None:
        """Reject a different request binding without disclosing the input values."""
        if self.binding != plan.binding:
            raise RequestBindingError("policy decision does not match request binding")


class PolicyPort(Protocol):
    """Evaluate registered inputs, defaulting to block when checks cannot be completed."""

    def evaluate(self, plan: RequestPlan, ctx: RunContext) -> PolicyDecision:
        """Return a decision retaining plan.binding, including when context checks fail."""
        ...
