# C4-B Judge 공유 계약

상태: **스키마 변경·공유 계약 구현·로컬 검증 완료, 팀 리뷰 대기 (2026-10-22)**. 이 문서는 `contracts`가 제공하는 Judge 경계의 정본이다. PR #34의 기존 오라클·메모리 journal·publisher는 보존하며, 새 포트의 실제 서비스 조립·정책 등록 저장소·영속화와 감사·권한 검증 확장은 후속 범위다.

## 1. 공개 포트

`JudgePort`는 다음 비동기 메서드를 제공한다.

```python
async def judge(request: JudgeRequest) -> JudgeResult
```

`JudgeRequest`는 정확히 다음 필드를 가진다: `run_key: RunKey`, `context: ReadContext`, `case_ref: Ref`, `submission_ref: Ref`, `expected_policy: ExpectedAccessPolicySnapshot | None`, `owner_identity: IdentityResult | None`, `evaluated_identity: IdentityResult | None`, `comparison_ref: Ref | None`. 모든 참조는 해당 run에 속해야 하며, 원문 HTTP 응답·쿠키·세션 비밀·캡처 핸들은 포함하지 않는다. `ReadContext`는 매 호출 다시 인가한다.

`JudgePolicyReader`는 app이 Judge에 주입하는 독립적인 등록 조회 경계다.

```python
async def read_case_policy(request: JudgePolicyReadRequest) -> JudgePolicyReadResult
```

`JudgePolicyReadRequest`는 정확히 `run_key: RunKey`, `context: ReadContext`, `case_ref: Ref`, `expected_policy: ExpectedAccessPolicySnapshot | None`을 가진다. `JudgePolicyReadResult`는 정확히 `run_key: RunKey`, `case_ref: Ref`, `status: ResultStatus`, `expected_policy: ExpectedAccessPolicySnapshot | None`, `reason_codes: tuple[ReasonCode, ...]`를 가진다. Reader는 선택값을 권한 부여 입력으로 신뢰하지 않고 등록 원본의 정확한 `policy_ref`, `SourceVersion`, 전체 불변 내용을 인증한 뒤 case의 정본 정책을 독립 조회한다. `None`이면 정본에서 해결한다. 진짜 등록 정책이 다른 case에 적용된 경우에는 case 정본을 반환하고 Judge가 `COMPLETE + UNDECIDABLE + expected_access_policy_invalid`로 남긴다. 위조된 source/full content, source 검증 실패는 `FAILED + source_unverified`, 조회 장애는 해당 실패 사유로 남긴다. 등록된 case에 정책이 없으면 `COMPLETE`와 `expected_access_policy_missing`, 미등록 case는 `FAILED + not_found`다. Reader는 요청의 run/case를 결과에 그대로 반영하고, 제공자는 그 run에 묶인 불변 mapping과 provenance를 검증할 의무가 있다. `policy.source`만으로 case mapping의 정본성을 증명했다고 간주하지 않는다. Knowledge의 case resolver나 다른 서비스 DB 직접 조회를 사용하지 않는다.

Reader의 결과 상태는 `COMPLETE` 또는 `FAILED`뿐이다. 정상 정책 결과는 사유가 비어 있고, 정상 부재는 **`reason_codes == (ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,)`**만 허용한다. 중복·다른 사유 추가·빈 사유는 거부한다. 실패 결과에는 정책이 없고 §2의 명시적 호출·감사 실패 허용목록에 속하는 사유가 하나 이상 있어야 한다. 정상 부재 마커는 실패 설명으로 쓸 수 없다. 등록 원본의 생성·영속화와 case 연결은 후속 app 저장 경계가 소유한다. 등록 변경은 새 revision/run으로 반영한다. 동일 결과를 cache에서 재사용할 때도 `ReadContext`의 현재 접근 권한을 다시 검사한다.

## 2. 결과와 판정 불변식

`JudgeResult`는 `run_key: RunKey`, `status: ResultStatus`, `verdict: Verdict | None`, `projection_event: VerdictProjected | None`, `reason_codes: tuple[ReasonCode, ...]`를 가진다. 제공자는 요청과 결과의 run·case 대응도 확인한다. 결과 생성자만으로 원래 요청을 알 수는 없다.

- `COMPLETE`: Verdict와 일치하는 같은 run의 `VerdictProjected`가 필수이고 호출 실패 사유는 빈 tuple이다. projection의 verdict와 receipt/fingerprint binding은 기존 C4-A 계약을 만족해야 한다. 지역 타입 검사는 실제 감사 commit 증명이 아니다.
- `FAILED`: Verdict와 projection은 모두 `None`이고 명시적 호출·감사 실패 허용목록의 사유가 하나 이상이다. 판정 진단 사유를 단독으로 사용하거나 실패 사유와 섞으면 거부한다.
- `PARTIAL`: Judge 결과에서는 허용하지 않는다.

공개 `Verdict`는 `verdict.v2`만 발행·검증한다. 값은 `CONFIRMED`, `SUSPECTED`, `UNDECIDABLE`, `ALLOWED`다.

- `CONFIRMED`는 세 CheckState가 모두 `YES`이고 정책 출처·비교·근거가 있는 기존 조건을 유지한다.
- `SUSPECTED`는 `policy_check=UNKNOWN`, `identity_check=YES`, `data_check=YES`, 비교 참조·근거·사유가 모두 있어야 한다.
- `ALLOWED`는 `policy_check=NO`, `expected_policy_source` 존재, `policy_allows` 또는 `sharing_or_delegation_allows` 사유가 필요하다. identity/data가 YES일 필요가 없고 비교·근거가 없어도 된다. HTTP 성공이나 취약점 부재를 뜻하지 않는다.
- `UNDECIDABLE`은 사유를 보존하며, 특히 `data_unverifiable`을 근거 부족으로 기록할 수 있다. 이는 Judge 작업 자체의 `COMPLETE`와 함께 반환될 수 있다.

`SUSPECTED`는 단순한 정책 부재만으로 만들 수 없다. 정책이 `UNKNOWN`이어야 하고, 서로 다른 검증 주체 A/B, 비자명 교차 데이터, 비교 참조와 근거가 모두 확인되며 반사·공통 템플릿 가능성이 제거되어야 한다. 명시적이고 유효한 공유/위임 ALLOW가 있으면 `SUSPECTED`로 발행하지 않는다. 직접 ALLOW와 무관한 공유/위임 UNKNOWN은 직접 ALLOW를 불필요하게 막지 않지만, 그 UNKNOWN이 현재 허용 여부를 무효화할 가능성이 있으면 `UNDECIDABLE`이다. 직접 DENY라도 실제 적용 가능한 공유/위임 ALLOW가 검증되면 `ALLOWED`다. 검증된 직접 ALLOW는 `ALLOWED`이며, 자료 부족이나 정상적인 신원 부재는 `UNDECIDABLE`일 수 있다. 원본 변조·run/case/resource/subject 불일치·receipt 오류·검증 포트 장애는 정상적인 근거 부족과 달리 `JudgeResult.FAILED`다.

ALLOWED의 구조 조건은 서로 다른 A/B 주체나 교차 노출의 확인을 요구하지 않는다. 실제 서비스는 평가 주체 B의 유효한 신원, 신뢰된 등록 정책 원본과 target/environment/resource/operation/subject·유효기간·provenance 대응을 확인해야 한다. CONFIRMED는 명시적 DENY와 공유·위임 모두 RESOLVED_NONE까지 검증해야 한다.

생성자는 CheckState·참조·사유 존재와 ALLOWED의 필수 허용 사유를 검사한다. 사유 라벨 자체를 검증된 정책 근거로 인정하지 않으며, SUSPECTED의 허용 정책 배제와 신호·사유의 실제 의미 대조는 Judge 서비스 책임이다. 타입 생성 성공만으로 정책·신원·교차 데이터가 검증됐다고 취급하지 않는다.

### 2.1 ALLOWED 발행 전 Judge 서비스 불변식

`identity_check`는 **A/B가 검증된 서로 다른 주체인지**, `data_check`는 **비자명한 교차 데이터 노출이 있는지**를 나타낸다. 평가 주체 B의 신원이 확인됐는지를 단독으로 표현하는 필드가 아니다. 따라서 B가 검증됐어도 A·비교 근거가 없으면 두 check는 UNKNOWN일 수 있다. ALLOWED는 이 교차 노출을 주장하지 않는 정책상 허용 판정이며, SUSPECTED보다 강한 ‘실제 접근 정상’ 판정이 아니다.

생성자의 정책 출처·허용 사유 존재는 **구조적 필요조건**이다. `POLICY_ALLOWS`나 `SHARING_OR_DELEGATION_ALLOWS` 라벨만으로는 실제 정책 출처·신원·인가를 증명하지 않는다. 아래 조건은 후속 `JudgePort.judge` 제공자 구현이 ALLOWED를 발행하기 전에 집행해야 한다. 계약 생성 성공이나 PR #34의 journal/publisher 통과로 이를 충족했다고 표시하지 않는다.

| 추적 ID | 서비스 불변식과 책임 |
|---|---|
| `J-ALLOW-01` | Judge가 평가 주체 B의 `IdentityResult` 원본·신원 Evidence·WebDiag 감사 commit을 독립 확인한다. run·subject·정책의 evaluated_subject와 판정 기준 시각의 유효성이 일치해야 한다. A/B 구별 check가 UNKNOWN이어도 **B의 검증은 생략하지 않는다**. |
| `J-ALLOW-02` | app 등록 경계와 Judge가 독립적인 case↔정책 정본, policy_ref·SourceVersion·전체 내용·target/environment/resource/operation/subject·provenance를 확인한다. Host의 snapshot·임의 SourceVersion·reason label만으로 허용하지 않는다. |
| `J-ALLOW-03` | Judge 오라클은 검증된 직접 ALLOW 또는 적용 가능한 공유/위임 ALLOW에서만 허용 사유를 도출한다. 명시적 DENY에 유효한 허용 예외가 없으면 ALLOWED를 발행하지 않는다. 허용을 무효화할 수 있는 UNKNOWN은 UNDECIDABLE로 보존한다. |
| `J-ALLOW-04` | Judge가 정책과 B 신원을 같은 신뢰된 기준 시각에서 검증한다. 비교 없는 현재 판정은 한 번 고정한 시각을 occurred_at에 보존하며 committed_at으로 대신하지 않는다. 기준 시각에서 정상적으로 확인된 만료·UNKNOWN은 ALLOWED가 아니다. |
| `J-ALLOW-05` | 매 호출 현재 ReadContext를 재인가하고, 캐시된 결과에도 적용한다. 새 현재 시점 요청에 과거 ALLOWED를 재사용하지 않으며 정책·시각·submission 멱등 규칙은 §4를 따른다. |
| `J-ALLOW-06` | 앞선 입력 검증을 마친 판정만 v2 fingerprint→자기 감사 commit→verify_committed→Projection 순서로 발행한다. 입력 관문 미충족은 **ALLOWED commit/publish 0건**이어야 한다. 정상 근거 부족의 UNDECIDABLE commit과 검증 실패의 FAILED를 구분한다. |

후속 Judge 서비스 PR의 담당자는 최민준(`mminjun`)이며, case↔정책 정본 구현은 app 담당 이동찬과 연결한다. 다음은 아직 구현 완료가 아닌 **서비스 PR의 필수 검증 항목**이다. `_UNMAPPED` 매핑이나 내부 ALLOWED enum 추가만으로 완료 처리하지 않는다.

- [ ] `J-ALLOW-01/04`: B 신원 부재·UNKNOWN·기준 시각에서 만료 → COMPLETE/UNDECIDABLE + `subject_not_verified`; ALLOWED 발행 없음. 신원 원본 변조·감사/run/subject 불일치·검증 장애 → FAILED.
- [ ] `J-ALLOW-02/03`: 정상 등록됐지만 다른 case의 ALLOW → UNDECIDABLE/`expected_access_policy_invalid`; 위조 원본·검증/조회 장애 → FAILED. 실제 DENY 사례에 다른 ALLOW를 붙여 결과를 숨기지 못함.
- [ ] `J-ALLOW-03`: 허용 라벨만 전달하거나 유효한 허용 예외 없는 DENY → ALLOWED 없음. 기존 CONFIRMED/SUSPECTED/UNDECIDABLE 조건을 보존.
- [ ] `J-ALLOW-01..04`: B 신원·정본·유효기간·직접/공유 허용이 모두 검증되면 A/비교/교차 노출이 없어도 ALLOWED 가능. 이때 identity_check/data_check UNKNOWN은 검증 면제가 아닌 서로 다른 축의 상태임을 확인.
- [ ] `J-ALLOW-05/06`: 캐시 반환의 현재 권한 거부, 원본 감사 검증 실패, 새 현재 시점의 재판정을 각각 검사하고 실패한 관문을 ALLOWED로 우회하지 않음.

이 서비스 관문과 테스트가 구현·검증되기 전에는 ALLOWED 발행 경로를 실제 app 조립에서 활성화하지 않는다. 이번 C4-B는 그 전제와 추적 항목을 고정하며 Judge 내부 구현은 변경하지 않는다.

### ReasonCode 분리

이번 공유 계약에 추가하는 정확한 9개는 다음과 같다.

`policy_allows`, `sharing_or_delegation_allows`, `expected_access_unknown`, `subject_not_verified`, `subjects_not_distinct`, `data_no_match`, `data_reflection_present`, `data_template_present`, `data_unverifiable`.

기존 `expected_access_policy_missing`, `expected_access_policy_invalid`, `sharing_or_delegation_unknown`은 재사용한다. `policy_deny_resolved`, `subjects_distinct_verified`, `data_nontrivial_match` 같은 긍정 근거는 ReasonCode에 추가하지 않고 CheckState·구조 조건으로 표현한다. `Verdict.reason_codes`는 판정 이유이고 `JudgeResult.reason_codes`는 호출·권한·revision·감사 실패 이유다. COMPLETE JudgeResult의 호출 사유는 비어 있어야 한다. PR #34의 journal/publisher와 memory adapter는 이번 문서에서 재구현하지 않으며, 기존 미대응 9개 매핑과 ALLOWED 매핑·strict xfail은 후속 Judge PR이다. `data_unverifiable`가 shared enum에 추가되어도 adapter mapping이 완료된 것은 아니다. 내부/public enum을 합칠 때 기존 변환 테스트는 삭제하지 않고 항등과 전체 값 대응을 검증한다.

`abc2lab_contracts.reason_codes`는 사유 역할과 FAILED 허용목록을 불변 `frozenset`으로 공개한다.

| 집합 | 용도와 범위 |
|---|---|
| `JUDGE_DIAGNOSTIC_REASON_CODES` | 위 신규 9개와 재사용 3개, 정확히 12개. 두 Judge 결과의 FAILED에서는 모두 금지한다. |
| `CALL_AUDIT_REASON_CODES` | 나머지 호출·감사 사유군. 감사의 긍정 상태인 `COMPARISON_CANARY_PASSED`도 포함하므로 전체를 실패 허용목록으로 사용하지 않는다. |
| `CALL_AUDIT_FAILURE_REASON_CODES` | 명시적으로 열거한 실패 사유 허용목록. 현재 60개이며 두 Judge 결과의 FAILED가 이 목록만 허용한다. `COMPARISON_CANARY_PASSED`는 제외한다. |

2026-10-22 기준 enum 73개는 진단 12개와 호출·감사 61개로 중복 없이 전수 분류된다. 테스트가 두 역할군의 합집합과 `set(ReasonCode)`의 동등성·교집합 부재를 검사하므로 enum 추가 시 분류도 함께 갱신해야 한다. 실패 허용목록은 enum의 여집합으로 계산하지 않는다. 새 코드가 명시적으로 허용되기 전에는 FAILED 사유가 될 수 없다. `EXPECTED_ACCESS_POLICY_MISSING`을 포함한 진단 사유나 canary 성공 마커는 유효한 실패 사유와 섞여도 거부한다.

이 변경은 `JudgeResult`·`JudgePolicyReadResult`의 실패 경계를 강화한다. 다른 결과 타입·Evidence 감사와 기존 Verdict의 사유 허용 범위를 일괄 변경하지 않으며 enum 값·fingerprint payload·golden vector도 변경하지 않는다.

Verdict 사유는 판정 의미를, `JudgeResult.reason_codes`는 호출·저장·권한·감사 실패를 표현한다. 같은 submission의 정규 의미 입력은 최초 해결한 정책·SourceVersion·판정 기준 시각을 보존해 재사용하되 매 호출 권한을 다시 검사한다. 다른 submission의 새 시점 ALLOWED는 새 revision과 감사 이벤트를 만든다. revision CAS 충돌과 감사 불확실성은 자동 재시도·재전송 없이 실패로 남긴다.

## 3. Fingerprint와 시간

Verdict payload 필드는 기존 집합을 유지하고 `record_kind=verdict`, `schema_version=verdict.v2`를 사용한다. v1 Verdict vector와 운영 호환 경로는 유지하지 않고 기존 벡터의 Verdict 항목을 v2로 교체한다. C1/C2·Evidence·Observation·ExpectedPolicy 벡터와 `canonical-json.v1` codec은 변경하지 않는다. `source_event`는 fingerprint 전에 고정하고 감사 receipt는 payload에 넣지 않는다. `VerdictProjected` 검증과 journal 재계산은 같은 `verdict_fingerprint` 경로를 사용한다.

`VerdictV2` 별도 클래스나 `Verdict.schema_version`·`evaluated_at` 필드는 추가하지 않는다. 버전은 fingerprint envelope에만 있고 기존 Verdict 업무 필드 집합은 유지한다.

비교 근거가 있으면 검증된 Evidence의 `observed_at`, 없는 ALLOWED는 Judge가 주입받은 하나의 신뢰된 판정 시각을 정책 평가 기준으로 사용하고 같은 값을 감사 `occurred_at`으로 보존한다. `AuditReceipt.committed_at`과 `occurred_at`은 임의로 동일시하지 않는다. 여러 비교 관찰 시각을 하나로 선택하는 규칙, occurred_at 영속화는 후속 구현에서 확정한다.

### 3.1 v1 지문 소비자·저장 자료 점검

2026-10-22, PR #39의 `da8ad05` 추적 파일을 점검했다. `verdict.v1`, 구 벡터 ID와 교체 전 Verdict golden SHA-256, 지문 소비 경로·데이터 fixture를 확인했으며 결과는 다음과 같다.

| 범위 | 확인한 상태 |
|---|---|
| Report·Knowledge의 src/tests | 패키지 scaffold이며 Verdict journal·저장 지문·v1 digest 하드코딩 소비자가 없다. |
| app·루트 eval | app은 scaffold이고 eval은 README만 있다. v1 Verdict 평가 fixture나 저장 지문이 없다. |
| Judge journal | 현재 메모리 어댑터가 업무 내용으로 `verdict_fingerprint`를 호출해 binding을 만들고 검증 시 다시 계산한다. v1 digest 상수나 추적된 영속 journal 자료는 없다. |
| 고정 벡터 | `fingerprint-v1-vectors.json`의 Verdict 항목은 `verdict-v2-c4` 1개다. 파일명·codec의 v1은 Verdict schema와 별개다. 교체 전 Verdict digest는 현재 추적 파일에서 발견되지 않았다. |
| 남은 v1 표기 | 설계 문서의 교체 설명과 `test_verdict_projection_rejects_same_payload_with_legacy_v1_digest`의 의도적인 거부 시험이다. 운영 v1 호환 경로나 보존한 v1 golden 항목이 아니다. |

따라서 현재 저장소의 구현된 소비자가 저장된 v1 지문에 의존하는 사례는 확인되지 않았다. 이는 CI green에서 추정한 결론이 아니라 소스·추적 자료 점검 결과다. Git 이력, 개인 로컬/untracked 자료, 실행 중 프로세스, 외부 DB·배포 journal의 상태까지 확인한 것은 아니다. 그런 v1 자료가 실제로 있다면 별도 이관을 확정해야 하며 원본 v1 영수증의 digest를 v2 값으로 덮어쓰지 않는다.

## 4. 멱등성·revision·감사

동일 `(run_key, case_ref)`에는 안정적인 `verdict_ref`를 사용한다. Verdict revision은 불변 판정의 버전이고 감사 sequence는 producer journal의 순번이므로 서로 대체하지 않는다. 같은 `submission_ref`와 정규 의미 입력이면 최초 해결한 정책·SourceVersion·판정 기준 시각·결과·projection·receipt를 재사용한다. `ReadContext` 자체는 의미 입력에서 제외하되 현재 권한은 매번 재검사한다. 같은 submission인데 의미 입력이 다르면 `FAILED + idempotency_conflict`다. 다른 submission이라도 과거의 동일 비교 Evidence·의미 입력·oracle_version에 대한 결과는 재사용할 수 있다. 반면 비교 없는 현재 시점 정책 평가는 독립적인 새 판정이므로 동일한 ALLOWED라도 새 revision과 감사 이벤트를 발행한다. 현재 revision은 Judge 내부 저장소에서 읽고 `JudgeRequest`에 expected_revision을 추가하지 않는다. 동시 새 revision 선점 충돌은 `FAILED + revision_conflict`이며 CAS 자동 재시도나 자동 재판정은 하지 않는다.

감사 commit 결과가 불명확하면 동일 원본을 재조회하고 검증한다. 동일 기록이 확인되면 재사용하고, 확인할 수 없으면 `FAILED`로 반환한다. 불명확한 상태에서 판정을 자동 재발행하거나 Gateway에 재전송하지 않는다.

## 5. 범위와 후속 구현 경계

이번 계약은 네트워크·DB·대상 HTTP 호출 없이 타입·binding·스크립트형 포트 예제를 검증한다. PR #34의 `VerdictPublisher`, `VerdictJournal`, memory adapter와 fingerprint 소비 경로는 이미 존재하며 이번 변경에서 재구현하지 않는다. 정책 정본 생성·case mapping 영속화는 app 등록 경계의 후속 구현이고, 새 Judge 포트 조립·오라클/사유 매핑은 Judge 담당자의 후속 PR이다. 내부/public enum 통합을 선택하면 담당자가 기존 변환 테스트를 유지해 항등과 전체 값 대응을 확인한다. S1 포트 집계는 `29개(비동기 26, 동기 3)`이며 이 문서는 그중 Judge와 정책 등록 조회 경계를 정의한다.

ALLOWED의 실제 서비스 발행 조건과 미완료 인수 테스트는 [§2.1의 J-ALLOW-01~06](#21-allowed-발행-전-judge-서비스-불변식)으로 추적한다. 계약 생성자의 UNKNOWN 허용을 신원·정책 검증 면제로 해석하지 않는다. v2 교체의 현재 소비자 점검 결과와 확인 범위는 §3.1에 기록한다.

현재 구현과 별개로 남은 원래 네 가지 구현 공백은 다음과 같다: 비교 Evidence 없이 ALLOWED를 판정할 때 case와 정책 resource/operation 대응을 신뢰된 등록 조회에서 검증하는 방법, owner/cross Evidence의 서로 다른 `observed_at` 선택, `occurred_at`의 journal 영속화, 안정적인 verdict_ref·submission 멱등성·CAS·감사 commit의 원자적 조정. 이 문서는 이를 임의 필드나 서비스 의존성으로 해결했다고 주장하지 않는다.

## 6. 요구사항 주제별 반영 범위

| 주제 | 반영 위치 |
|---|---|
| 공개 Judge/Reader 타입과 run·case 불변식 | §1 |
| COMPLETE/FAILED/PARTIAL 및 Verdict 구조 조건 | §2 |
| ReasonCode 9개·재사용·긍정 근거 분리 | §2 ReasonCode |
| 정책 ALLOW/DENY·공유/위임 UNKNOWN 의미 | §2 |
| `verdict.v2`·vector 교체·receipt 제외 | §3 |
| 판정 시각과 감사 시각 구분 | §3 |
| 안정 ref·revision/sequence·멱등·CAS·감사 불확실성 | §4 |
| PR #34 소비자와 후속 Judge 구현 경계 | §2 ReasonCode, §5 |

## 7. 로컬 검증 기록

2026-10-22, PR #38까지 반영한 `origin/main`의 `ea17ec2`를 반영한 `codex/judge-c4b-contracts`의 검증 결과다. 이 절은 공유 계약의 로컬 검증 기록이며 GitHub CI나 팀 승인 결과가 아니다. 병합은 팀 리뷰 후 별도로 확인한다. 확정 결정 ①~㉚의 별도 번호표는 제공되지 않았으므로 §6에서 요구사항 주제별로 대응하며 번호를 추정하지 않는다.

| 실행 명령 | 실제 결과 |
|---|---|
| `uv run --no-project --python 3.13.15 scripts/dev.py check contracts` | Ruff lint/format·strict mypy 41개 파일·테스트 **422개 통과** |
| `uv run --no-project --python 3.13.15 scripts/dev.py check judge` | Ruff lint/format·strict mypy 14개 파일·**43개 통과, 기존 xfail 1개**. 실제 journal·publisher 회귀 포함 |
| `uv run --locked --no-sync lint-imports` (`check all`에서도 실행) | **6개 경계 유지·위반 0개** |
| `uv run --no-project --python 3.13.15 scripts/dev.py check all` | pre-commit Ruff·mypy 73개 소스·전체 **667개 통과, 기존 xfail 2개**·전체 패키지 wheel/sdist·외부 라이브러리 import smoke 통과 |
| `test_judge_reason_codes.py` (contracts/전체 검사에 포함) | **83개 통과**. enum 전수 분류·실패 허용목록·진단/실패 혼합 거부·정상 부재에 모든 enum 사유 추가/중복 거부 |
| 고정 벡터·변경 범위 | Verdict 1개만 v2로 교체, 다른 10개 보존. Judge 및 타 서비스·루트 설정·lock 변경 없음 |

모든 명령은 로컬 uv cache를 `/tmp`에 두고 실행했다. 새 xfail을 추가하거나 기존 테스트를 삭제하지 않았다. 남은 Judge xfail은 미대응 ReasonCode 매핑, 다른 하나는 Gateway의 기존 전송 사유 매핑이다. 이 검증은 정책 등록 정본·case mapping 구현, 실제 인가·영속 감사·대상 전송·S1 통합의 완료나 GitHub CI/팀 승인 결과를 의미하지 않는다.
