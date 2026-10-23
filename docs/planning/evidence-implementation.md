# Evidence S1 로컬 구현 노트

상태: **구현 반영 (이경준 · evidence)**. [PR #35](https://github.com/ABC2LAB/abc2lab-dast/pull/35)·[PR #36](https://github.com/ABC2LAB/abc2lab-dast/pull/36)의 메모리·무전송 구현을 소비자·조립 관점에서 기록한다. 공유 계약은 [evidence-c3-freeze](evidence-c3-freeze.md)·[S1 규격 §7](s1-api-spec.md#7-evidence-실행-전용과-공개-저장)가 정본이며, 이 문서는 그 구현·조립·소비 노트다. 실제 Gateway 연동·내구 저장/감사·재시작 복구·인가 통합은 후속이다.

## 1. 구현 범위

`packages/evidence`에 메모리·무전송으로 구현했다(격리 `check evidence` 통과).

| 구성요소 | 포트 | 내용 |
|---|---|---|
| `core/capture.LocalCaptureStore` | `LocalCapturePort` | 캡처 수명(active→released/expired, TTL 60s·1 MiB·run당 8개)·자기 일관성/등록 바인딩 검증·동기 소유권 인계·`acquire`(실행영역 내부 읽기) |
| `adapters/memory_store.InMemoryEvidenceStore` | `EvidencePort` | `store_evidence`/`evidence_read_summary`·content_fingerprint(공유 C1 codec)·멱등/충돌·비교 의존성 검증·run 격리 |
| `core/seal.LocalSealer` | `ExecutionEvidencePort` | `seal`·`compare_and_seal`·`recover_submission`, 제출 멱등 기록, PoC 요청 레시피 생성 |

## 2. app이 조립 시 주입할 seam

evidence 내부 Protocol(`abc2lab_evidence.ports`). 현재 테스트는 fake만 있고 실제 구현은 app이 연결한다. **judge를 import하지 않는다.**

- `CaptureRegistry` — 등록 동작/자원 바인딩 조회(캡처 바인딩 검증·레시피 생성).
- `ComparisonRuleEngine` — judge 소유 규칙: `classify`·`normalize`·`assess_data`(canary 기반 비자명/반사/템플릿). app이 judge oracle에서 주입.
- `RunMac` — run HMAC 계산. 키는 구현 메모리 전용·결과/인자 비노출.
- `EvidenceAuditJournal` — Evidence 생산자 감사 저널 쓰기(선할당 event_ref·바인딩으로 commit → AuditReceipt).
- `CaptureAccess` — 캡처 저장소의 동기 읽기/해제(`LocalCaptureStore`가 구현).
- `SealerConfig` — producer_ref·redaction_version·ref/시각 공급기.

## 3. 핵심 동작 결정

- **캡처 크기** = body + 모든 헤더 name/value의 UTF-8 bytes 합계(계약 정의). active 상한 초과는 `capture_unavailable`.
- **바인딩** = 실행 view 자기 일관성 + 등록(origin/method/purpose·자원 바인딩·매개변수 멀티셋 정확 일치). 불일치는 `capture_binding_mismatch`(원문 미보관).
- **비교 신호 분담** — `same_resource`·`distinct_verified_subjects`·`owner/cross_normal_data`는 evidence가, `nontrivial_data_match`·`reflection_excluded`·`template_excluded`는 규칙 엔진이 산출. **HMAC 일치만으로 `nontrivial_data_match=YES` 금지**(엔진이 canary로 판정).
- **레시피 부재 사유 우선순위** = `recipe_not_exportable` → `recipe_unsupported` → `recipe_missing`. 생성기 미구현 단계는 `recipe_unsupported`. 레시피는 실제 origin/입력 값·인증 자료 없이 `${SLOT}` placeholder·등록 path_template만 담는다.
- **제출 멱등** — 원문 `capture_ref`를 영속화하지 않고 도메인 분리 지문으로 충돌을 대조한다. 같은 제출·같은 바인딩 재호출은 **재캡처 없이** 기존 결과, 다른 바인딩은 `IDEMPOTENCY_CONFLICT`. `recover_submission`은 캡처 재취득·대상 재전송 0.
- **완료 기준** — `seal` COMPLETE = Evidence + 저장 receipt 1개(fingerprint 대조). `compare_and_seal` COMPLETE = `StoredComparison`(저장 receipt 3) + `ComparisonProjected`(COMPARISON 감사 영수증). 하나라도 미확인이면 성공 receipt를 보존한 PARTIAL.
- **비노출** — 원문 응답·캡처 핸들·run HMAC 키는 실행영역 메모리 전용. 공개 결과·로그·fingerprint 입력에 넣지 않는다.

## 4. 소비자(webdiag·host) 참고

- `seal`/`compare_and_seal`은 **자기가 acquire한 캡처를 스스로 release**한다. 소비자는 넘긴 capture_ref를 다시 해제하지 않고, 받아놓고 봉인까지 못 간 캡처만 `release_captures`로 정리한다. (capture_ref 출처는 Gateway `AttemptResult`.)
- 재시도/전송 불명은 새 캡처로 재-seal 말고 같은 `submission_ref`로 재호출하거나 `recover_submission`을 쓴다.
- `AccessCompareResult`는 evidence가 준 `stored_comparison`·`projection_event`를 **그대로 전달**(Host가 project)하고 새로 만들지 않는다. PARTIAL을 확정으로 취급하지 않는다.
- `ComparisonSignals`는 판정이 아니다(판정은 Judge). capture_ref·원문을 로그·공개 결과로 흘리지 않는다.

## 5. 남은 작업 (후속 PR)

- 실제 Gateway 캡처 인계 연동과 무전송 통합.
- 내구 저장소·감사 journal(`AuditVerifier`/`AuditReader`) 실구현과 출처/인가 검증.
- 재시작 복구의 실제 재조회·재조정, 제출 Lease/Fencing/CAS 내구화.
- 레시피의 등록 원본 독립 대조(Evidence/Report), 다중 매개변수·FORM·충돌 placeholder 처리.
