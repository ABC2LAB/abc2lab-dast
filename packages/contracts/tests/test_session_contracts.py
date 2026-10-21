"""Focused runtime checks for the C2 session and identity contract."""

from dataclasses import replace

import pytest
from abc2lab_contracts.execution import ExecuteRequest, ExecutionRequest
from abc2lab_contracts.primitives import ResultStatus
from abc2lab_contracts.session import (
    IdentityContent,
    IdentityResult,
    IdentityStatus,
    SessionBinding,
    SessionResult,
    SessionState,
)


def test_verified_identity_requires_receipt(identity_content: IdentityContent) -> None:
    with pytest.raises(ValueError, match="audit receipt"):
        IdentityResult.from_content(identity_content, None)


def test_identity_content_cannot_be_used_as_final_result(identity_content: IdentityContent) -> None:
    with pytest.raises(TypeError):
        ExecuteRequest(
            identity_content.run_key,
            "request-1",
            "prepared-1",
            identity_content,  # type: ignore[arg-type]
        )


def test_session_binding_requires_matching_identity_snapshot(
    execution_request: ExecutionRequest, identity: IdentityResult
) -> None:
    session = execution_request.session
    assert session is not None
    wrong_account = replace(identity, account_ref="other-account")
    with pytest.raises(ValueError, match="identity binding"):
        SessionBinding(session, SessionState.AUTHENTICATING, wrong_account, "context-1", False)


def test_confirmed_binding_requires_verified_identity(
    execution_request: ExecutionRequest, identity: IdentityResult
) -> None:
    session = execution_request.session
    assert session is not None
    unknown = replace(identity, status=IdentityStatus.UNKNOWN, audit_receipt=None)
    with pytest.raises(ValueError, match="verified identity"):
        SessionBinding(session, SessionState.CONFIRMED, unknown, "context-1", False)


def test_session_result_output_matches_status(execution_request: ExecutionRequest) -> None:
    with pytest.raises(ValueError, match="confirmed session"):
        SessionResult(
            execution_request.run_key,
            ResultStatus.COMPLETE,
            None,
            SessionState.NOT_READY,
            (),
            (),
        )
    with pytest.raises(ValueError, match="confirmed state"):
        SessionResult(
            execution_request.run_key,
            ResultStatus.FAILED,
            None,
            SessionState.CONFIRMED,
            (),
            (),
        )
