"""Closed reason roles and the fail-closed whitelist for Judge call failures.

Every ReasonCode is deliberately classified as a Judge diagnostic or a call/
audit reason. The latter includes audit status, so its positive canary marker
is not a call failure. Keep failure members explicit rather than subtracting
diagnostics from the enum: a new unclassified member must not authorize FAILED.
"""

from abc2lab_contracts.primitives import ReasonCode

JUDGE_DIAGNOSTIC_REASON_CODES: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.POLICY_ALLOWS,
        ReasonCode.SHARING_OR_DELEGATION_ALLOWS,
        ReasonCode.EXPECTED_ACCESS_UNKNOWN,
        ReasonCode.SUBJECT_NOT_VERIFIED,
        ReasonCode.SUBJECTS_NOT_DISTINCT,
        ReasonCode.DATA_NO_MATCH,
        ReasonCode.DATA_REFLECTION_PRESENT,
        ReasonCode.DATA_TEMPLATE_PRESENT,
        ReasonCode.DATA_UNVERIFIABLE,
        ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,
        ReasonCode.EXPECTED_ACCESS_POLICY_INVALID,
        ReasonCode.SHARING_OR_DELEGATION_UNKNOWN,
    }
)

CALL_AUDIT_FAILURE_REASON_CODES: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.CONFIGURATION_MISSING,
        ReasonCode.NOT_FOUND,
        ReasonCode.ACCESS_DENIED,
        ReasonCode.REVISION_CONFLICT,
        ReasonCode.REVISION_UNAVAILABLE,
        ReasonCode.RESULT_LIMIT_EXCEEDED,
        ReasonCode.SNAPSHOT_EXPIRED,
        ReasonCode.IDEMPOTENCY_CONFLICT,
        ReasonCode.UNSUPPORTED_AUTHENTICATION,
        ReasonCode.QUEUE_FULL,
        ReasonCode.UNSUPPORTED_SCHEMA_VERSION,
        ReasonCode.POLICY_BLOCKED,
        ReasonCode.POLICY_VIEW_MISMATCH,
        ReasonCode.PREPARED_HANDLE_INVALID,
        ReasonCode.PREPARED_HANDLE_EXPIRED,
        ReasonCode.PREPARED_HANDLE_FOREIGN_SCOPE,
        ReasonCode.PREPARED_HANDLE_CONSUMED,
        ReasonCode.SCOPE_MISMATCH,
        ReasonCode.CROSS_CONFIRMATION_MISSING,
        ReasonCode.IDENTITY_UNKNOWN,
        ReasonCode.IDENTITY_MISMATCH,
        ReasonCode.SESSION_EXPIRED,
        ReasonCode.SESSION_GENERATION_CHANGED,
        ReasonCode.SESSION_BUSY,
        ReasonCode.RECOVERY_EXHAUSTED,
        ReasonCode.CANCELLED,
        ReasonCode.BUDGET_EXHAUSTED,
        ReasonCode.DEADLINE_EXCEEDED,
        ReasonCode.CLEANUP_TIMEOUT,
        ReasonCode.INTERNAL_ERROR,
        ReasonCode.SCHEDULER_FAILED,
        ReasonCode.TRANSPORT_NOT_ENTERED,
        ReasonCode.SEND_ACKNOWLEDGEMENT_LOST,
        ReasonCode.CAPTURE_UNAVAILABLE,
        ReasonCode.CAPTURE_EXPIRED,
        ReasonCode.CAPTURE_BINDING_MISMATCH,
        ReasonCode.RESPONSE_LIMIT_EXCEEDED,
        ReasonCode.EVIDENCE_STORE_FAILED,
        ReasonCode.CROSS_EVIDENCE_STORE_FAILED,
        ReasonCode.COMPARISON_INCOMPLETE,
        ReasonCode.COMPARISON_CANARY_FAILED,
        ReasonCode.COMPARISON_CANARY_UNKNOWN,
        ReasonCode.COMPARISON_SAME_RESOURCE_UNKNOWN,
        ReasonCode.COMPARISON_SUBJECTS_UNKNOWN,
        ReasonCode.COMPARISON_OWNER_DATA_UNKNOWN,
        ReasonCode.COMPARISON_CROSS_DATA_UNKNOWN,
        ReasonCode.COMPARISON_DATA_MATCH_UNKNOWN,
        ReasonCode.COMPARISON_REFLECTION_UNKNOWN,
        ReasonCode.COMPARISON_TEMPLATE_UNKNOWN,
        ReasonCode.SOURCE_UNVERIFIED,
        ReasonCode.AUDIT_COMMIT_FAILED,
        ReasonCode.AUDIT_VERIFICATION_UNKNOWN,
        ReasonCode.AUDIT_GAP,
        ReasonCode.RECIPE_MISSING,
        ReasonCode.RECIPE_UNSUPPORTED,
        ReasonCode.RECIPE_NOT_EXPORTABLE,
        ReasonCode.RECIPE_BINDING_MISMATCH,
        ReasonCode.POC_EVIDENCE_INCOMPLETE,
        ReasonCode.POC_VERDICT_UNCONFIRMED,
        ReasonCode.POC_AUDIT_INCOMPLETE,
    }
)

CALL_AUDIT_REASON_CODES: frozenset[ReasonCode] = CALL_AUDIT_FAILURE_REASON_CODES | frozenset(
    {ReasonCode.COMPARISON_CANARY_PASSED}
)
