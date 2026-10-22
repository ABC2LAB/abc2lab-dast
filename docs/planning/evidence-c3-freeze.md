# Evidence C3 공유 계약 동결안 (2026-10-22 보완)

상태: **공유 contracts 구현 / 2026-10-22 감사 연결·진단 보완의 영향 담당 승인 대기**. 기존 단계별 계약 합의의 21~23번을 포함하며 이번 보완은 §6에 정리한다. 실제 Evidence 저장소·저널·캡처 실행 구현의 검증 또는 배포 완료를 뜻하지 않는다.

기준: [S1 API §7/§10](s1-api-spec.md), [C3 보완안](evidence-c3-contract.md), [PoC recipe §3](poc-report-design.md), [fingerprint v1](fingerprint-contract.md). 차이가 있으면 본 문서의 **복구 확장·receipt 순서·동시성** 확정 규칙을 적용한다. Gateway 시그니처와 C3-A의 원문 동기 캡처 계약은 그대로 유지한다.

## 1. 공유 API와 소유 경계

| 영역 | Port | 방식 | 메서드 |
|---|---|---|---|
| 실행 로컬 Gateway→Evidence | `LocalCapturePort` | sync | `capture`, `release_captures` |
| 실행 로컬 WebDiag→Evidence | `ExecutionEvidencePort` | async | `seal`, `compare_and_seal`, `recover_submission` |
| 비식별 Evidence 저장·조회 | `EvidencePort` | async | `store_evidence`, `evidence_read_summary` |

새 `recover_submission(RecoverSubmissionRequest) -> SealResult | CompareOutcome`는 `run_key, submission_ref, kind: EvidenceSubmissionKind(seal/compare)`만 받는다. 캡처 핸들·원문·임의 대상 URL을 받거나 새 대상 HTTP를 실행하지 않는다. 종류에 따라 원래 결과 타입을 반환한다. 제공자는 반환 전, 소비자는 반환값 수락 전에 `validate_recovery_result(request, result)`로 SEAL→정확한 SealResult, COMPARE→정확한 CompareOutcome 및 같은 run을 검사한다. FAILED도 종류 불일치를 허용하지 않는다. 실제 submission_ref와 최초 바인딩의 조회·대조는 제공자 책임이다. 실행 로컬 복구 메서드는 MCP/LLM/Host 일반 공개 포트에 주입하지 않는다.

공유 레코드: `EvidenceSummary`, `ComparisonSignals`, `ComparisonPayload`, `StoredComparison`, `ArtifactKind`, `StoreReceipt`, `RedactedBundle`, `StoreOutcome`, `EvidenceReadRequest`, `EvidenceReadResult`, `SealRequest`, `SealResult`, `CompareRequest`, `CompareOutcome`, `ComparisonProjected`, `RecipeParameter`, `RegisteredRequestRecipe`, `EvidenceSubmissionKind`, `RecoverSubmissionRequest`.

`contracts`는 frozen/slots 정확한 타입, enum/tuple, 구조적 불변식을 검증한다. **실제 원본 저장, 출처의 진위/시점별 효력, 권한 검사, 캡처/등록 바인딩, 민감값 제거, AuditReader/AuditVerifier 호출, 동시성 내구성은 Evidence 서비스 책임**이다. `ContractRecord`의 생성 성공을 저장·감사 성공으로 취급하지 않는다.

## 2. 불변 Artifact와 fingerprint 순서

1. `seal`/`compare_and_seal`이 첫 `await` 이전에 캡처(비교는 양쪽)를 원자적 취득하고 실행 등록/계정/세대·신원/규칙 바인딩을 대조한다.
2. **먼저** 새로운 Evidence/Comparison Artifact ID와 생산자 Event ID를 선할당한다. 같은 제출의 재조회·복구에서는 이전에 고정한 ID만 사용한다. 이전에 저장한 Evidence를 비교에 재사용하면 그 ID/receipt를 변경하지 않는다.
3. 최초 제출의 비공개 내구 기록이 commit된 **다음에만** 최초 Artifact 저장을 시작한다. 이때 Payload가 아직 없으면 content fingerprint는 `None`이며, 가짜 fingerprint나 감사 receipt를 작성하지 않는다.
4. 원문을 메모리에서 민감값 제거·응답 분석하고, `EvidenceSummary.source_event`에 **Evidence 자신의** 선할당 `AuditLink(producer, event_ref)`를 넣어 완전한 EvidenceSummary를 조립한다. Gateway attempt의 source_event와 혼동하지 않는다.
5. contracts의 정확한 typed wrapper로 `evidence.v1`과 `comparison.v1` fingerprint를 계산한다. `EvidenceSummary`에는 nullable recipe와 source_event의 불변 내용이 포함된다. `ComparisonPayload`에는 저장/audit receipt가 전혀 포함되지 않는다. receipt는 payload fingerprint에 섞지 않는다.
6. 비식별 Artifact 저장 + `StoreReceipt` 확보 → `EVIDENCE` 2개 및 `COMPARISON` 1개 생산자 감사 commit의 실재 여부 검증 → 필수 자료가 모두 검증된 후에만 완료된 `StoredComparison`과 `ComparisonProjected` 발행. 원본 비교 감사 바인딩 revision은 `1`; 비교 원본 journal 종류는 `COMPARISON`.

정확한 `ComparisonProjected.source_receipt`는 비교 Artifact **생산자 COMPARISON AuditReceipt**다. `event_ref`, `producer`, `run_key`, `record_ref=comparison_ref`, `record_revision=1`, `record_fingerprint=comparison_fingerprint(payload)`를 모두 검증하며, 마지막으로 해당 생산자의 `verify_committed`를 사용한다. `StoreReceipt` 3개와 혼동하지 않는다.

## 3. 저장 receipt 3개 불변식

`StoredComparison.receipts`는 정확히 `(Owner Evidence receipt, Cross Evidence receipt, Comparison receipt)` 순서. contracts 생성자는 개수, enum 종류(`evidence`, `evidence`, `comparison`), payload의 owner/cross/comparison 참조와 각각의 `artifact_ref`, 중복 부재, 모두 동일한 `run_key`를 강제한다. 함께 제공된 `ComparisonPayload`의 fingerprint를 재계산해 Comparison receipt의 값과도 대조한다. Owner/Cross Evidence 내용은 이 객체에 없으므로 해당 두 receipt의 내용 대조는 저장 서비스 책임이다. `SealResult.COMPLETE`도 함께 제공된 `EvidenceSummary`의 fingerprint와 저장 receipt를 대조한다. 이 로컬 일관성 검사는 실제 저장·감사 commit의 증명이 아니다.

실제 데이터 내용의 fingerprint 재계산과 원본 artifact 존재, 저장 commit/출처, 감사 기록의 진위는 Evidence 저장 서비스가 독립적으로 검증한다. 기존의 동일 run Evidence는 재사용 가능하며 **각 StoreReceipt의 원래 `submission_ref`, `source`, `committed_at`, fingerprint를 그대로 보존**한다. 세 receipt의 `submission_ref`나 `source.revision`이 동일할 필요는 없다. 새 비교 저장 요청에서 생성한 Comparison receipt만 그 요청의 `source`와 맞춘다. 정상 source 버전 업그레이드만으로 과거 근거를 무효화하지 않는다. 명시적 신뢰 폐기와 소급 효력은 신뢰된 등록 규칙으로 별도 확인한다. 확인 불가면 COMPLETE 금지.

`RedactedBundle.comparison`의 Evidence 의존 참조는 같은 bundle 또는 기존 같은 run의 저장 기록을 허용한다. 모든 의존성과 출처를 저장자가 확인한 후에만 완료 비교를 공개한다. 공개 포트는 `RawResponse`, 쿠키, 실제 path/query 값, 임의 dict payload나 캡처 핸들을 받지 않는다.

레시피가 있는 `EvidenceSummary`는 레시피의 `operation_ref`·`resource_ref`가 자신의 값과 같아야 한다. `RegisteredRequestRecipe`는 `//host`나 역슬래시가 포함된 경로를 거부한다. 이 형태 검사와 별도로 Evidence/Report는 주입된 등록 원본의 동작·자원·바인딩·revision·경로·placeholder·출처를 모두 대조한 뒤 저장·출력해야 한다. contracts 테스트의 무전송 fake는 등록과 다른 레시피가 저장 전에 거부되는 연결 예제이며, 실제 인가·저장·감사 구현을 대신하지 않는다.

## 4. 제출 멱등성·재시작 복구

- `submission_ref`는 최초 호출 전에 호출자가 할당하고, 같은 `(run_key, submission_ref)`에 기존 검증된 입력 바인딩만 허용한다. 최초 요청 바인딩에는 종류, 실제 A/B attempt·자원·동작, 신원 fingerprint, ComparisonRules 출처/내용이 포함된다. 다른 내용은 `IDEMPOTENCY_CONFLICT`.
- 캡처 참조는 128비트 이상 암호학적 난수여야 한다. 비공개 제출 내구 기록에는 역할을 구분한 도메인 분리 SHA-256 **검증 지문**만 저장하고 원문 `capture_ref`는 영속화하지 않는다. 지문은 제출 충돌 대조 전용이며 원문/저장/감사 증명이 아니다.
- 내부 내구 기록은 `run_key`, `submission_ref`, 종류, 검증된 업무/캡처 바인딩 지문, 선할당 artifact/event 참조, fingerprint 미생성/확정 여부, 저장 성공 영수증, 감사 확인 상태, 처리 진행 상태, Lease 및 Fencing Token의 최소 데이터를 보존한다. **이 내부 기록은 `contracts`의 공개 dataclass가 아니다.** 실제로 무엇을 저장할지와 암호·권한 보호는 Evidence 내부에서 구현·테스트한다. 원문 응답, 비밀, 캡처 핸들, run HMAC 키 영속화 금지.
- 최초 내구 기록 확정 전의 장애에서는 최초 제출 바인딩을 추측하여 완료 처리하지 않는다. 최초 내구 기록 이후의 장애에서는 `recover_submission`으로 기존 저장/감사 상태만 재조회하고, 필요한 Artifact가 없다면 원문을 복구하려 하지 않는다.
- 동일 제출에는 **한 번에 한 변경 처리자**만 허용한다. 비공개 Evidence 처리자 Lease의 시간·갱신은 내부 설정(공유 `RunLimits`에 추가하지 않음). CAS 소유권 인계 시 단조 증가 Fencing Token으로 오래된 처리자의 제출 상태 쓰기를 거부한다.
- 제출 내구 저장, Artifact 저장, 감사 저널은 **독립 트랜잭션**이다. 토큰이 낡아도 이미 전송된 저장 I/O는 나중에 commit될 수 있으므로, 변경된 불변 ID/내용을 거부하고 기존 ID/fingerprint의 실제 commit을 재조회·검증하여 재조정한다. Lease 만료나 네트워크 timeout만으로 미저장/취소/미전송을 선언하지 않는다.

## 5. COMPLETE / PARTIAL / FAILED

| 확실히 검증된 상태 | 복구·일반 호출 반환 |
|---|---|
| 필수 Artifact·StoreReceipt·원본 감사 모두 실재·일치 | `COMPLETE`, 기존 Evidence/StoredComparison/Projection/receipts 반환 |
| 저장·감사 결과 미확인/지연 I/O 잔존 | `PARTIAL`, 성공한 receipt 유지, 완료 비교·Projection 없음 |
| 일부 Artifact 저장 성공, 나머지 불명 또는 복구 불가 | `PARTIAL`, 기존 receipt 보존, 가능한 저장·감사 상태만 무전송 재조회 |
| 성공 receipt 없음 + 원문 캡처 소멸 + 필요한 Artifact 없음이 **확정** + 진행 I/O 없음 | `FAILED`, 원래 HTTP sent/unknown 상태는 보존 |
| 동일 submission 다른 바인딩/종류 | 충돌한 입력은 `FAILED`, receipt 없이 `IDEMPOTENCY_CONFLICT`; 기존 제출·receipt를 덮어쓰지 않음 |

복구 성공 시 결과는 현재 검증 상태를 기준으로 재구성한다. 해결된 과거 오류는 새 결과의 `reason_codes`에서 제거하며, 실패·미확인 이력은 감사 저널에 그대로 남긴다. `seal`의 COMPLETE에는 해당 Evidence와 저장 receipt 1개가 필요하다. `compare_and_seal` COMPLETE에는 `StoredComparison`과 `ComparisonProjected` 둘 다 필요하다. PARTIAL/FAILED 결과는 저장됐다는 이유만으로 감사 확인되지 않은 완결 Artifact를 발행하지 않는다.

**결과 상태 보완(2026-10-21, 이동찬 확인):** `StoreOutcome`·`SealResult`·`CompareOutcome`에서 성공 receipt가 하나라도 있으면 `PARTIAL` 또는 `COMPLETE`로 반환한다. 나머지 근거를 복구할 수 없어도 성공 receipt를 버리거나 `FAILED`에 넣지 않는다. `FAILED`에는 성공 receipt가 없고, 모든 receipt는 결과와 같은 run이어야 한다. `StoreOutcome.COMPLETE`에는 최소 1개 receipt가 필요하다. `PARTIAL`은 반드시 이후 완료가 가능하다는 뜻이 아니며 대상 요청 재전송의 근거가 아니다.

`StoreOutcome`·`SealResult`·`CompareOutcome`·`EvidenceReadResult`의 `PARTIAL`/`FAILED`는 비어 있지 않은 `reason_codes`가 필요하다. 조회 실패를 성공한 빈 결과로 바꾸지 않는다. `EvidenceReadResult.FAILED`는 Artifact를 발행하지 않으며, 허용된 일부 자료를 반환할 때는 사유와 함께 `PARTIAL`을 쓴다. 정상 조회 결과가 0건인 `COMPLETE`는 허용한다.

## 6. 감사 연결·비교 진단과 남은 리스크

### 6.1 Evidence와 실제 전송의 연결 (2026-10-22 확정)

`EvidenceSummary.source_event`는 계속 Evidence 자신의 이벤트다. Gateway event_ref를 capture 입력에 추가하지 않는다. **EVIDENCE binding.attempt_ref → 주입된 Gateway의 ATTEMPT 조회·commit 검증**을 기본 연결 경로로 고정한다.

1. Gateway는 동기 capture/소유권 등록 뒤 `AttemptRecord`와 ATTEMPT 감사를 commit한다. binding은 `record_ref == attempt_ref == AttemptRecord.attempt_ref`, `request_ref == AttemptRecord.request_ref`를 필수로 갖고, revision·fingerprint는 실제 AttemptRecord에서 계산한다. 감사의 account/generation/send_status/시각/사유도 **같은 commit된 원본에서 일관되게** 생성한다. caller가 준 상태로 덮어쓰지 않는다.
2. Evidence의 async seal/compare/복구는 app이 주입한 Gateway `AuditReader`로 같은 run/producer의 안정된 snapshot을 조회한다. 비공개 캡처의 request_ref·attempt_ref와 일치하는 **ATTEMPT**를 찾는다. REQUEST_INTENT나 정책 allow는 전송 증거가 아니다. cursor/snapshot·연속 sequence·수위를 대조하고, 설정된 페이지/시간 상한 안에서 snapshot 끝까지 확인해 충돌하는 revision을 숨기지 않는다. 동일 attempt의 revision은 1부터 연속된 이력에서 유일한 최고 record_revision의 이벤트를 채택하고 causal_link도 그 이벤트를 가리킨다. 동일 revision의 중복/상이한 fingerprint, revision 누락 또는 상태 충돌은 AUDIT_GAP/AUDIT_VERIFICATION_UNKNOWN으로 남기며 유리한 과거 sent만 선택하지 않는다. 이미 확인된 sent 사실·횟수는 이 검증 실패로 지우지 않는다.
3. run·주입된 producer·event/ref/revision·request/attempt 및 account/generation을 대조하고 해당 Gateway `verify_committed`가 VERIFIED인 기록만 채택한다. caller/LLM이 제공한 event/receipt나 producer 문자열을 조회 원본으로 사용하지 않는다. **이 경로는 신뢰된 생산자의 원본 확인(attestation)**이다. AuditPage에는 전체 AttemptRecord가 없으므로 소비자가 capture_status/decision_ref 등 모든 업무 필드의 digest를 독립 재계산했다고 주장하지 않는다. Gateway verifier가 저장된 AttemptRecord를 다시 읽어 digest 및 공개 metadata의 일치를 확인해야 한다. PolicyDecision처럼 업무 payload 전체를 가진 경로의 독립 재계산 의무는 그대로다.
4. EVIDENCE 감사 binding은 `kind=EVIDENCE`, `record_ref=summary.evidence_ref`, revision `1`, `fingerprint=evidence_fingerprint(summary)`, `attempt_ref=summary.attempt_ref`, **request_ref와 binding_id는 None**이다. 공개 summary만으로 소비자가 이 binding을 재계산할 수 있게 한다. 비공개 request_ref는 Gateway ATTEMPT 대조에 사용한다. 생산자와 소비자는 모두 `validate_evidence_audit`로 source_event/run/내용·계정/세대/근거 참조를 대조하고, 실제 Evidence 생산자의 commit도 별도 확인한다. 이 이벤트의 send_status는 None이며 전송 사실은 Gateway에서 읽는다.
5. 확인된 Gateway `AuditLink`는 **EVIDENCE AuditEvent.causal_links**에 넣는다. COMPARISON의 causal_links는 owner/cross의 검증된 EVIDENCE 이벤트를 가리킨다. 순서는 ATTEMPT commit → EVIDENCE commit → COMPARISON commit이다. 연결 미확인 시 선할당 Evidence event ID를 보존하고 완료 감사를 확정하지 않는다. 이미 commit한 불변 이벤트를 나중에 수정하지 않는다. 성공 StoreReceipt는 PARTIAL에 보존한다.
6. Judge·Report는 Evidence source_event의 실제 감사와 Gateway ATTEMPT를 같은 경로로 조회·검증하고, causal_links가 조회 결과와 일치하는지도 대조한다. `sent`와 검증된 캡처·저장 근거가 있을 때만 실제 전송에 연결된 근거로 사용한다. `unknown`, 조회 실패/만료/상한 초과/충돌은 `AUDIT_VERIFICATION_UNKNOWN` 등 사유로 보존하며 UNDECIDABLE 또는 보고서 제한을 남긴다. 확정 `not_sent`와 응답 근거가 함께 있으면 바인딩 불일치다. 누락을 not_sent·전송 0건으로 바꾸거나 HTTP를 재전송하지 않는다.

특정 attempt의 commit 확인은 run 전체 봉인을 기다릴 필요가 없다. 같은 snapshot의 끝과 committed_through까지 확인하며, terminal_sequence=None인 열린 journal도 이미 commit된 attempt를 검증할 수 있다. 다만 기록 부재의 확정과 **최종 보고서의 감사 완전성**은 봉인된 전체 snapshot/기대 범위를 별도로 확인한다. 열린/불완전 snapshot의 부재는 unknown, 봉인된 완전 snapshot에서 기대 attempt가 없으면 AUDIT_GAP이다. 생산자가 보증한 감사 상태와 실제 wire bytes의 암호학적 증명은 구분한다.

### 6.2 UNKNOWN 사유와 canary (2026-10-22 확정)

**UNKNOWN 사유는 Evidence의 원본 COMPARISON 감사 기록에서 확인한다.** ComparisonSignals/ComparisonPayload 필드, comparison.v1/evidence.v1 fingerprint·고정 벡터는 바꾸지 않는다. Evidence는 다음 상태·사유를 AuditEvent.reason_codes에 기록하고 Judge·Report는 comparison_ref의 원본 감사를 조회·verify_committed한 뒤 설명에 사용한다.

| 신호/진단 | 감사 코드 |
|---|---|
| canary 검증 | `comparison_canary_passed` / `comparison_canary_failed` / `comparison_canary_unknown` 중 정확히 하나 |
| same_resource UNKNOWN | `comparison_same_resource_unknown` |
| distinct_verified_subjects UNKNOWN | `comparison_subjects_unknown` |
| owner_normal_data UNKNOWN | `comparison_owner_data_unknown` |
| cross_normal_data UNKNOWN | `comparison_cross_data_unknown` |
| nontrivial_data_match UNKNOWN | `comparison_data_match_unknown` |
| reflection_excluded UNKNOWN | `comparison_reflection_unknown` |
| template_excluded UNKNOWN | `comparison_template_unknown` |

각 UNKNOWN 신호에는 해당 코드를 반드시 넣고 YES/NO에는 그 UNKNOWN 코드를 넣지 않는다. 상세 원인이 확인되면 `identity_unknown`, `capture_unavailable`, `source_unverified` 등 해당 원인 코드도 함께 남긴다. 원인을 알 수 없으면 추측하지 않고 해당 신호 미확인으로 설명한다. canary 실패/미확인은 정규화 신뢰를 보장하지 못하므로 nontrivial_data_match=UNKNOWN 및 대응 코드를 요구한다. canary 통과가 다른 신호를 자동 YES로 만들지는 않는다. 원문·canary 값·응답 문자열은 기록하지 않는다.

COMPARISON binding의 request_ref/attempt_ref/binding_id와 event의 send_status/account_ref/session_generation/policy_outcome은 None이다. event.case_ref는 payload.case_ref, evidence_refs는 `(owner_evidence_ref, cross_evidence_ref)` 순서다. EVIDENCE의 evidence_refs는 정확히 `(summary.evidence_ref,)`다. 두 종류 모두 verdict_refs는 비어 있고 EVIDENCE의 policy_outcome도 None이다. 비교에 한쪽 실행 계정이나 후속 Verdict를 섞지 않는다. `validate_comparison_audit`는 이 바인딩·fingerprint·신호/사유 일관성을 검사한다. 이는 순수 로컬 검사이며 저장/감사 진위를 증명하지 않는다. 감사 metadata는 comparison digest에 포함되지 않으므로 **주입된 생산자 reader/verifier의 동일 원본 보장과 불변 journal**을 통해 확인한다. 감사 읽기 실패나 사유 누락을 이유 없는 정상 비교로 처리하지 않는다.

### 6.3 남은 리스크 (C3 타입 동결 범위 밖)

1. Source가 **명시적으로 폐기**되었을 때 과거 Evidence의 소급 유효성은 등록 정책/이력 검증으로만 판단한다. 단순 revision 갱신과 구분하고 유효성 불명이라면 COMPLETE 금지.
2. 같은 제출 기록이 내구 commit되었지만 아직 Payload가 생성되지 않은 상태에서 프로세스가 죽으면 그 원문으로부터 Payload를 재생성할 수 없다. 외부 저장소/감사 기록에 실제로 아무것도 없고 진행 I/O가 없음을 확정하면 FAILED다.

## 7. 담당 및 테스트 책임

- **이동찬 (`contracts`)**: 공개 frozen 레코드·Protocol, 필드/receipt/Projection 구조 검사, `evidence.v1`·`comparison.v1` typed adapter 및 운영 registry, deterministic vectors, C3 계약 테스트·문서.
- **이경준 (`evidence`)**: 원문 수명/민감값 제거, recipe를 주입된 등록 원본에 대조, 저장·출처·audit journal 검증, 비공개 제출 내구 기록·Lease/Fencing/CAS, 종료·재시작 복구/저장 재조정·동시성 테스트.
- **최민준 (`gateway`/`judge`/`report`)**: C3-A 원문 인계/attempt 사실 보존과 감사, 저장된 Evidence 및 receipt의 검증, recipe 자료 소비와 비교·보고서 결과 검토.

이 패치의 contracts 테스트는 타입·순수 fingerprint 검증만 증명한다. 운영 서비스의 원문 비노출·store 진위·감사 내구성·재시작 복구까지 통과했다는 증거로 사용하지 않는다.
