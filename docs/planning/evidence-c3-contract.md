# Evidence C3 계약 보완안

상태: **공유 계약 동결(2026-10-21, 이동찬 확인) / Evidence 제공자·소비자 코드 리뷰 필요**. 세부 확정안은 [C3 동결안](evidence-c3-freeze.md)을 따른다. 이경준의 Evidence 소유 경계 제안을 검토해 [S1 상세 규격 §7·§10](s1-api-spec.md)과 [fingerprint 계약](fingerprint-contract.md)에 맞춘다. 이는 실제 Evidence 저장·감사 서비스 구현 완료를 뜻하지 않는다.

## 1. 이번에 고정한 의미

`EvidenceSummary.source_event`는 **Evidence가 소유한 해당 artifact 감사 이벤트의 `AuditLink`**다. Gateway attempt 링크로 대체하지 않는다. `AuditLink(producer, event_ref)`는 식별자이며 실제 저장 증명은 해당 생산자의 `AuditReceipt`와 `verify_committed`다.

Evidence는 `evidence_ref`와 자신의 `event_ref`를 fingerprint 계산 전에 고정한다. `event_ref`는 완성될 fingerprint나 감사 영수증에서 도출하지 않는다. 같은 `submission_ref`의 동일 작업을 재확인할 때는 이미 할당한 참조와 불변 내용을 재사용한다. 새 이벤트 ID·시각을 만들어 같은 내용을 다른 fingerprint로 바꾸지 않는다. 다른 내용이면 기존 멱등 충돌 규칙을 따른다.

```text
Evidence의 artifact/event 식별자 고정
→ 자체 source_event를 포함한 EvidenceSummary 구성
→ evidence.v1 fingerprint 계산
→ 민감값 제거 artifact 저장과 StoreReceipt 확인
→ 동일 event_ref와 fingerprint로 EVIDENCE 감사 commit 확인
→ seal 완료 결과 발행
```

링크를 미리 만드는 것은 감사 성공을 미리 선언하는 것이 아니다. 감사 실패·불명에는 완료 근거를 새로 발행하지 않고, 이미 확인된 저장 영수증은 보존한다. 조회자는 `source_event`의 실제 감사 기록을 읽어 run·producer/event_ref·artifact ref/revision·내용 fingerprint를 독립 대조한다.

## 2. 캡처 경계는 유지

`CaptureRequest`·`ExecutedRequestView`에 `source_event`를 추가하지 않는다. 원문 수신 직후에는 동기 capture로 await 없이 소유권을 넘기고, 캡처 결과를 얻은 뒤 Gateway가 전송/캡처 상태를 attempt 감사에 기록하는 기존 순서를 유지한다.

```text
Gateway transport
→ 동기 capture / 소유자 등록
→ CaptureResult
→ Gateway attempt 결과 감사 commit
→ AttemptResult
```

응답의 원인인 Gateway attempt와 Evidence의 artifact 이벤트는 구분한다. **2026-10-22 확정:** EVIDENCE binding.attempt_ref로 app이 주입한 Gateway의 ATTEMPT를 read_audit·verify_committed로 확인하고, 확인된 링크를 EVIDENCE AuditEvent.causal_links에 넣는다. ATTEMPT binding에는 같은 record_ref/attempt_ref와 request_ref가 필수다. EVIDENCE binding은 summary에서 재구성할 수 있도록 request_ref/binding_id=None이다. 전체 AttemptRecord를 받지 않는 이 경로는 신뢰된 생산자 원본 확인이며, 소비자가 전송 레코드 전체를 독립 재해시한 것으로 취급하지 않는다. snapshot·revision 충돌·unknown 처리와 Judge/Report 소비 절차는 [동결안 §6.1](evidence-c3-freeze.md#61-evidence와-실제-전송의-연결-2026-10-22-확정)을 따른다. 새 필드/포트를 추가하지 않으며 원문 인계 전에 Gateway 결과 commit을 기다리게 하지 않는다.

## 3. 이번 contracts 구현 범위

필드는 [S1 §7](s1-api-spec.md#7-evidence-실행-전용과-공개-저장)과 [PoC 최소 타입](poc-report-design.md#3-최소-추가-타입)을 따른다. 기존 C2의 `ComparisonRules`·`IdentityResult`·`AuditLink`·감사 타입과 scalar/상태/사유를 재사용한다.

| 묶음 | 구현한 공유 계약 |
|---|---|
| 공개 근거·비교 자료 | `EvidenceSummary`, `ComparisonSignals`, `ComparisonPayload`, `StoredComparison` |
| 저장·조회 | `ArtifactKind(evidence/comparison)`, `StoreReceipt`, `RedactedBundle`, `StoreOutcome`, `EvidenceReadRequest`, `EvidenceReadResult` |
| 로컬 봉인·비교·복구 | `SealRequest`, `SealResult`, `CompareRequest`, `CompareOutcome`, `RecoverSubmissionRequest`, `EvidenceSubmissionKind`와 async `seal`·`compare_and_seal`·`recover_submission` |
| 공개 저장·읽기 포트 | async `store_evidence`·`evidence_read_summary` |
| 원본 비교 이벤트 | `ComparisonProjected`와 실제 Evidence producer의 감사 영수증 바인딩 |
| 레시피 자료형 | `RecipeParameter`, `RegisteredRequestRecipe` |
| fingerprint | `evidence.v1`·`comparison.v1`의 정확한 typed wrapper·payload adapter·운영 registry·고정 벡터 |

`EvidenceSummary.request_recipe`는 필수 nullable 필드다. 따라서 그 타입을 dict/Any나 임시 None 전용 타입으로 대신하지 않는다. 레시피 생성·민감값 치환 구현은 후속으로 둘 수 있지만, 공유 자료형은 EvidenceSummary와 같은 PR 또는 선행 PR에서 정의한다. 미지원이면 기존 계약대로 request_recipe=None과 사유를 보존한다. Report의 PoC 출력 타입과 Judge/Knowledge 포트는 이 구현 범위에 넣지 않는다.

## 4. 비교 저장·감사 수명주기

`ComparisonPayload`는 이미 감사·저장 영수증이 없는 불변 업무 내용이다. `EvidenceSummary`도 감사 영수증 필드가 없고 미리 고정한 AuditLink만 가진다. 현재 필드 구조에는 별도 `ComparisonContent`·`EvidenceSummaryContent`가 필요하지 않다. 이는 최종 record가 실제 AuditReceipt를 필수 필드로 갖는 C2 PolicyDecision/IdentityResult와 다른 조건이다.

```text
기준·교차 EvidenceSummary와 ComparisonPayload 구성
→ 두 evidence fingerprint + comparison fingerprint 계산
→ Evidence 2건·Comparison 1건의 저장 영수증 3개 확인
→ 두 EVIDENCE artifact와 COMPARISON 원본 감사 확인
→ StoredComparison 및 ComparisonProjected를 complete로 반환
```

- 비교 원본 감사는 `AuditEventKind.COMPARISON`이며 `record_ref=comparison_ref`, 불변 artifact의 `record_revision=1`을 쓴다. `EVIDENCE`는 각 EvidenceSummary artifact 감사에 사용한다.
- `StoredComparison.payload`를 fingerprint하고 저장 영수증 3개는 각각 독립 대조한다. receipt를 ComparisonPayload fingerprint에 섞지 않는다.
- `ComparisonProjected`의 event_ref/producer/run/source_revision은 원본 comparison 감사 영수증과 결합한다. source_revision은 artifact record revision이며 감사 sequence나 규칙 버전으로 대체하지 않는다.
- complete에는 저장·필수 감사 확인과 비교·원본 이벤트가 모두 필요하다. 일부 확인 실패·불명에는 성공한 receipt를 보존하고 완료 StoredComparison/Projection을 새로 발행하지 않는다. 감사 저장 불명은 같은 식별자로 재조회하며 대상 요청을 재전송하지 않는다.
- Evidence는 기존 `AuditVerifier`·`AuditReader`를 구현한다. 새 범용 commit 서비스 포트는 추가하지 않으며 자기 journal의 쓰기는 Evidence 내부 구현 책임이다.
- UNKNOWN인 비교 신호의 원인과 canary 3상태는 원본 COMPARISON AuditEvent.reason_codes에서 확인한다. payload에 필드를 추가하지 않는다. 생산자·소비자는 `validate_comparison_audit`로 신호/사유·case/근거 참조·내용 지문을 대조하고 실제 감사 commit을 별도 확인한다. 상세 코드와 불변 metadata 규칙은 [동결안 §6.2](evidence-c3-freeze.md#62-unknown-사유와-canary-2026-10-22-확정)를 따른다.

## 5. 담당과 후속 확인

| 책임 | 담당·검토 |
|---|---|
| 공유 타입·Protocol·fingerprint·벡터·관련 계약 문서 | 이동찬(`contracts`), 이경준과 최민준이 영향 경계 리뷰 |
| 실제 캡처·봉인·비교·저장·감사 구현 | 이경준(`evidence`) |
| 실제 응답 인계·attempt 감사·캡처 결과 보존 | 최민준(`gateway`) |
| WebDiag·Host 소비·전달 | 이경준 |
| Judge·Report 소비·비교 규칙 제공 | 최민준 |

이번 contracts 테스트는 완결 결과의 업무 내용/receipt fingerprint 일치, 잘못된 producer/kind/ref/revision/내용 거부, 성공 receipt의 같은 run·`PARTIAL` 보존, 미완료 사유 필수, 실패 조회의 자료 비공개를 검사한다. 등록과 다른 레시피를 저장 전에 거부하는 무전송 fake 예제도 포함한다. 상태의 정확한 의미는 [동결안 §5](evidence-c3-freeze.md#5-complete--partial--failed)를 따른다. 동일 submission의 event_ref 재사용, 한쪽 근거 누락과 저장·감사 실패/불명의 실제 복구·동시성 검증은 Evidence 제공자 구현에서 수행해야 한다. 캡처 크기는 기존 C3-A의 **본문 + 모든 헤더 이름·값 UTF-8 bytes 합계 1 MiB** 기준을 따른다.

제안자가 보고한 Evidence 로컬 구현·격리 검사 결과는 제공자 측 진행 상황이며, 현재 공유 checkout에 그 구현이 제공됐거나 검증됐다는 의미는 아니다. 임시 `_c3_records.py`·fingerprinting 구현은 해당 담당자가 공유 계약 병합 후 import로 교체한다. 이동찬의 작업은 contracts와 관련 문서에 한정한다.
