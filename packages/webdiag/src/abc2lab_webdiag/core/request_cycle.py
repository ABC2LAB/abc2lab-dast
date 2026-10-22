"""Gateway 준비→정책 평가→실행 cycle을 캡슐화한 전송 단일 경로의 재사용 단위다.

authenticate·identify·observe·access_compare가 모두 이 cycle로 실제 요청을 수행한다.
request_ref는 호출자가 동작마다 미리 발급해 ExecutionRequest에 넣고, 이 함수는 Gateway가
전송 판단·감사의 단일 지점이 되도록 흐름만 조정한다. 원문·캡처 핸들을 다루지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from abc2lab_contracts.execution import AttemptResult, ExecuteRequest, ExecutionRequest
from abc2lab_contracts.ports import GatewayPort, PolicyPort
from abc2lab_contracts.primitives import AttemptSummary, ReasonCode, ResultStatus


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    """한 논리 요청의 실행 결과. attempt가 None이면 prepare 실패로 시도 자체가 없었다."""

    attempt: AttemptResult | None
    reason_codes: tuple[ReasonCode, ...]


async def run_request(
    gateway: GatewayPort, policy: PolicyPort, request: ExecutionRequest
) -> AttemptOutcome:
    """prepare→evaluate→execute를 순서대로 수행하고 알려진 전송 상태를 보존한다.

    prepare가 실패하면 execute하지 않고 시도 없이 사유만 남긴다(가짜 attempt 금지). 정책이
    저장 실패·차단(decision None/block)이어도 execute를 호출해 Gateway가 감사 가능한 not_sent를
    발행하게 한다. 반환을 못 받았다는 이유로 미전송 처리하거나 자동 재요청하지 않는다.
    """
    prepared = await gateway.prepare(request)
    if (
        prepared.status is not ResultStatus.COMPLETE
        or prepared.prepared_handle is None
        or prepared.policy_input is None
    ):
        reason_codes = prepared.reason_codes or (ReasonCode.TRANSPORT_NOT_ENTERED,)
        return AttemptOutcome(attempt=None, reason_codes=reason_codes)
    decision = await policy.evaluate(prepared.policy_input)
    attempt = await gateway.execute(
        ExecuteRequest(
            run_key=request.run_key,
            request_ref=request.request_ref,
            prepared_handle=prepared.prepared_handle,
            decision=decision.decision,
        )
    )
    return AttemptOutcome(attempt=attempt, reason_codes=())


def to_attempt_summary(attempt: AttemptResult) -> AttemptSummary:
    """AttemptResult에서 캡처·인증 신호를 제외한 공개 요약을 만든다."""
    return AttemptSummary(
        run_key=attempt.run_key,
        request_ref=attempt.request_ref,
        attempt_ref=attempt.attempt_ref,
        send_status=attempt.send_status,
        audit_links=attempt.audit_links,
        reason_codes=attempt.reason_codes,
    )
