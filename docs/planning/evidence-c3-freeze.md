# Evidence C3 공유 계약 동결안 (2026-10-21)

상태: **계약 동결 / 공유 contracts 구현 및 Evidence 제공자 리뷰 대상**. 이동찬과의 단계별 계약 합의에서 21~23번을 포함해 확정한 사항이다. 실제 Evidence 저장소·저널·캡처 실행 구현의 검증 또는 배포 완료를 뜻하지 않는다.

기준: [S1 API §7/§10](s1-api-spec.md), [C3 보완안](evidence-c3-contract.md), [PoC recipe §3](poc-report-design.md), [fingerprint v1](fingerprint-contract.md). 차이가 있으면 본 문서의 **복구 확장·receipt 순서·동시성** 확정 규칙을 적용한다. Gateway 시그니처와 C3-A의 원문 동기 캡처 계약은 그대로 유지한다.

## 1. 공유 API와 소유 경계

| 영역 | Port | 방식 | 메서드 |
|---|---|---|---|
| 실행 로컬 Gateway→Evidence | `LocalCapturePort` | sync | `capture`, `release_captures` |
| 실행 로컬 WebDiag→Evidence | `ExecutionEvidencePort` | async | `seal`, `compare_and_seal`, `recover_submission` |
| 비식별 Evidence 저장·조회 | `EvidencePort` | async | `store_evidence`, `evidence_read_summary` |

새 `recover_submission(RecoverSubmissionRequest) -> SealResult | CompareOutcome`는 `run_key, submission_ref, kind: EvidenceSubmissionKind(seal/compare)`만 받는다. 캡처 핸들·원문·임의 대상 URL을 받거나 새 대상 HTTP를 실행하지 않는다. 종류에 따라 원래 결과 타입을 반환한다. 실행 로컬 복구 메서드는 MCP/LLM/Host 일반 공개 포트에 주입하지 않는다.

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

`StoredComparison.receipts`는 정확히 `(Owner Evidence receipt, Cross Evidence receipt, Comparison receipt)` 순서. contracts 생성자는 개수, enum 종류(`evidence`, `evidence`, `comparison`), payload의 owner/cross/comparison 참조와 각각의 `artifact_ref`, 중복 부재, 모두 동일한 `run_key`를 강제한다.

실제 데이터 내용의 fingerprint 재계산과 원본 artifact 존재, 저장 commit/출처, 감사 기록의 진위는 Evidence 저장 서비스가 독립적으로 검증한다. 기존의 동일 run Evidence는 재사용 가능하며 **각 StoreReceipt의 원래 `submission_ref`, `source`, `committed_at`, fingerprint를 그대로 보존**한다. 세 receipt의 `submission_ref`나 `source.revision`이 동일할 필요는 없다. 새 비교 저장 요청에서 생성한 Comparison receipt만 그 요청의 `source`와 맞춘다. 정상 source 버전 업그레이드만으로 과거 근거를 무효화하지 않는다. 명시적 신뢰 폐기와 소급 효력은 신뢰된 등록 규칙으로 별도 확인한다. 확인 불가면 COMPLETE 금지.

`RedactedBundle.comparison`의 Evidence 의존 참조는 같은 bundle 또는 기존 같은 run의 저장 기록을 허용한다. 모든 의존성과 출처를 저장자가 확인한 후에만 완료 비교를 공개한다. 공개 포트는 `RawResponse`, 쿠키, 실제 path/query 값, 임의 dict payload나 캡처 핸들을 받지 않는다.

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
| 일부 Artifact 저장 성공, 나머지 불명 | `PARTIAL`, 기존 receipt 보존, 무전송 재조회 |
| 원문 캡처 소멸 + 필요한 Artifact 없음이 **확정** + 진행 I/O 없음 | `FAILED`, 원래 HTTP sent/unknown 상태는 보존 |
| 동일 submission 다른 바인딩/종류 | `FAILED`, `IDEMPOTENCY_CONFLICT` |

복구 성공 시 결과는 현재 검증 상태를 기준으로 재구성한다. 해결된 과거 오류는 새 결과의 `reason_codes`에서 제거하며, 실패·미확인 이력은 감사 저널에 그대로 남긴다. `seal`의 COMPLETE에는 해당 Evidence와 저장 receipt 1개가 필요하다. `compare_and_seal` COMPLETE에는 `StoredComparison`과 `ComparisonProjected` 둘 다 필요하다. PARTIAL/FAILED 결과는 저장됐다는 이유만으로 감사 확인되지 않은 완결 Artifact를 발행하지 않는다.

## 6. 리스크·추후 협의 (C3 타입 동결 범위 밖)

1. Gateway attempt의 감사와 Evidence producer 감사 사이 원인 링크를 어떻게 전달·조회할지는 Gateway/Evidence 경계에서 후속 합의한다. `CaptureRequest`·`ExecutedRequestView`에 임의 감사 필드 추가 금지. 현재 감사 인과 관계는 `AuditEvent.causal_links`로 표현한다.
2. Source가 **명시적으로 폐기**되었을 때 과거 Evidence의 소급 유효성은 등록 정책/이력 검증으로만 판단한다. 단순 revision 갱신과 구분하고 유효성 불명이라면 COMPLETE 금지.
3. 같은 제출 기록이 내구 commit되었지만 아직 Payload가 생성되지 않은 상태에서 프로세스가 죽으면 그 원문으로부터 Payload를 재생성할 수 없다. 외부 저장소/감사 기록에 실제로 아무것도 없고 진행 I/O가 없음을 확정하면 FAILED다.

## 7. 담당 및 테스트 책임

- **이동찬 (`contracts`)**: 공개 frozen 레코드·Protocol, 필드/receipt/Projection 구조 검사, `evidence.v1`·`comparison.v1` typed adapter 및 운영 registry, deterministic vectors, C3 계약 테스트·문서.
- **이경준 (`evidence`)**: 원문 수명/민감값 제거, recipe를 주입된 등록 원본에 대조, 저장·출처·audit journal 검증, 비공개 제출 내구 기록·Lease/Fencing/CAS, 종료·재시작 복구/저장 재조정·동시성 테스트.
- **최민준 (`gateway`/`judge`/`report`)**: C3-A 원문 인계/attempt 사실 보존과 감사, 저장된 Evidence 및 receipt의 검증, recipe 자료 소비와 비교·보고서 결과 검토.

이 패치의 contracts 테스트는 타입·순수 fingerprint 검증만 증명한다. 운영 서비스의 원문 비노출·store 진위·감사 내구성·재시작 복구까지 통과했다는 증거로 사용하지 않는다.
