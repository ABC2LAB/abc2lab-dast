# S1 Host 공개 계약 v0.1 — 타입·상태·감사·구현 인수 기준

> **검토용 스키마 변경 제안** · 기준 `ABC2LAB/abc2lab-dast` `main` @ `0a13f6e` (2026-10-23). 계약 구현은 `contracts` 담당, 실제 Host 서비스는 Host 담당(이경준)이 구현한다. `Report` 공개 계약은 별도 PR. 이 문서는 팀 합의/서비스 구현/실제 HTTP 검증의 완료를 뜻하지 않는다.
>
> 이전 대화의 H-1~H-30 **정확한 원문 전체가 복원되지 않았다**. 아래 규칙은 확인 가능한 S1 명세와 2026-10-23 사용자가 채택한 추천안을 통합한 **새 설계 기준**이다. 번호 N-01~N-30은 이 문서 전용 추적 번호이며, 옛 H 번호와 1:1로 대응한다고 주장하지 않는다.

설계 입력은 위 기준 커밋이며, 이번 구현의 기준은 PR #44까지 병합된 `main` `f649487`이다. `feat/contracts-host-public`에서 검토용 변경을 구현하며 실제 Host 서비스와 공유 계약의 검증을 구분한다.

## 1. 역할 경계·공개 인터페이스

- 공개 `HostPort`: `start_run(StartRunRequest) -> StartRunResult`, `get_status(GetRunStatusRequest) -> GetRunStatusResult`, `stop(StopRunRequest) -> StopReceipt`, 모두 `async`. `abc2lab_contracts.ports.HostPort`로도 노출한다.
- 세 요청 모두 필수 `ReadContext(caller_ref, authorization_ref)`를 포함한다. 여기서는 기존 공유 타입을 범용 호출자·인가 참조 맥락으로 재사용하며, `Read`라는 이름이 읽기 전용 권한이나 쓰기 권한을 부여하지 않는다. `app`이 인증한 식별자는 **권한 자체가 아니며**, Host는 주입된 신뢰된 authorizer/registration reader에서 **매 호출 시** 시작·조회·정지 각각에 필요한 현재 권한, 조직·대상·환경 및 run 접근 범위를 재검증한다. constructor는 인증 증거를 검증하지 못한다.
- 다른 조직이나 조회 권한 없는 run에 대한 `get_status`·`stop`은 존재하지 않는 run과 **동일하게** `FAILED + (NOT_FOUND,)`로 공개한다. `GetRunStatusResult.reason_codes`에는 `ACCESS_DENIED`를 허용하지 않으며, `NOT_FOUND`를 다른 사유와 섞지 않는다. 조회 권한은 있으나 정지 권한이 없다면 **stop 결과에서만** `ACCESS_DENIED`가 가능하다. 작업 실행 중 실제로 발생한 거부는 중첩 TaskSummary의 사유로 보존하며 run 조회 권한 거부와 혼동하지 않는다. 내부 운영 감사는 실제 거부 원인을 제한적으로 기록할 수 있지만 외부로 유출하지 않는다.
- Host ID: `RunKey.run_ref`, `task_ref`, `case_ref`. WebDiag `request_ref`; Gateway `attempt_ref`. Host는 요청 recipe·쿠키·계정 자격 증명·원문 캡처/응답·GT를 API/감사 payload로 복사하지 않는다. 실행 허용 결정은 Policy/Gateway에서 독립 확인한다.
- `start_run`은 검증된 `registration_ref`와 caller-generated `submission_ref`만 받으며 임의 URL/비밀번호를 받지 않는다. Host는 서비스에 주입된 등록 정본에 대해 속성·버전·정책 snapshot을 검증한다.
- Host 내부 `plan/submit/lease/complete/cancel`, worker 1, finite queue, Event/TaskGroup supervision, CAS, Outbox, journal storage는 공유 Port가 아니다. 실제 구현은 별도 Host PR.

| 공개 record | 필드 (모두 필수, `None` 허용은 타입에 표시) |
|---|---|
| `StartRunRequest` | `organization_ref, target_ref, environment_ref, registration_ref, submission_ref, context` |
| `RunHandle` | `run_key: RunKey, created_at: UtcTime` |
| `StartRunResult` | `status: ResultStatus, run: RunHandle?, reason_codes` |
| `GetRunStatusRequest` | `run_key: RunKey, context: ReadContext` |
| `GetRunStatusResult` | `run_key, status: ResultStatus, run_status: RunStatus?, reason_codes` |
| `RunStatus` | `run_key, revision: Revision, snapshot_revision: Revision, state: RunState, tasks: tuple[TaskSummary,...], send_counts: SendCounts, audit_completeness, operations_audit_completeness, reason_codes` |
| `TaskSummary` | `task_ref, revision: Revision, kind, case_ref: Ref?, state, attempt_summaries: tuple[AttemptSummary,...], reason_codes` |
| `SendCounts` | `sent:int, not_sent:int, unknown:int` (bool 불가, 비음수) |
| `StopRunRequest` | `run_key, context` |
| `StopReceipt` | `run_key, status, stop_state, requested_at: UtcTime?, reason_codes` |

`RunStatus.revision`은 `RunAuditRecord.revision`과 같은 **run 업무 revision**이다. `TaskSummary.revision`은 개별 task의 현재 불변 업무 revision이다. `RunStatus.snapshot_revision`은 tasks·send_counts·두 감사 completeness·reason_codes를 포함한 공개 상태 전체의 일관 snapshot revision이다. Host는 run마다 안정적인 snapshot revision을 배정하고, 공개 내용이 바뀔 때만 증가시키며, 내용이 같으면 반복 조회에서 재사용한다. 업무 revision과 snapshot revision을 서로 대신 사용하지 않는다. Host는 한 read transaction/snapshot에서 모든 task와 전송 집계를 가져오며 서로 다른 시점 자료를 임의로 합성하거나 100개 등 임의 상한으로 tasks를 생략하지 않는다. 일관된 snapshot/version을 만들 수 없으면 `REVISION_UNAVAILABLE`을 포함한 `FAILED + None`을 반환한다. 이 실패 사유는 다른 실제 실패 사유와 함께 보존할 수 있다. `PARTIAL`도 버전이 있는 일관된 부분 snapshot을 확보한 경우에만 가능하며 한도·조회 실패의 사유를 보존한다. 일부 결과를 전체인 것처럼 COMPLETE로 반환하지 않는다. `case_ref`는 사례에 귀속된 작업에 지정하고 collect 등 귀속되지 않은 작업에서 `None`이 가능하다. case↔task/등록 정본 검증은 Host 책임이며 타입 검사만으로 보장되지 않는다.

## 2. 호출 결과와 실패 분류

| API | 허용 결과 | 규칙 |
|---|---|---|
| start | `COMPLETE + RunHandle + ()` | 수락 정본·중복 방지·큐 복구 의무가 commit된 경우에만 확인. *Run 실행 완료 아님* |
| start | `PARTIAL + None + reasons` | 수락 commit 여부 불명. 새 run/새 작업을 만들지 않고 기존 submission과 정본/outbox를 재조정 |
| start | `FAILED + None + reasons` | 수락하지 않았음이 확인된 거절 (`QUEUE_FULL`, `IDEMPOTENCY_CONFLICT`, 등록/인가 오류 등) |
| get_status | `COMPLETE + RunStatus + ()` | 현재 권한 확인된 일관·전체 상태 snapshot |
| get_status | `PARTIAL + RunStatus + reasons` | tasks·전송 집계 등 상태 조회가 일부만 성공해, 유효한 version이 있는 일관된 부분 snapshot과 조회 누락 사유를 반환 |
| get_status | `FAILED + None + reasons` | 조회 실패, 무권한/없는 run 모두 `NOT_FOUND` 공개 |
| stop | `COMPLETE + REQUESTED + requested_at` | 취소 의도 commit 수락. 실제 중지·lease/capture 회수 아님 |
| stop | `COMPLETE + STOPPED + requested_at` | 이전에 수락된 취소의 실행/cleanup 종료가 확인됨. `requested_at`은 최초 수락 시각 |
| stop | `COMPLETE + NOT_APPLICABLE + None` | 기존 취소 수락 없이 `COMPLETED`/`FAILED`로 끝났거나, `FINALIZING`에 진입해 신규 취소를 수락하지 않는 경우. FINALIZING 자체는 terminal이 아님 |
| stop | `PARTIAL + UNKNOWN + requested_at? + reasons` | 취소 intent commit 또는 cleanup 종료 여부 미확정. 해당 시각이 신뢰 가능한 경우에만 보존 |
| stop | `FAILED + UNKNOWN + None + reasons` | 명백한 거부/조회 실패, 요청 시각을 만들지 않음 |

**상태 조회의 두 축:** 바깥 `GetRunStatusResult.status`는 **조회 결과의 완성도**, 안쪽 두 `audit_completeness`는 **Run의 감사 검증 상태**다. 권한 확인과 전체 snapshot 조회가 성공했다면 감사가 UNKNOWN이어도 `COMPLETE + RunStatus + ()`로 반환하며, 감사 미확인 사유는 `RunStatus.reason_codes`에 보존한다. 진행 중이거나 실패한 Task가 있다는 사실도 바깥 PARTIAL의 사유가 아니다. 바깥 PARTIAL은 조회 자체가 일부 실패해 일관된 부분 snapshot만 제공할 때 사용하고 누락·조회 실패를 바깥 사유에 남긴다. 일관된 snapshot/version조차 확보하지 못하면 `REVISION_UNAVAILABLE`을 포함한 `FAILED + None`이다. 소비자는 먼저 바깥 status로 조회 범위를 확인하고, 안쪽 Run/Task 상태·두 감사 필드로 실행 및 감사 상태를 표시한다. 조회 COMPLETE를 감사 완료나 진단 안전성으로 해석하지 않는다.

`COMPLETE`인 stop은 요청 수락·정리 종료·취소 적용 대상 아님 중 어느 사실이 확인됐는지 `stop_state`로 구분하며 전송 회수 보장은 아니다. 권한을 먼저 확인한 뒤 기존 cancellation intent를 조회한다. 이미 수락된 취소가 있으면 최초 `requested_at`을 유지하고 `REQUESTED`를 반복 반환하며 cleanup 확인 뒤에만 `STOPPED`로 바꾼다. 기존 취소가 없을 때 `FINALIZING`의 새 stop은 `NOT_APPLICABLE`을 반환한다. 이 결정은 run CAS/원자 decision으로 concurrent stop과 조정한다. `NOT_APPLICABLE`은 stopped로 오해할 수 없으며 `STOPPED`는 cleanup 완료를 입증한 경우에만 반환한다. 불확실하면 `PARTIAL + UNKNOWN`에 신뢰 가능한 시각만 보존하고, 상태를 되돌리거나 진단 journal을 다시 열지 않는다. `CancelledError`는 정리/기록한 뒤 전파하고 정상 실패 결과로 삼키지 않는다.

**시작 사유의 폐쇄 허용목록:** `host.START_REJECTION_REASON_CODES`는 `CONFIGURATION_MISSING`, `NOT_FOUND`, `ACCESS_DENIED`, `SCOPE_MISMATCH`, `IDEMPOTENCY_CONFLICT`, `QUEUE_FULL`, `UNSUPPORTED_SCHEMA_VERSION`, `SOURCE_UNVERIFIED`다. `FAILED`의 모든 사유가 이 집합에 있어야 한다. `host.START_UNCERTAINTY_REASON_CODES`는 `AUDIT_COMMIT_FAILED`, `AUDIT_VERIFICATION_UNKNOWN`, `AUDIT_GAP`, `REVISION_UNAVAILABLE`, `INTERNAL_ERROR`, `DEADLINE_EXCEEDED`, `SNAPSHOT_EXPIRED`이며 `PARTIAL`의 모든 사유가 이 집합에 있어야 한다. 두 결과 모두 사유가 하나 이상 필요하고 run은 None이다. 두 역할의 혼합이나 미등록 사유는 거부하므로 `QUEUE_FULL`을 앞에 붙여 감사 불명을 FAILED로 숨길 수 없다. 새 ReasonCode도 명시적으로 이 경계에 등록하기 전에는 시작 실패/부분 결과에 사용할 수 없다. 이 집합은 Host 시작 호출 전용이며 다른 서비스의 사유 분류를 변경하지 않는다.

사유 이름은 실제 수락/거절의 증명이 아니다. Host는 기존 submission 정본을 먼저 대조하고 수락되지 않았음이 확인된 경우에만 FAILED를 반환한다. 저장·commit·수락 확인이 불명확하면 기존 키로 재조정하며 새 submission이나 대상 요청으로 보충하지 않는다. GetStatus의 미존재/무권한은 정확히 `FAILED + None + (NOT_FOUND,)`로 같게 표현하고, 현재 조회 권한을 확인한 뒤 발생한 실제 저장·revision 조회 오류는 별도 실패 사유를 보존한다.

**시작 멱등성:** key `(organization_ref, submission_ref)` 고정. 동일 등록 입력으로 재호출하면 현재 권한을 재검증한 뒤 최초 수락의 동일 `RunKey`와 `created_at`을 반환. 같은 key에 서로 다른 `target_ref / environment_ref / registration_ref`는 `IDEMPOTENCY_CONFLICT`. 수락 commit 직후 응답 유실·worker enqueue 실패도 복구 정본을 먼저 조회하며 두 번째 수락이나 추가 대상 전송을 만들지 않는다. `ReadContext`의 token 문자열 변화가 곧 업무 submission 충돌은 아니다.

## 3. Run/Task 생명주기

`RunState`: `QUEUED → RUNNING → FINALIZING → COMPLETED|FAILED`, 취소 시 `QUEUED|RUNNING → STOPPING → FINALIZING → STOPPED|FAILED`. 실패한 작업이 있어도 보고가 저장되고 전체 워크플로가 정상 종료됐다면 `COMPLETED` 가능. `FAILED`는 Host 실행/조립 자체의 실패를 의미하며 진단에서 취약점을 찾지 못했다는 뜻이 아니다. 재시작 복구·cleanup timeout 등 실패 경로는 상태+사유로 명시한다. terminal `COMPLETED/FAILED/STOPPED` 이후 상태 회귀/재전송 금지. 모든 실행 task가 더 이상 QUEUED/RUNNING이 아니어야 FINALIZING과 terminal에 진입 가능하다. 운영 감사 완전성과 진단 감사 완전성은 **둘 다 UNKNOWN인 채 terminal 상태가 될 수 있다**.

`TaskKind`: `COLLECT/OBSERVE/COMPARE/JUDGE/REPORT`. `TaskState`: `QUEUED/RUNNING/COMPLETE/PARTIAL/FAILED/CANCELLED`; 부분/실패/취소는 사유 필수, 이미 존재하는 `AttemptSummary`/감사 링크/근거는 보존한다. 성공한 보고 생성과 요청 전송 여부는 독립적이다. 현재 revision의 의미를 수정하려면 **새 불변 revision**. 작업 실패·취소가 무관한 다른 run 또는 작업까지 취소되도록 구현하지 않는다.

`FINALIZING`은 진단·보고 task가 모두 끝난 뒤 최종 Run 상태 저장과 bounded operations audit 확인을 수행하는 단계다. 순서는 `RUNNING/STOPPING`에서 진단 작업·생산자 소유 정리 종료→Host/producer 진단 journal 봉인 및 고정 prefix 확정→Report task 생성·실행·완료→`FINALIZING`→terminal이다. Report task 생성과 모든 전이(`QUEUED/RUNNING/COMPLETE/PARTIAL/FAILED/CANCELLED`), 그리고 cutoff 이후의 모든 Run/Task revision은 별도 **private operations audit** 범위다. 따라서 **보고 Task가 RUNNING인 동안에는 `FINALIZING`으로 전이하지 않고** 기존 `RUNNING` 또는 `STOPPING` 상태를 유지한다. `FINALIZING`에서 audit gap을 관측해도 terminal 전이 자체를 영원히 금지하지 않는다. 진단 journal은 seal 이후 다시 열거나 Report lifecycle을 추가하지 않는다.

중요: `RunStatus`가 단일 snapshot이라도 진단 감사·운영 감사 completeness는 snapshot의 **관찰값**이다. UNKNOWN→COMPLETE로 검증 결과가 갱신될 수 있으며 Run 생명주기 불필요 회귀를 만들지 않는다. `revision`은 업무 revision, `snapshot_revision`은 전체 공개 snapshot version이며 둘 다 명시한다. 상태 snapshot revision과 진단 journal sequence·운영 audit sequence·개별 task revision은 별개다.

## 4. 진단 감사와 운영 감사 — 독립 경계

- `audit_completeness`: Gateway/Policy/WebDiag/Evidence/Judge/Host 등 producer의 진단 evidence/intent/attempt/판정/Run·Task journal을 **등록된 전 생산자** 기준으로 확인. expected ref 누락, prefix/중간 sequence gap, 미봉인, snapshot expiry, 검증 reader 실패, reference 충돌 중 하나라도 있으면 `UNKNOWN`. `UNKNOWN`을 `not_sent`나 빈 결과로 바꾸지 않는다.
- `operations_audit_completeness`: 현재 `RunStatus` 조회/snapshot 경계에서 확인한, 호출 허용/거부, 시작 재호출·멱등 충돌, stop 의도, CAS 충돌, recovery/cleanup 등 **Host 제어 평면** 운영 감사 기록의 연속성/저장 확인 상태. 값은 해당 관찰 범위에 대해 `COMPLETE` 또는 `UNKNOWN`이며 미래 전체 control-plane lifetime이 영구 봉인됐다는 뜻이 아니다. 이후 `get_status`/`stop`/recovery가 새 operations record를 추가할 수 있고, 진단 journal을 다시 열지 않는다. 진단 로그가 온전하더라도 독립적으로 UNKNOWN 가능하며, 운영 감사 기록의 원문·권한 비밀은 공개하지 않는다.
- 두 감사 상태는 독립적으로 `COMPLETE` 또는 `UNKNOWN`. Host 운영 로그와 진단 journal의 저장소·sequence·봉인 경계를 혼동하지 않는다. 운영 감사 미확정은 숨기지 않고 RunStatus에 드러내되 내부 거부 이유는 공개하지 않는다.
- 등록 생산자 집합은 app 주입 registry에서 고정하며 Host도 포함한다. Host는 진단 cutoff 전에 각 서비스 반환에 있는 전체 request/attempt/event/receipt ref의 기대 집합을 **감사 조회 전에** 조립하고, 모든 진단 producer journal을 봉인한 뒤 고정된 prefix 수위를 전달한다. 조회 실패한 생산자를 제외하거나 실제 읽힌 행으로 기대 집합을 역생성하지 않는다. `AuditExpectation.last_sequence=None`은 미확정, `0`은 봉인된 빈 journal에만 가능하다. Report는 이 고정된 sealed diagnostic prefix만 검사하며 Report task 자신과 cutoff 이후 Run/Task revision을 `ReportInput.tasks`나 진단 expectation에 포함하지 않는다.
- Host는 보고서에 원본 production AuditEvent가 필요한 경우 주입된 공개 reader/receipt verify를 사용하고 타 모듈의 비공개 DB 직접 읽기를 금지한다. Report는 실제 네트워크 재전송으로 누락을 보완하지 않는다.
- 실행/producer 쓰기 종료와 **감사 완전성 확인은 서로 다른 조건**이다. 진단 journal cutoff 이전의 prefix가 sealed여도 operations audit는 독립 sequence/scope로 기록·검증하며 진단 prefix에서 추론하지 않는다. Report task 및 post-cutoff Run revisions는 operations audit에만 남긴다. 두 audit 모두 실제 저장 검증 전에는 COMPLETE로 추론하지 않는다. 진단 또는 운영 감사가 UNKNOWN이어도 Run은 COMPLETED/FAILED/STOPPED terminal로 끝날 수 있지만 알려진 공백은 reason_codes/Report partial로 남긴다.

## 5. Run/Task 불변 감사 records와 fingerprint

- `RunAuditRecord(run_key, registration_ref, submission_ref, revision, state, created_at, updated_at, reason_codes)`.
- `TaskAuditRecord(run_key, task_ref, revision, kind, case_ref, state, attempt_summaries, created_at, updated_at, reason_codes)`.
- exact `frozen` dataclass 타입, UTC 정규화, Revision 양수, `updated_at >= created_at`; 상태에 필요한 reason과 일치해야 한다. 이 두 record는 **업무 상태 revision**을 기술하지 진단·운영 감사 completeness의 조회 파생값을 fingerprint에 중복 저장하지 않는다.
- 기존 `abc2lab_contracts.fingerprint`의 `canonical-json.v1`만 사용하며 `record_kind=run/task`, `schema_version=run.v1/task.v1`. `record_ref=run_key.run_ref/task_ref`; `record_revision=revision`. AuditReceipt `sequence`와 업무 revision은 별개. vector는 `docs/examples/host-fingerprint-vectors.json`에 봉인한다.
- `normalize_reason_codes`: value 오름차순 정렬·동일 중복 제거. `normalize_attempt_summaries`: **`attempt_ref` 기준 오름차순**, 동일 내용 중복 제거; 각 Attempt의 `audit_links`는 `(producer,event_ref)` 순, reason도 정규화. **같은 attempt_ref에 다른 request_ref 또는 다른 업무 필드가 있으면 충돌**로 거부하고 Host가 비공개 감사 gap/UNKNOWN으로 기록한다. 단순 RequestRef 기준으로 구분해 이중 집계하지 않는다.
- 공개 `TaskSummary`는 입력 tuple 순서를 보존하며 감사용 정렬을 강제하지 않는다. `attempt_ref` 중복은 거부한다. 반면 `TaskAuditRecord`는 결정적인 fingerprint 입력이므로 Host가 생성 전에 `normalize_attempt_summaries`와 `normalize_reason_codes`를 명시적으로 적용한다. 공개 요약의 정렬까지 강제하는 규칙은 아니며, 공개 tuple 순서를 바꾸면 관찰 가능한 snapshot 내용도 바뀌므로 `snapshot_revision` 규칙은 적용한다.
- 생성자 및 typed fingerprint는 미정규화된 Run/Task 감사 record를 거부한다. 서로 다른 의미를 같은 revision/ref 아래 재기록할 수 없다. heartbeat, 단순 정렬 차이나 journal 조회만으로 업무 revision을 불필요하게 증가시키지 않는다.
- Host service가 `AuditRecordBinding(RUN/TASK)`·`AuditReceipt`를 저장된 실제 payload와 비교해야 하며, 호출자가 준 digest나 receipt 사본만으로 VERIFY 완료를 주장할 수 없다.

## 6. Host 구현 및 인수 테스트 의무 (contracts 외)

- Start: 단일 ACID 수락 transaction에 submission 멱등 인덱스·run initial state·audit/outbox obligation을 저장하고 commit 확인 뒤 enqueue. commit/응답 손실이면 같은 key로 reconcile, 단순 재전송 금지. 큐 포화는 **확정 거절**일 때만 QUEUE_FULL.
- Task 변경: 진단 cutoff 이전의 진단 task 변경은 Task CAS + 새 불변 TaskAuditRecord + 진단 감사 Outbox를 동일 transaction에 둔다. REPORT task 전체 생명주기와 cutoff 이후 Run/Task revision은 private operations audit obligation과 원자 commit한다. Run/Task 동시 변경(stop/terminal)은 Run CAS + Task CAS + 각 기록에 맞는 감사 obligations를 원자 commit한다. CAS 실패한 옛 실행이 새 작업을 발행하거나 이미 봉인한 진단 journal에 기록할 수 없어야 한다.
- Journal: outbox는 event_ref/fingerprint를 고정한 채 idempotent commit/재검증. 실제 journal sequence gaps는 조용히 건너뛰지 않음. Host 운영 감사의 완전성은 별도 추적. commit 실패를 COMPLETE라고 주장하지 않음.
- Stop: 즉시 제어 경로에서 취소 intent를 정본 기록하고 신규 queue allocation/transport를 차단. 기존 transport에 진입한 Attempt는 `SENT`/`UNKNOWN` 상태 그대로. cleanup lease/capture 완료까지 `STOPPED` 금지. worker `join`/empty queue는 실제 정리/봉인의 증명이 아님.
- Read: Host `get_status/stop`은 막힌 transport semaphore/worker를 기다리지 않고 응답하며 같은 run/task revision snapshot 읽기. ACL 재검증/스코프 은닉은 fake auth로 검증.
- 존재 은닉 인수: 같은 RunKey·ReadContext 요청에 대해 run이 없는 저장소와 run이 있지만 조회 무권한인 저장소를 각각 구성하고, 실제 Host handler의 공개 결과가 모두 `FAILED + None + (NOT_FOUND,)`로 같은지 검사한다. 실제 원인은 private operations audit에만 보존한다. 이번 생성자 테스트는 이 표현과 잘못된 사유를 검사하며, 실제 ACL 분기·저장소 동작을 검증한 것은 아니다.
- Integration: no-send S1 fake에서 두 번 start, 결과 유실, 큐 포화, 2 concurrent stop, CAS 충돌, partial 보고서, 원본 시도 보존, 진단/운영 감사 독립 UNKNOWN, shutdown/recovery를 시험. 실제 HTTP/영속 감사·Gate D-0는 별도 검증 필요.

## 7. 변경 추적/검수 체크리스트 — **신규 N 번호**

| 번호 | 요구사항 | 검증 책임 |
|---|---|---|
| N-01 | 세 API 요청 모두 ReadContext 필수 | contracts 생성자 |
| N-02 | 조회·중지 없는 Run과 비인가 Run 동일 외부 NOT_FOUND | Host 서비스 |
| N-03 | 최초/반복 호출마다 권한 현재성 재검증 | Host 서비스 |
| N-04 | `(org, submission_ref)` 최초 정본 고정 | Host 서비스 |
| N-05 | 같은 키·다른 등록 입력은 IDEMPOTENCY_CONFLICT | Host 서비스 |
| N-06 | 수락 commit 미확정은 PARTIAL이고 중복 enqueue 금지 | Host 서비스 |
| N-07 | Stop.REQUESTED는 cleanup 완료 아님 | contracts + Host |
| N-08 | 기존 취소 수락이 없고 취소 적용 대상이 아닌 FINALIZING/terminal run의 stop은 NOT_APPLICABLE | contracts + Host |
| N-09 | 요청 없던 stopped/확정 실패에 가짜 requested_at 금지 | contracts |
| N-10 | 진단 journal 봉인 뒤 Report를 생성하고, 보고 Task까지 종료된 뒤 FINALIZING에 진입 | contracts + Host |
| N-11 | terminal 상태 회귀/다시 전송 금지 | Host 서비스 |
| N-12 | partial Report가 있어도 Run COMPLETED 가능 | contracts + Host |
| N-13 | Run 업무 revision과 별도 snapshot_revision으로 조회 Run/Task 일관 스냅샷 식별 | contracts + Host |
| N-14 | TaskSummary.case_ref·revision 보존 | contracts |
| N-15 | 전체 Task 및 이미 있던 Attempt 보존 | contracts + Host |
| N-16 | 서로 다른 Task의 시도 중복 집계 검출 | Host 서비스 |
| N-17 | unknown 전송을 not_sent로 낮추지 않음 | Host + Report |
| N-18 | 진단 감사 vs 운영 감사 분리, Report는 sealed diagnostic prefix만 검증 | contracts + Host |
| N-19 | 실행/cleanup 종료와 감사 COMPLETE 분리, cutoff 이후 lifecycle은 operations audit | contracts + Host |
| N-20 | 기대 producer 목록은 reader 조회 전에 고정 | Host 서비스 |
| N-21 | 누락/미봉인은 last_sequence=None; Report는 cutoff prefix만 읽음 | Host + Report |
| N-22 | 진단 감사 prefix/sequence gap UNKNOWN | Host + Report |
| N-23 | Run/Task frozen revision 기록과 정확한 감사 binding | contracts + Host |
| N-24 | 신규 revision과 Outbox를 원자 commit | Host 서비스 |
| N-25 | Run+Task CAS는 한 transaction으로 조정 | Host 서비스 |
| N-26 | 같은 event_ref idempotent 재조정 | Host 서비스 |
| N-27 | attempt_ref 단독 기준 정렬·중복·충돌 판정 | contracts + Host |
| N-28 | 업무 record type/schema별 정확한 canonical fingerprint | contracts |
| N-29 | vector 고정 bytes/hash 및 타입 변조 거부 | contracts |
| N-30 | 무전송 통합과 실제 HTTP 준비 판정을 구분 | app + Host + Gateway |

위 책임 표를 구현 범위로 읽을 때 다음을 구분한다. 현재 contracts PR에서 다루는 지역 범위는 N-01의 요청 `ReadContext` 구조, N-07~N-10의 stop/state 조합에 대한 생성자 불변식, N-13~N-15의 run 업무 revision·`snapshot_revision`·보존 구조, N-18~N-19의 두 completeness 값과 진단/운영 범위 보존, N-23의 frozen audit record 형태, N-27의 `attempt_ref` 정규화·충돌 표현, N-28~N-29의 typed fingerprint와 vector 검증이다. 이 항목의 계약 테스트는 타입·필드·상태 조합·정규 bytes/digest의 지역 정합성만 확인하며, 실제 권한·저장 commit·동시성·감사 원본과 binding의 일치를 증명하지 않는다.

Host 서비스 인수 범위는 N-02~N-06, N-11~N-12, N-16~N-17, N-20~N-22, N-24~N-26과 N-03·N-04·N-05의 매 호출 권한/멱등 동작이다. N-07~N-10, N-13~N-15, N-18~N-19, N-23, N-27은 contracts 타입을 소비하면서 실제 transaction·CAS·reader·cleanup·감사 저장과 함께 재검증해야 한다. 특히 진단 cutoff 전 seal, Report 전체 lifecycle 및 post-cutoff Run revision의 operations audit 기록, 동일 snapshot 재사용/변경 시 증가, FINALIZING stop race의 원자 결정을 인수 테스트한다. N-30은 app·Host·Gateway의 무전송 통합과 실제 HTTP 준비 판정을 분리하는 인수 항목이다. 따라서 현재 문서와 구현 제안은 Host 서비스·Report 구현 완료, 실제 DB/HTTP 검증, 팀 합의를 주장하지 않는다.

### 7.1 2026-10-23 리뷰 반영 결정

- 진단 journal은 Report task를 만들기 전에 봉인한다. Report의 `AuditExpectation`은 registry에서 고정한 **sealed diagnostic prefix**만 검사하며, Report task 자체의 생성·전이와 cutoff 이후 Run/Task revision은 별도의 private operations audit에 기록한다. `ReportInput.tasks`는 cutoff 시점에 존재하는 진단 task만 포함하고 Report task lifecycle 자체는 포함하지 않는다. 공개 `RunStatus.tasks`에는 Report task를 포함한 모든 task를 유지한다.
- operations audit는 진단 journal과 독립 sequence/scope를 가지며, 진단 prefix나 큐 상태에서 COMPLETE를 추론하지 않는다. `operations_audit_completeness`는 각 조회 snapshot에서 확인된 bounded scope만 말하며 미래 제어 평면 전체의 완료를 약속하지 않는다. 실제 저장 검증은 Host 서비스 인수 범위다. 진단 journal은 seal 후 다시 열지 않고, cutoff 이후 새 대상 작업을 발급하지 않는다. RunState가 Report 중 `RUNNING`/`STOPPING`으로 남아 있어도 이 cutoff 규칙은 변하지 않는다.
- `RunStatus.revision`은 RunAuditRecord와 같은 업무 revision이다. `snapshot_revision`은 전체 공개 상태의 안정적 일관 version이며, 보이는 내용이 바뀔 때 증가하고 동일 read에서는 재사용한다. 이를 만들 수 없으면 `REVISION_UNAVAILABLE`을 포함한 FAILED/None을 반환한다. PARTIAL도 유효한 snapshot_revision이 있는 일관된 부분 snapshot일 때만 허용한다. `run.v1`/`task.v1` payload와 vectors는 이 구분으로 변경하지 않는다.
- stop은 항상 authorization을 먼저 확인하고 기존 cancellation intent를 우선 확인한다. 기존 intent가 있으면 최초 시각을 보존하고 `REQUESTED`를 반복하며 cleanup 확인 뒤 `STOPPED`가 된다. 기존 intent가 없으면 FINALIZING의 새 stop은 `NOT_APPLICABLE`이며, 이 판단은 CAS/원자 decision으로 동시 stop과 조정한다. 불확실하면 `PARTIAL + UNKNOWN`이며 상태 회귀·진단 journal 재개방은 없다.
- `operations_audit_completeness`는 현재 공개 snapshot에서 검증된 bounded operations 범위의 관찰값이다. 이후 private operations record가 추가될 수 있으며, 진단 complete가 미래 Run terminal 또는 operations complete를 주장하지 않는다. `snapshot_revision`은 공개 `RunStatus` 내용이 바뀔 때만 증가하고, 공개 내용이 동일한 private operations append나 반복 read만으로 증가하지 않는다. 이 필드와 operations journal sequence는 `run.v1`/`task.v1` payload에 추가하지 않는다.

## 8. 팀 리뷰에서 조율할 영역

1. Host 제공자 이경준: `FINALIZING` 위치, snapshot revision 발급 시점, 원자 트랜잭션/운영 감사 설계, Stop.NOT_APPLICABLE/STOPPED 구현 경로.
2. app 소비자 이동찬: 신뢰된 caller/authorization/registration 제공자, 사용자 권한 조회·제어 범위, 멱등 submission 발급/재시도.
3. Report 제공자 최민준: 진단 감사 producer registry/봉인, report partial/UNKNOWN, audit expectations 계약 소비.
4. 스키마 PR 제목에는 `스키마 변경` 포함. 계약 구현 완료와 Host 실제 DB/HTTP 테스트 완료를 구분. `uv run --no-project --python 3.13.15 scripts/dev.py check contracts`는 **최신 main을 기준으로 작업 브랜치에 변경을 적용한 후** 실행한다. main에 직접 작업하거나 push하지 않는다.

## 9. 이번 contracts 변경의 로컬 검증

2026-10-23, `main` `f649487`을 기준으로 한 작업 브랜치에서 PR #45 리뷰 보완까지 반영해 확인했다.

| 검사 | 실제 결과 |
|---|---|
| `uv run --no-project --python 3.13.15 scripts/dev.py check contracts` | Ruff 검사·포맷 통과, mypy 45개 파일 통과, pytest **602 passed** |
| `uv run --no-project --python 3.13.15 scripts/dev.py check all` | Ruff 훅·mypy 78개 파일·Import Linter 6개 경계 통과, pytest **907 passed, 1 xfailed**, 13개 패키지 wheel/sdist 빌드와 SDK import 확인 통과 |
| Host 전용 두 테스트 파일 | 위 contracts 검사에 포함된 **180개** 사례. 요청 context 누락/타입, 전체 결과 상태 조합, 시각·revision·정규화·변조 거부, 고정 bytes/digest, 업무 revision과 별개인 감사 sequence 예제를 검사 |
| `git diff --check`·문서 로컬 링크 | 통과. 기존 C1~C4 벡터와 lock·루트 설정·타 서비스 구현은 변경하지 않음 |

전체 검사의 xfail 1개는 기존 `packages/gateway/tests/test_translation.py::test_not_entered_should_carry_a_reason`이다. 미전송 사유 변환의 기존 미완료 사항이며 이번 Host 계약에서 새 xfail을 추가하거나 테스트를 완화하지 않았다. 이 로컬 검증은 팀 승인·GitHub CI·Host 서비스 인수·실제 DB/HTTP 검증의 완료를 뜻하지 않는다.
