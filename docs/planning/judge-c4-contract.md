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

Reader의 정상 결과는 `COMPLETE` 또는 `FAILED`뿐이다. 정상 정책 결과는 사유가 비어 있고, 정상 부재는 누락 사유가 있어야 한다. 실패 결과에는 정책이 없고 하나 이상의 사유가 있어야 한다. 등록 원본의 생성·영속화와 case 연결은 후속 app 저장 경계가 소유한다. 등록 변경은 새 revision/run으로 반영한다. 동일 결과를 cache에서 재사용할 때도 `ReadContext`의 현재 접근 권한을 다시 검사한다.

## 2. 결과와 판정 불변식

`JudgeResult`는 `run_key: RunKey`, `status: ResultStatus`, `verdict: Verdict | None`, `projection_event: VerdictProjected | None`, `reason_codes: tuple[ReasonCode, ...]`를 가진다. 제공자는 요청과 결과의 run·case 대응도 확인한다. 결과 생성자만으로 원래 요청을 알 수는 없다.

- `COMPLETE`: Verdict와 일치하는 같은 run의 `VerdictProjected`가 필수이고 호출 실패 사유는 빈 tuple이다. projection의 verdict와 receipt/fingerprint binding은 기존 C4-A 계약을 만족해야 한다. 지역 타입 검사는 실제 감사 commit 증명이 아니다.
- `FAILED`: Verdict와 projection은 모두 `None`이고 실패 사유가 하나 이상이다.
- `PARTIAL`: Judge 결과에서는 허용하지 않는다.

공개 `Verdict`는 `verdict.v2`만 발행·검증한다. 값은 `CONFIRMED`, `SUSPECTED`, `UNDECIDABLE`, `ALLOWED`다.

- `CONFIRMED`는 세 CheckState가 모두 `YES`이고 정책 출처·비교·근거가 있는 기존 조건을 유지한다.
- `SUSPECTED`는 `policy_check=UNKNOWN`, `identity_check=YES`, `data_check=YES`, 비교 참조·근거·사유가 모두 있어야 한다.
- `ALLOWED`는 `policy_check=NO`, `expected_policy_source` 존재, `policy_allows` 또는 `sharing_or_delegation_allows` 사유가 필요하다. identity/data가 YES일 필요가 없고 비교·근거가 없어도 된다. HTTP 성공이나 취약점 부재를 뜻하지 않는다.
- `UNDECIDABLE`은 사유를 보존하며, 특히 `data_unverifiable`을 근거 부족으로 기록할 수 있다. 이는 Judge 작업 자체의 `COMPLETE`와 함께 반환될 수 있다.

`SUSPECTED`는 단순한 정책 부재만으로 만들 수 없다. 정책이 `UNKNOWN`이어야 하고, 서로 다른 검증 주체 A/B, 비자명 교차 데이터, 비교 참조와 근거가 모두 확인되며 반사·공통 템플릿 가능성이 제거되어야 한다. 명시적이고 유효한 공유/위임 ALLOW가 있으면 `SUSPECTED`로 발행하지 않는다. 직접 ALLOW와 무관한 공유/위임 UNKNOWN은 직접 ALLOW를 불필요하게 막지 않지만, 그 UNKNOWN이 현재 허용 여부를 무효화할 가능성이 있으면 `UNDECIDABLE`이다. 직접 DENY라도 실제 적용 가능한 공유/위임 ALLOW가 검증되면 `ALLOWED`다. 검증된 직접 ALLOW는 `ALLOWED`이며, 자료 부족이나 정상적인 신원 부재는 `UNDECIDABLE`일 수 있다. 원본 변조·run/case/resource/subject 불일치·receipt 오류·검증 포트 장애는 정상적인 근거 부족과 달리 `JudgeResult.FAILED`다.

ALLOWED의 구조 조건은 서로 다른 A/B 주체나 교차 노출의 확인을 요구하지 않는다. 실제 서비스는 평가 주체 B의 유효한 신원, 신뢰된 등록 정책 원본과 target/environment/resource/operation/subject·유효기간·provenance 대응을 확인해야 한다. CONFIRMED는 명시적 DENY와 공유·위임 모두 RESOLVED_NONE까지 검증해야 한다.

생성자는 CheckState·참조·사유 존재와 ALLOWED의 필수 허용 사유를 검사한다. 사유 라벨 자체를 검증된 정책 근거로 인정하지 않으며, SUSPECTED의 허용 정책 배제와 신호·사유의 실제 의미 대조는 Judge 서비스 책임이다. 타입 생성 성공만으로 정책·신원·교차 데이터가 검증됐다고 취급하지 않는다.

### ReasonCode 분리

이번 공유 계약에 추가하는 정확한 9개는 다음과 같다.

`policy_allows`, `sharing_or_delegation_allows`, `expected_access_unknown`, `subject_not_verified`, `subjects_not_distinct`, `data_no_match`, `data_reflection_present`, `data_template_present`, `data_unverifiable`.

기존 `expected_access_policy_missing`, `expected_access_policy_invalid`, `sharing_or_delegation_unknown`은 재사용한다. `policy_deny_resolved`, `subjects_distinct_verified`, `data_nontrivial_match` 같은 긍정 근거는 ReasonCode에 추가하지 않고 CheckState·구조 조건으로 표현한다. `Verdict.reason_codes`는 판정 이유이고 `JudgeResult.reason_codes`는 호출·권한·revision·감사 실패 이유다. COMPLETE JudgeResult의 호출 사유는 비어 있어야 한다. PR #34의 journal/publisher와 memory adapter는 이번 문서에서 재구현하지 않으며, 기존 미대응 9개 매핑과 ALLOWED 매핑·strict xfail은 후속 Judge PR이다. `data_unverifiable`가 shared enum에 추가되어도 adapter mapping이 완료된 것은 아니다. 내부/public enum을 합칠 때 기존 변환 테스트는 삭제하지 않고 항등과 전체 값 대응을 검증한다.

Verdict 사유는 판정 의미를, `JudgeResult.reason_codes`는 호출·저장·권한·감사 실패를 표현한다. 같은 submission의 정규 의미 입력은 최초 해결한 정책·SourceVersion·판정 기준 시각을 보존해 재사용하되 매 호출 권한을 다시 검사한다. 다른 submission의 새 시점 ALLOWED는 새 revision과 감사 이벤트를 만든다. revision CAS 충돌과 감사 불확실성은 자동 재시도·재전송 없이 실패로 남긴다.

## 3. Fingerprint와 시간

Verdict payload 필드는 기존 집합을 유지하고 `record_kind=verdict`, `schema_version=verdict.v2`를 사용한다. v1 Verdict vector와 운영 호환 경로는 유지하지 않고 기존 벡터의 Verdict 항목을 v2로 교체한다. C1/C2·Evidence·Observation·ExpectedPolicy 벡터와 `canonical-json.v1` codec은 변경하지 않는다. `source_event`는 fingerprint 전에 고정하고 감사 receipt는 payload에 넣지 않는다. `VerdictProjected` 검증과 journal 재계산은 같은 `verdict_fingerprint` 경로를 사용한다.

`VerdictV2` 별도 클래스나 `Verdict.schema_version`·`evaluated_at` 필드는 추가하지 않는다. 버전은 fingerprint envelope에만 있고 기존 Verdict 업무 필드 집합은 유지한다.

비교 근거가 있으면 검증된 Evidence의 `observed_at`, 없는 ALLOWED는 Judge가 주입받은 하나의 신뢰된 판정 시각을 정책 평가 기준으로 사용하고 같은 값을 감사 `occurred_at`으로 보존한다. `AuditReceipt.committed_at`과 `occurred_at`은 임의로 동일시하지 않는다. 여러 비교 관찰 시각을 하나로 선택하는 규칙, occurred_at 영속화는 후속 구현에서 확정한다.

## 4. 멱등성·revision·감사

동일 `(run_key, case_ref)`에는 안정적인 `verdict_ref`를 사용한다. Verdict revision은 불변 판정의 버전이고 감사 sequence는 producer journal의 순번이므로 서로 대체하지 않는다. 같은 `submission_ref`와 정규 의미 입력이면 최초 해결한 정책·SourceVersion·판정 기준 시각·결과·projection·receipt를 재사용한다. `ReadContext` 자체는 의미 입력에서 제외하되 현재 권한은 매번 재검사한다. 같은 submission인데 의미 입력이 다르면 `FAILED + idempotency_conflict`다. 다른 submission이라도 과거의 동일 비교 Evidence·의미 입력·oracle_version에 대한 결과는 재사용할 수 있다. 반면 비교 없는 현재 시점 정책 평가는 독립적인 새 판정이므로 동일한 ALLOWED라도 새 revision과 감사 이벤트를 발행한다. 현재 revision은 Judge 내부 저장소에서 읽고 `JudgeRequest`에 expected_revision을 추가하지 않는다. 동시 새 revision 선점 충돌은 `FAILED + revision_conflict`이며 CAS 자동 재시도나 자동 재판정은 하지 않는다.

감사 commit 결과가 불명확하면 동일 원본을 재조회하고 검증한다. 동일 기록이 확인되면 재사용하고, 확인할 수 없으면 `FAILED`로 반환한다. 불명확한 상태에서 판정을 자동 재발행하거나 Gateway에 재전송하지 않는다.

## 5. 범위와 후속 구현 경계

이번 계약은 네트워크·DB·대상 HTTP 호출 없이 타입·binding·스크립트형 포트 예제를 검증한다. PR #34의 `VerdictPublisher`, `VerdictJournal`, memory adapter와 fingerprint 소비 경로는 이미 존재하며 이번 변경에서 재구현하지 않는다. 정책 정본 생성·case mapping 영속화는 app 등록 경계의 후속 구현이고, 새 Judge 포트 조립·오라클/사유 매핑은 Judge 담당자의 후속 PR이다. 내부/public enum 통합을 선택하면 담당자가 기존 변환 테스트를 유지해 항등과 전체 값 대응을 확인한다. S1 포트 집계는 `29개(비동기 26, 동기 3)`이며 이 문서는 그중 Judge와 정책 등록 조회 경계를 정의한다.

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
| `uv run --no-project --python 3.13.15 scripts/dev.py check contracts` | Ruff lint/format·strict mypy 39개 파일·테스트 **339개 통과** |
| `uv run --no-project --python 3.13.15 scripts/dev.py check judge` | Ruff lint/format·strict mypy 14개 파일·**43개 통과, 기존 xfail 1개**. 실제 journal·publisher 회귀 포함 |
| `uv run --locked --no-sync lint-imports` (`check all`에서도 실행) | **6개 경계 유지·위반 0개** |
| `uv run --no-project --python 3.13.15 scripts/dev.py check all` | pre-commit Ruff·mypy 72개 소스·전체 **584개 통과, 기존 xfail 2개**·전체 패키지 wheel/sdist·외부 라이브러리 import smoke 통과 |
| 고정 벡터·변경 범위 | Verdict 1개만 v2로 교체, 다른 10개 보존. Judge 및 타 서비스·루트 설정·lock 변경 없음 |

모든 명령은 로컬 uv cache를 `/tmp`에 두고 실행했다. 새 xfail을 추가하거나 기존 테스트를 삭제하지 않았다. 남은 Judge xfail은 미대응 ReasonCode 매핑, 다른 하나는 Gateway의 기존 전송 사유 매핑이다. 이 검증은 정책 등록 정본·case mapping 구현, 실제 인가·영속 감사·대상 전송·S1 통합의 완료나 GitHub CI/팀 승인 결과를 의미하지 않는다.
