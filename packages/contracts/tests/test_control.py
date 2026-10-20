"""Validate immutable bindings and the synchronous Policy/Gateway fake seam."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest
from abc2lab_contracts import (
    AccountRef,
    PolicyDecision,
    PolicyDecisionRef,
    PolicyOutcome,
    PolicyPort,
    ReasonCode,
    RequestAttemptRef,
    RequestBinding,
    RequestBindingError,
    RequestPlan,
    RequestPurpose,
    RequestRef,
    RunContext,
    RunRef,
)
from abc2lab_contracts.execution import (
    CaptureAvailability,
    CapturedObservation,
    GatewayPort,
    SendStatus,
)


class FakePolicy:
    """Illustrate Protocol conformance and context mismatch handling, not authorization."""

    def evaluate(self, plan: RequestPlan, ctx: RunContext) -> PolicyDecision:
        has_matching_context = plan.binding.context == ctx
        return PolicyDecision(
            decision_ref=PolicyDecisionRef(value="decision-1"),
            binding=plan.binding,
            outcome=PolicyOutcome.ALLOW if has_matching_context else PolicyOutcome.BLOCK,
            reason_code=ReasonCode(
                value="fixture_allow" if has_matching_context else "context_mismatch"
            ),
        )


class FakeGateway:
    """Model a failed send acknowledgement once, without any real transmission."""

    def __init__(self) -> None:
        self.attempt_count = 0

    def execute(self, plan: RequestPlan, decision: PolicyDecision) -> CapturedObservation:
        decision.validate_binding(plan)
        is_blocked = decision.outcome is PolicyOutcome.BLOCK
        if not is_blocked:
            self.attempt_count += 1
        return CapturedObservation(
            attempt_ref=RequestAttemptRef(value="attempt-1"),
            binding=plan.binding,
            decision=decision,
            observed_at=datetime(2026, 10, 20, tzinfo=UTC),
            send_status=SendStatus.NOT_SENT if is_blocked else SendStatus.UNKNOWN,
            capture_availability=(
                CaptureAvailability.NOT_APPLICABLE
                if is_blocked
                else CaptureAvailability.INDETERMINATE
            ),
            capture_ref=None,
            reason_code=ReasonCode(value="policy_block" if is_blocked else "acknowledgement_lost"),
        )


def test_structural_ports_preserve_binding_and_unknown_without_retry(plan: RequestPlan) -> None:
    policy: PolicyPort = FakePolicy()
    fake_gateway = FakeGateway()
    gateway: GatewayPort = fake_gateway
    decision = policy.evaluate(plan, plan.binding.context)

    observation = gateway.execute(plan, decision)

    assert decision.binding == plan.binding == observation.binding
    assert observation.send_status is SendStatus.UNKNOWN
    assert fake_gateway.attempt_count == 1


def test_context_mismatch_retains_original_binding_and_blocks_attempt(plan: RequestPlan) -> None:
    policy: PolicyPort = FakePolicy()
    fake_gateway = FakeGateway()
    different_context = replace(plan.binding.context, run_ref=RunRef(value="another-run"))

    decision = policy.evaluate(plan, different_context)
    observation = fake_gateway.execute(plan, decision)

    assert decision.binding == plan.binding
    assert decision.outcome is PolicyOutcome.BLOCK
    assert observation.send_status is SendStatus.NOT_SENT
    assert fake_gateway.attempt_count == 0


def test_changed_inputs_invalidate_decision_before_attempt(plan: RequestPlan) -> None:
    binding = plan.binding
    context = binding.context
    assert binding.session is not None
    other_account = AccountRef(value="another-account")
    changed_bindings: list[RequestBinding] = [
        replace(binding, context=replace(context, run_ref=RunRef(value="another-run"))),
        replace(
            binding,
            context=replace(
                context, target_scope_ref=replace(context.target_scope_ref, revision="2")
            ),
        ),
        replace(
            binding,
            context=replace(
                context, authorization_ref=replace(context.authorization_ref, revision="2")
            ),
        ),
        replace(
            binding,
            context=replace(
                context, execution_profile_ref=replace(context.execution_profile_ref, revision="2")
            ),
        ),
        replace(
            binding, context=replace(context, budget_ref=replace(context.budget_ref, revision="2"))
        ),
        replace(binding, request_ref=RequestRef(value="another-request")),
        replace(binding, request_spec_ref=replace(binding.request_spec_ref, revision="2")),
        replace(binding, method="HEAD"),
        replace(binding, purpose=RequestPurpose.AUTHENTICATE),
        replace(binding, session=replace(binding.session, generation=1)),
        replace(
            binding,
            session=replace(
                binding.session,
                session_ref=replace(binding.session.session_ref, value="another-session"),
            ),
        ),
        replace(
            binding,
            account_ref=other_account,
            session=replace(binding.session, account_ref=other_account),
        ),
        replace(binding, session=None),
    ]
    decision = FakePolicy().evaluate(plan, context)
    gateway = FakeGateway()

    for changed in changed_bindings:
        with pytest.raises(RequestBindingError, match="does not match request binding"):
            gateway.execute(RequestPlan(binding=changed), decision)
    assert gateway.attempt_count == 0


@pytest.mark.parametrize("method", ["get", "GET /secret", "GET\n", "", "GÉT"])
def test_invalid_http_method_is_rejected_without_echo(plan: RequestPlan, method: str) -> None:
    with pytest.raises(ValueError, match="^method must be an uppercase HTTP token$"):
        replace(plan.binding, method=method)


def test_anonymous_observation_is_valid_but_cannot_carry_another_account_session(
    plan: RequestPlan,
) -> None:
    anonymous = replace(plan.binding, account_ref=None, session=None)
    assert anonymous.account_ref is None
    with pytest.raises(ValueError, match="session account must match"):
        replace(plan.binding, account_ref=None)
    with pytest.raises(ValueError, match="authentication requires"):
        replace(anonymous, purpose=RequestPurpose.AUTHENTICATE)


def test_reference_types_are_distinct_and_records_are_frozen(plan: RequestPlan) -> None:
    assert len({RunRef(value="same"), RequestRef(value="same")}) == 2
    assert hash(plan) == hash(replace(plan))
    with pytest.raises(FrozenInstanceError):
        plan.binding.context.run_ref.__setattr__("value", "another-run")


@pytest.mark.parametrize("value", ["", " ", "secret\nvalue", "secret\x00value", "secret\x7fvalue"])
def test_invalid_reference_does_not_echo_value(value: str) -> None:
    with pytest.raises(ValueError) as error:
        RunRef(value=value)
    assert (
        str(error.value)
        == "value must be a nonempty token without whitespace or control characters"
    )


def test_revision_and_session_generation_are_validated(plan: RequestPlan) -> None:
    with pytest.raises(ValueError, match="revision must be"):
        replace(plan.binding.request_spec_ref, revision="")
    assert plan.binding.session is not None
    for generation in (-1, True):
        with pytest.raises(ValueError, match="generation must be a nonnegative integer"):
            replace(plan.binding.session, generation=generation)
