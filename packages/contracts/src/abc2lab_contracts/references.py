"""Opaque identifiers for registered execution inputs; references grant no authority."""

from dataclasses import dataclass


def _validate_token(value: str, field: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in value
        )
    ):
        raise ValueError(
            f"{field} must be a nonempty token without whitespace or control characters"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class _OpaqueRef:
    value: str

    def __post_init__(self) -> None:
        _validate_token(self.value, "value")


@dataclass(frozen=True, slots=True, kw_only=True)
class _VersionedRef(_OpaqueRef):
    revision: str

    def __post_init__(self) -> None:
        _validate_token(self.value, "value")
        _validate_token(self.revision, "revision")


@dataclass(frozen=True, slots=True, kw_only=True)
class RunRef(_OpaqueRef):
    """Identify one run, whose registered target and environment cannot change."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestRef(_OpaqueRef):
    """Identify one immutable logical request plan, separate from transmission attempts."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountRef(_OpaqueRef):
    """Identify a registered account alias without credentials or identity claims."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionRef(_OpaqueRef):
    """Identify a vault-managed session without exposing its authentication material."""


@dataclass(frozen=True, slots=True, kw_only=True)
class TargetScopeRef(_VersionedRef):
    """Identify an immutable revision of a registered target scope."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizationRef(_VersionedRef):
    """Identify a revision of an operator's execution authorization, subject to revocation."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestSpecRef(_VersionedRef):
    """Identify immutable destination, headers, payload and authentication preparation."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionProfileRef(_VersionedRef):
    """Identify immutable finite execution limits and allowed request behavior."""


@dataclass(frozen=True, slots=True, kw_only=True)
class BudgetRef(_VersionedRef):
    """Identify immutable budget configuration; remaining capacity is checked atomically."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyDecisionRef(_OpaqueRef):
    """Identify an immutable policy decision and its independently persisted audit record."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestAttemptRef(_OpaqueRef):
    """Identify one transmission attempt, including attempts with unknown send status."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ReasonCode(_OpaqueRef):
    """Carry a stable diagnostic code instead of a potentially sensitive exception message."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionBinding:
    """Bind a session generation to its registered account; no lifecycle or identity proof."""

    account_ref: AccountRef
    session_ref: SessionRef
    generation: int

    def __post_init__(self) -> None:
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("generation must be a nonnegative integer")
