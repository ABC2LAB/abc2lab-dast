"""Immutable registration snapshots injected by the application boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from abc2lab_contracts._validation import ContractRecord, normalize_utc, require_positive
from abc2lab_contracts.primitives import (
    Purpose,
    Ref,
    RequestParameter,
    RunKey,
    SourceVersion,
    UtcTime,
)


class ExpectedAccess(StrEnum):
    """Expected access values are serialized as allow, deny, or unknown."""

    ALLOW = "allow"
    DENY = "deny"
    UNKNOWN = "unknown"


class ResolutionState(StrEnum):
    """Registered sharing/delegation resolution state."""

    RESOLVED_NONE = "resolved_none"
    RESOLVED_ALLOW = "resolved_allow"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ScopeSnapshot(ContractRecord):
    """Capture the allowed origins and operations for one run."""

    source: SourceVersion
    allowed_origins: tuple[str, ...]
    allowed_operation_refs: tuple[Ref, ...]
    valid_from: UtcTime
    valid_until: UtcTime

    def _validate_invariants(self) -> None:
        if normalize_utc(self.valid_from) >= normalize_utc(self.valid_until):
            raise ValueError("scope validity must be ordered")


@dataclass(frozen=True, slots=True)
class ExecutionProfileSnapshot(ContractRecord):
    """Capture allowed methods, purposes, and redirect behavior."""

    source: SourceVersion
    allowed_methods: tuple[str, ...]
    allowed_purposes: tuple[Purpose, ...]
    allow_redirects: bool
    valid_until: UtcTime


@dataclass(frozen=True, slots=True)
class BudgetSnapshot(ContractRecord):
    """Capture static attempt, duration, and response-size limits."""

    source: SourceVersion
    max_attempts: int
    max_duration_ms: int
    max_response_bytes: int

    def _validate_invariants(self) -> None:
        require_positive("max_attempts", self.max_attempts)
        require_positive("max_duration_ms", self.max_duration_ms)
        require_positive("max_response_bytes", self.max_response_bytes)


@dataclass(frozen=True, slots=True)
class AccountRegistration(ContractRecord):
    """Describe an account without including credential material."""

    account_ref: Ref
    expected_subject_ref: Ref
    auth_profile_ref: Ref
    identity_profile_ref: Ref


@dataclass(frozen=True, slots=True)
class OperationRegistration(ContractRecord):
    """Describe one registered operation and its resource bindings."""

    source: SourceVersion
    operation_ref: Ref
    allowed_purposes: tuple[Purpose, ...]
    auth_profile_ref: Ref | None
    method: str
    origin: str
    path_template: str
    resource_bindings: tuple[ResourceBinding, ...]

    def _validate_invariants(self) -> None:
        if (
            Purpose.AUTHENTICATE in self.allowed_purposes
            or Purpose.IDENTIFY in self.allowed_purposes
        ):
            if self.auth_profile_ref is None:
                raise ValueError("authentication operations require auth_profile_ref")


@dataclass(frozen=True, slots=True)
class ResourceBinding(ContractRecord):
    """Bind a registered resource to an owner and parameter template."""

    resource_binding_ref: Ref
    source: SourceVersion
    resource_ref: Ref
    owner_subject_ref: Ref
    parameters: tuple[RequestParameter, ...]


@dataclass(frozen=True, slots=True)
class ExpectedAccessPolicySnapshot(ContractRecord):
    """Declare the expected access for one registered A/B operation."""

    source: SourceVersion
    policy_ref: Ref
    target_ref: Ref
    environment_ref: Ref
    resource_ref: Ref
    operation_ref: Ref
    owner_subject_ref: Ref
    evaluated_subject_ref: Ref
    expected_access: ExpectedAccess
    sharing: ResolutionState
    delegation: ResolutionState
    valid_from: UtcTime
    valid_until: UtcTime

    def _validate_invariants(self) -> None:
        if normalize_utc(self.valid_from) >= normalize_utc(self.valid_until):
            raise ValueError("policy validity must be ordered")


@dataclass(frozen=True, slots=True)
class CrossExecutionConfirmation(ContractRecord):
    """Confirm the owner/evaluated account pairing for one execution."""

    source: SourceVersion
    run_key: RunKey
    resource_ref: Ref
    operation_ref: Ref
    owner_account_ref: Ref
    evaluated_account_ref: Ref
    valid_until: UtcTime


@dataclass(frozen=True, slots=True)
class ComparisonRules(ContractRecord):
    """Identify the registered comparison and canary rules."""

    source: SourceVersion
    normalizer_ref: Ref
    oracle_ref: Ref
    canary_profile_ref: Ref
