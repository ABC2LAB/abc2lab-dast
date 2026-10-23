# S1 Report 공개 계약 v0.1 — 구현 제안

> 코드 구현 제안 · 기준 `ABC2LAB/abc2lab-dast` `main` @ `54f9b98` (2026-10-23). `contracts` 담당의 공개 타입/테스트만 포함한다. Report 서비스 구현, 팀 리뷰/병합, 저장/조회·실대상 검증 완료를 뜻하지 않는다.

## 1. 공개 호출과 소유권

- `abc2lab_contracts.report.ReportPort`와 `abc2lab_contracts.ports.ReportPort`: `async build_report(ReportInput) -> ReportResult`.
- Host는 대상 run의 현재 권한을 확인하고, **진단 journal cutoff**의 마지막 확정 Task 업무 revision과 관찰/비교/판정/생산자 기대 범위를 전달한다. `REPORT` Task와 cutoff 이후 운영 revision은 입력에서 제외한다.
- Report 제공자는 매 호출 권한 재검사, 자기 결과 정본, 독립 생산자 감사·Evidence 조회/검증, 무전송 구조화 보고/Markdown 렌더링과 저장 commit을 책임진다. Host/Evidence/Judge/Policy/Gateway DB를 직접 읽지 않는다.
- `ReadContext`는 권한 증명이 아니다. 읽기 권한이 없는 run의 존재를 누설하지 않도록 `FAILED + (NOT_FOUND,)`를 사용한다. 이 명세의 정상 결과 생성자 검증은 원본 provenance/인가/저장 확인이 아니다.

## 2. 요청·응답 스키마

| Record | 필드 및 계약 |
|---|---|
| `ReportInput` | `run_key, context, tasks, observations, comparisons, verdicts, audit_expectations`; 전부 필수, 원문/비밀/임의 재현 코드 없음 |
| `AuditExpectation` | `producer, first_sequence=1, last_sequence: int\|None, expected_event_refs, request_refs, attempt_refs`. `last_sequence=0`은 정상 봉인된 빈 journal과 빈 기대 목록에만 사용. 미봉인/조회 불명은 `None` |
| `AuditGap` | `producer, request_ref?, attempt_ref?, event_ref?, reason_code`; 읽지 못한 producer도 등록 기대 목록에서 삭제하지 않음 |
| `CaseLimit` | `case_ref, status, stored_evidence_refs, comparison_ref?, reason_codes`; 판정 전 실패/부분 비교 보존 |
| `DiagnosisReport` | `run_key, report_ref, verdicts, send_counts, incomplete_task_refs, audit_completeness, audit_gaps, evidence_refs, comparison_refs, comparison_limits, pocs, reason_codes` |
| `PocStep` | `sequence, action, account_ref, identity_ref?, request_recipe?, evidence_ref?`; action은 네 가지 고정형 |
| `PocReport` | `case_ref, verdict_ref, state, replay_status=not_run, comparison_ref?, steps, evidence_refs, audit_links, reason_codes`; 각 판정 하나에 상태 하나 |
| `ReportResult` | `run_key, status, report?, reason_codes`; `COMPLETE`/`PARTIAL`은 저장된 report 보존, `FAILED`는 report 없음 |

## 3. 신뢰·결과 경계

- Report는 등록 producer별 고정 기대 event/request/attempt, `1..terminal_sequence`, 봉인/현재 snapshot, event binding과 source receipt를 대조한다. 미확인 `last_sequence=None`을 0건으로 간주하거나 실제 반환된 행에서 기대 집합을 역산하지 않는다.
- Host의 공개 `TaskSummary`만으로 `task.v1` fingerprint를 재계산할 수 없다. Report는 고정 cutoff 범위의 Host 원본 audit binding과 `AuditVerifier.verify_committed` 결과를 대조하는 **Host attestation**을 사용하고, 독립 내용 재계산이라고 표시하지 않는다.
- 전송 `SENT`, `NOT_SENT`, `UNKNOWN`은 별도 유지한다. **전체 run 집계**는 Host가 발행한 각 고유 attempt_ref의 확정 상태와 감사 검증에 근거하며, 조회 실패를 0건/`NOT_SENT`로 채우지 않는다.
- `CONFIRMED`와 `PocState.DOCUMENTED`는 별개다. documented는 유효하고 저장된 네 단계/두 계정/동일 객체 GET recipe/identity/evidence/감사 연결의 **원 실행 문서화**이며 재현 성공이 아니다. 실제 재실행은 수행하지 않으며 `PocReplayStatus.NOT_RUN`으로 표시한다.
- CONFIRMED의 필수 PoC가 `INCOMPLETE`/`UNAVAILABLE`, 감사가 UNKNOWN, 진단 Task가 일부 미완료인 경우 저장된 보고서를 포함한 `ReportResult.PARTIAL`을 반환한다. SUSPECTED/UNDECIDABLE의 PoC가 incomplete라는 사실만으로 보고 전체를 PARTIAL로 만들지 않는다.
- `FAILED`는 완료 artifact 없음(권한/조회/저장/취소/원본 검증 실패 등), `PARTIAL`은 유효한 저장 보고서와 구체 제한 이유가 있음, `COMPLETE`는 보고 생성·저장과 요구 완결 조건이 확인됨을 나타낸다. 취약점 발견 여부와 다르다.
- 취소는 `CancelledError`를 삼키지 않고 전파한다. 원문 응답·인증 값·캡처 핸들·HMAC 키를 공개 record·리포트에 넣지 않는다.

## 4. 서비스 구현에서 반드시 확인할 사항

- 이 패치의 immutable record 생성자 검증은 **저장소 감사 검증이나 보고서 commit을 구현하지 않는다**. `report` 담당이 Evidence/Audit Reader/Verifier·저장 어댑터를 주입하고 의미 검증/멱등·중단 테스트를 작성한다.
- Confirmed/Documented 검사에는 `PocStep`의 identity_ref와 저장된 identity 근거, 동일 case/operation/resource/계정/generation/recipe source, 진짜 producer receipt·감사 연속성을 재확인한다. 같은 문자열 ref라는 이유만으로 신뢰하지 않는다.
- 현재 독립 PR에서는 새로운 공개 실행 포트·Gateway 재전송 API·생산자 fingerprint 스키마를 만들지 않는다. `ReportPort`가 추가되면서 **S1 명세의 설계상 마지막 공개 포트 하나**를 코드로 구현하는 것이다.
- 리뷰: Report 제공자 최민준, Host 소비자 이경준, 공유 계약 이동찬. 적용 전 `uv run --no-project --python 3.13.15 scripts/dev.py check contracts` 및 `check all` 실행.

근거: [S1 API 상세 규격](s1-api-spec.md#9-진단-보고), [PoC 출력 설계](poc-report-design.md), [Host 공개 계약](host-public-contract-v0.1.md).
