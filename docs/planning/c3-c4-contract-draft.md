# C3·C4 최소 계약 초안 (gateway/judge 소유 범위)

상태: **제안 / 이동찬 리뷰 반영 (2026-10-21)**. 작성 최민준. [C1·C2](s1-development-status.md#1-작은-계약-pr로-다시-시작)와 병렬로 제안한 C3·C4의 **최소 타입·Protocol** 초안이다. 구현·벡터·fake는 포함하지 않는다. 이 초안은 [S1 API 상세 규격](s1-api-spec.md)과 [PoC 보고서 계약](poc-report-design.md)의 필드를 구현 가능한 Protocol 경계로 좁힌 것이며, 상위 두 문서가 충돌 시 우선한다. 현재 담당은 [배정표](../module-development.md#담당-배정)를 따른다.

## 1. 범위와 선행 의존

이 초안은 Gateway의 capture 소비 경계와 Judge의 제공 경계를 다룬다. Evidence 제공·Knowledge·Host·Report 경계는 아래 담당자가 별도 계약 PR로 제안한다. 최민준이 Report도 맡지만, Report 계약은 이 초안의 Judge 계약과 별도 작업으로 유지한다.

| 계약 | 이 초안의 범위(최민준) | 후속 별도 계약과 현재 담당 |
|---|---|---|
| C3 로컬 Evidence | Gateway→로컬 Evidence `capture` 포트, `ExecutedRequestView`, 실행 전용 `RawResponse` | Evidence의 `seal`/`compare_and_seal`/`store_evidence`/`evidence_read_summary`, `EvidenceSummary.request_recipe`, 레시피 생성 — 이경준 |
| C4 발견·투영·보고 | Judge `judge` 포트, `JudgeRequest`/`JudgeResult`/`Verdict`/`VerdictProjected` | Knowledge의 `register_candidates`/`project`/`get_case_view` — 이동찬; Host 조립 — 이경준; Report의 `build_report` — 최민준 |

**선행:** C1 codec과 C2 타입(`Ref`, `Revision`, `RunKey`, `UtcTime`, `Purpose`, `ResultStatus`, `ReasonCode`, `CheckState`, `SourceVersion`, `AuditLink`, `IdentityResult`, `ExpectedAccessPolicySnapshot`, `ComparisonRules`, `RequestParameter`)가 선행이다. 아래 record는 그 타입을 재사용하며 **임의 dict·`Any`·서비스별 사본을 만들지 않는다**. 타입 이름·경로는 병합된 C2 계약을 따른다. fingerprint payload는 [공유 codec](fingerprint-contract.md#3-record별-payload)의 record별 adapter를 따르고, 새 record(`Verdict` 등)는 해당 계약 PR에서 typed wrapper·벡터를 추가한다. C1은 [PR #15](https://github.com/ABC2LAB/abc2lab-dast/pull/15), C2는 [PR #20](https://github.com/ABC2LAB/abc2lab-dast/pull/20)으로 main에 병합됐다. C3·C4 자체의 구현 완료를 뜻하지 않는다.

## 2. C3 — Gateway → 로컬 Evidence `capture` 경계

실행 영역 전용 **private 포트**다(§7). Gateway가 전송 직후 원문 버퍼와 실행 view를 동기로 인계하고, 소유권·정리 책임을 로컬 Evidence로 넘긴다. Host·공개 호출자가 중계하지 않는다. 동기 포트이므로 I/O·저장·장시간 계산을 하지 않고, 같은 event loop·단일 스레드에서 유한 메모리 소유권만 원자적으로 인계한다(§2.2).

```python
class LocalCapturePort(Protocol):
    def capture(self, request: CaptureRequest) -> CaptureResult: ...
    def release_captures(self, request: ReleaseCapturesRequest) -> CloseResult: ...
```

| Record | 필드 |
|---|---|
| `CaptureRequest` | `run_key: RunKey`, `attempt_ref: Ref`, `request_ref: Ref`, `operation_ref: Ref`, `resource_ref: Ref?`, `account_ref: Ref?`, `session_generation: int?`, `identity_ref: Ref?`, `observed_at: UtcTime`, `executed_request: ExecutedRequestView`, `raw_response: RawResponse` |
| `CaptureResult` | `run_key: RunKey`, `status: ResultStatus`, `capture_ref: Ref?`, `reason_codes: tuple[ReasonCode, ...]`. complete만 `capture_ref` 존재, 실패는 None·사유 |
| `ExecutedRequestView` | `run_key, request_ref, attempt_ref, operation_ref, operation_revision: Revision, resource_ref: Ref?, resource_binding_ref: Ref?, resource_binding_revision: Revision?, account_ref: Ref?, session_generation: int?, purpose: Purpose, method: str, actual_origin: str, actual_path: str, actual_parameters: tuple[RequestParameter, ...]`. actual_parameters는 지원하는 객체 GET의 비인증 path/query만, 비대상 동작은 빈 tuple. headers/cookies/form/body·인증 파라미터 제외 |
| `RawResponse` | `status_code: int`, `headers: tuple[RawHeader, ...]`, `body: bytes`. 실행 메모리 전용·비밀 포함 가능. `bytes`/`str`는 불변이라 수명은 참조·핸들 관리로 보장하며 메모리 내용 소거는 보장하지 않는다(아래 소유권·수명) |
| `RawHeader` | `name: str`, `value: str` |
| `ReleaseCapturesRequest` | `run_key: RunKey`, `capture_refs: tuple[Ref, ...]`. 빈 tuple은 해당 run의 모든 active |

**거부·정리 의미(§7, PoC §2):** 다음은 `CaptureResult.failed`, `capture_ref=None`으로 반환하고 인계받은 원문/view를 즉시 해제한다. 전송 상태(`sent/unavailable`)는 Gateway가 보존하며 capture 실패가 이를 바꾸지 않는다.

- run/request/attempt·등록 origin/method/operation·account/generation이 `executed_request`와 캡처 맥락 사이에서 불일치 → `capture_binding_mismatch`
- 지원 객체 GET의 경로·파라미터·자원 바인딩이 등록과 불일치 → `capture_binding_mismatch`
- 응답이 한도(1 MiB) 초과·파싱 실패 → `response_limit_exceeded`/`capture_unavailable` (전송은 `sent/unavailable`로 보존)

**소유권·수명(§7, 이동찬 리뷰 B):** `active -> released/expired`. 60초 TTL, 캡처당 1 MiB, run당 active 8개(§11 한도 재사용). `release_captures` 반복 호출은 멱등. 원문 버퍼·캡처 핸들·HMAC 키를 하위 API·로그·결과에 넣지 않는다. 동기 capture는 바인딩·한도 검증과 소유권 인계만 하고, 민감값 제거·데이터 분석은 비동기 seal(Evidence·이경준)의 책임이다.

`bytes`/`str`는 불변이라 '즉시 해제'는 메모리 내용의 물리적 소거가 아니라 **참조·핸들 수명 관리**를 뜻한다. 다음으로 정의한다.

- Gateway는 인계 성공 이후 원문 버퍼·view 참조를 자체 보유하지 않는다.
- Evidence는 완료·실패·취소·TTL 만료·종료 시 자신이 보유한 참조·핸들을 제거하고, released/expired는 재사용할 수 없다.
- 정리 실패 시 캡처를 사용 가능 상태로 남기지 않는다(안전 실패).
- `release_captures`의 빈 `capture_refs`(run 전체 해제)는 run 종료·중단 정리에만 쓰고, 개별 캡처 해제에는 쓰지 않는다.
- 메모리 내용의 확실한 소거가 보안 요구사항이면 전용 버퍼 타입·소거 정책을 별도 설계한다. 이 계약 범위 밖의 후속이다.

적용 사례: S1-33(다른 run/객체/계정/generation/revision 결합 → `capture_binding_mismatch`), S1-31(canary·원문·인증 값 미출력), S1-04(전송 확정 후 캡처 실패 → `sent/unavailable`).

## 3. C4 — Judge `judge` 경계

읽기·감사·판정 저장을 포함하므로 **async** 포트다. 내부 (a)(b)(c) 오라클·정규화 비교는 동기 순수 함수로 두고 포트에서 await한다(§2.2).

```python
class JudgePort(Protocol):
    async def judge(self, request: JudgeRequest) -> JudgeResult: ...
```

| Record | 필드 |
|---|---|
| `JudgeRequest` | `run_key: RunKey`, `case_ref: Ref`, `submission_ref: Ref`, `expected_policy: ExpectedAccessPolicySnapshot?`, `owner_identity: IdentityResult?`, `evaluated_identity: IdentityResult?`, `comparison_ref: Ref?` |
| `JudgeResult` | `run_key: RunKey`, `status: ResultStatus`, `verdict: Verdict?`, `projection_event: VerdictProjected?`, `reason_codes: tuple[ReasonCode, ...]`. complete는 판정과 원본 이벤트를 함께 반환, failed는 둘 다 None |
| `Verdict` | `run_key, verdict_ref: Ref, revision: Revision, case_ref, value: CONFIRMED/SUSPECTED/UNDECIDABLE, policy_check: CheckState, identity_check: CheckState, data_check: CheckState, expected_policy_source: SourceVersion?, comparison_ref: Ref?, evidence_refs: tuple[Ref, ...], oracle_version: SourceVersion, source_event: AuditLink, reason_codes` |
| `VerdictProjected` | `kind=verdict`, `event_ref, run_key, producer: Ref, source_revision: Revision, source_receipt: AuditReceipt, verdict: Verdict`. Judge가 원본 생산자, 전달자가 소유권을 바꾸지 않음(§8) |

**입력 경계:** Judge는 `comparison_ref`로 저장된 `StoredComparison`을 Evidence 읽기 포트로 **직접 가져와** 주체·유효기간·자원·정책 대응을 재검증하며, 호출자가 구성한 StoredComparison이나 원문·`CaptureRef`를 입력으로 받지 않는다. **기대 정책 신뢰(이동찬 리뷰 A):** `expected_policy`는 `app`이 주입한 불변 snapshot(또는 검증 포트)으로만 신뢰하고, 그 `SourceVersion`을 등록 정책 원본과 독립 대조한다. 호출자가 구성해 전달한 정책 내용을 그대로 믿지 않으며, 다른 모듈 DB를 직접 읽지 않는다. 등록 원본과의 일치를 확인할 수 없으면 `policy_check=unknown`으로 `UNDECIDABLE`이다. Evidence 읽기는 기존 `ReadContext` 접근 권한 검사를 유지한다. `ComparisonRules`(정규화·canary)는 Judge가 소유·정의하고 `app`이 로컬 Evidence에 주입한다(§13-6). 주체/정책 유효성은 각 근거의 `observed_at` 당시로 판단하고, 판정 시각 TTL 경과만으로 당시 유효 근거를 버리지 않는다.

**판정 규칙(§7, §9):** 세 `CheckState`가 모두 `yes`일 때만 `value=CONFIRMED`.
- (a) `policy_check`: 신뢰된 등록 정책이 B를 명시적 금지(`expected_access=deny`)하고 `sharing/delegation=resolved_none`. 표시 문구·owner 필드·목록 차이를 정책으로 승격하지 않음. 미해소·불명은 `no`/`unknown`.
- (b) `identity_check`: A·B가 유효하고 서로 다른 검증된 subject(`owner_identity`·`evaluated_identity`의 `status=verified`). 만료·불명은 유보.
- (c) `data_check`: 같은 A 객체의 정상·비자명 실데이터가 B 교차 응답에 나타나고 반사/템플릿 제외. `nontrivial_data_match=yes` + `reflection_excluded`/`template_excluded`. HTTP 200·HMAC 일치·ID echo·owner_id·공통 템플릿만으로 `yes` 불가.

부족하지만 구체적 이상이 있으면 `SUSPECTED`, 정책 부재·실행 당시 만료·자료 검증 불가는 `UNDECIDABLE`. 판정 작업 자체는 완료이므로 `JudgeResult.complete`일 수 있다. 판정/감사 저장 실패는 `failed`/None. 자료를 못 읽었다고 Gateway 재전송을 요구하지 않는다.

**SUSPECTED/UNDECIDABLE 경계(이동찬 리뷰 D — 제안, SUSPECTED 정확한 허용 조건은 팀 합의 필요):**

| 정책·신원·데이터 상황 | 권장 판정 |
|---|---|
| (a)(b)(c) 모두 검증됨 | `CONFIRMED` |
| 일부 확정 근거 부족이나 구체적 이상 징후 존재 | `SUSPECTED` 가능 |
| 등록 정책 부재 또는 실행 당시 유효성 확인 불가 | `UNDECIDABLE` |
| 명시적으로 허용된 접근 | 취약점으로 확정하지 않음 |

**멱등성과 revision(이동찬 리뷰 C):** 판정 변경은 새 `revision`으로 남기고 과거를 덮어쓰지 않는다. 같은 입력의 재호출과 새 판정을 구분한다. `Verdict.source_event`와 `VerdictProjected.source_receipt`의 생성 순서는 아래 fingerprint 절에서 고정한다.

| 상황 | 처리 |
|---|---|
| 같은 `submission_ref`, 같은 정규 입력 | 기존 `Verdict`·receipt 재사용 |
| 같은 `submission_ref`, 다른 입력 | `idempotency_conflict`(failed), 기존 판정 유지 |
| 새 근거로 재판정 | 새 submission·새 `revision` 발행 |
| 감사 저장 결과 불명 | 기존 기록을 조회·확인, 무조건 재발행하지 않음 |

**fingerprint:** `Verdict`의 payload adapter·golden vector는 이 C4 PR에서 `record_kind=verdict`, `schema_version=verdict.v1`로 추가한다(모든 business field 포함, 자체 digest 없음 — [계약 §3](fingerprint-contract.md#3-record별-payload)). `Verdict.source_event`는 fingerprint 이전에 고정된 `Verdict`의 business field다. `VerdictProjected.source_receipt`는 투영 시 생성되며 `Verdict`의 필드가 아니다 — 투영은 이미 fingerprint된 `Verdict`를 감싸므로 `Verdict` fingerprint는 투영 순서·receipt와 무관하게 결정적이다.

적용 사례: S1-07(기대 정책 누락·예외 불명 → `UNDECIDABLE`/근거 있는 `SUSPECTED`), S1-08((a)(b)(c) 충족 → `CONFIRMED`), S1-09(반사·동적·공유/위임·오류/로그인·soft-404 반례에서 `CONFIRMED` 없음), S1-05(A/B 주체 불명·만료 → 유보).

## 4. 이동찬 리뷰 반영 (2026-10-21)

초안 §4 열린 질문은 이동찬(contracts)의 리뷰로 다음과 같이 합의했다.

| 질문 | 결정 |
|---|---|
| 1. `RawResponse`를 `contracts`에 두는가 | **조건부 허용.** 실행 전용 private 타입·Protocol로 `contracts`에 정의하되, 공개 직렬화·로그·MCP·fingerprint 입력으로 노출하지 않는 경계를 명시(§2). 핵심은 타입 정의 자체가 아니라 실제 값 접근·전달 경로의 제한이다(`module-design-confirmed.md §3`) |
| 2. C3를 capture만으로 여는가 | **분리.** Gateway→Evidence `capture` 계약 PR과 Evidence의 seal/compare 구현 PR을 분리하고, 연결은 후속 통합 테스트에서 검증. 현재 Evidence 담당은 이경준이며 [재배정 기록](../module-development.md#담당-재배정-2026-10-21)을 따른다 |
| 3. `Verdict` registry 등록 시점 | C2 머지 후 **C4 Judge 경계 PR**에서 typed wrapper·adapter·golden vector를 함께 등록 |
| 4. 타입 경로·이름 | C2가 먼저 확정한 공통 타입을 재사용. C3/C4에서 중복 타입을 만들지 않음 |

리뷰의 상위 지적(A 신뢰된 등록 정책 독립 검증, B `RawResponse` 소유권·메모리, C 멱등성·revision)은 각각 §3·§2에 반영했다.

**남은 팀 합의:** `SUSPECTED`의 정확한 허용 조건(어떤 '구체적 이상 징후'가 SUSPECTED를 정당화하는지). §3의 표는 방향 제안이며 확정 규칙이 아니다.

**구현 PR에서 강화할 경계 테스트(기존 사례에 추가, 새 수용 사례 남발 금지):**

- C3: capture 실패 직후 Gateway·Evidence가 원문 참조를 보유하지 않음, 해제된 핸들 재사용 거부(S1-33·S1-31).
- C3: 한 작업의 `release_captures`가 같은 run의 다른 유효 캡처를 해제하지 않음.
- C3: 등록 요청과 `ExecutedRequestView`의 path/query/binding 한 필드만 달라도 거부(S1-33).
- C4: `expected_access`·sharing·delegation 중 하나만 바뀌어도 `CONFIRMED` 미발행(S1-08·S1-09).
- C4: 같은 submission의 중복·충돌·revision 증가 처리(S1-07~09).

구현은 C2 정합 후 각 경계 PR에서 진행한다. 이 초안은 리뷰용 제안이며 계약 구현·fake·테스트의 완료를 뜻하지 않는다.
