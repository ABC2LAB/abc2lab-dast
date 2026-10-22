# C3·C4 최소 계약 초안 (gateway/judge 소유 범위)

상태: **Gateway/Judge 경계의 초기 제안 기록 / C3 계약 #26·#27, Knowledge #30, Judge C4-B #39 및 제공자 사유 매핑 #41 반영 (2026-10-22)**. 작성 최민준. 이 초안의 capture/Judge 관련 공개 계약은 후속 별도 PR에서 이미 구현되었으므로 구현된 타입·상태는 [C3 동결안](evidence-c3-freeze.md)과 [Judge C4-B 계약](judge-c4-contract.md), 실제 `contracts` 코드를 정본으로 삼는다. Host 시작/상태/중지·Report 보고 입력/출력의 공개 계약, Judge의 실제 JudgePort 제공자 및 영속 감사는 아직 남아 있다. 초안 자체를 전체 C3/C4 서비스 완료 증거로 해석하지 않는다.

## 1. 범위와 선행 의존

이 초안은 Gateway의 capture 소비 경계와 Judge의 제공 경계를 다룬 당시 제안이다. Evidence(#27)와 Knowledge(#30), Judge(#39)의 공개 계약은 이후 별도 PR로 병합됐고, 제공자 구현은 각 담당 모듈에서 진행 중이다. Host의 진입점과 Report 공개 계약은 아직 별도 후속 작업이며, Report 담당 최민준이 제안하되 Judge 내부 구현과는 분리한다.

| 계약 | 이 초안의 담당 경계 | 2026-10-22 확인한 후속 구현/미완료 |
|---|---|---|
| C3 로컬 Evidence | Gateway→로컬 Evidence `capture`, `ExecutedRequestView`, 실행 전용 `RawResponse` — Gateway 최민준 | C3-A #26·C3 Evidence 공유 계약 #27 병합; Evidence 이경준의 메모리 캡처·seal/compare·recover #35, recipe #36 구현. 실제 Gateway 연계·내구/감사/복구 통합은 후속 |
| C4 발견·투영·판정·보고 | Judge `judge`, `JudgeRequest`/`JudgeResult`/`Verdict`/`VerdictProjected` — Judge 최민준 | KnowledgePort #30·JudgePort/Reader/`verdict.v2` #39·Judge 사유 매핑 #41 병합. Knowledge 제공자(이동찬), Host 진입점 제공자(이경준), Report 공유 계약·제공자(최민준)는 후속 |

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

**소유권·수명(§7, 이동찬 리뷰 B):** `active -> released/expired`. 60초 TTL, 캡처당 1 MiB, run당 active 8개(§11 한도 재사용). 크기는 [상세 규격 §7](s1-api-spec.md#7-evidence-실행-전용과-공개-저장)의 본문 bytes + 모든 헤더 이름·값 UTF-8 bytes 합계로 계산하며 Python 객체 오버헤드는 제외한다(2026-10-21 이동찬 확인). `release_captures` 반복 호출은 멱등. 원문 버퍼·캡처 핸들·HMAC 키를 하위 API·로그·결과에 넣지 않는다. 동기 capture는 바인딩·한도 검증과 소유권 인계만 하고, 민감값 제거·데이터 분석은 비동기 seal(Evidence·이경준)의 책임이다.

`bytes`/`str`는 불변이라 '즉시 해제'는 메모리 내용의 물리적 소거가 아니라 **참조·핸들 수명 관리**를 뜻한다. 다음으로 정의한다.

- Gateway는 인계 성공 이후 원문 버퍼·view 참조를 자체 보유하지 않는다.
- Evidence는 완료·실패·취소·TTL 만료·종료 시 자신이 보유한 참조·핸들을 제거하고, released/expired는 재사용할 수 없다.
- 정리 실패 시 캡처를 사용 가능 상태로 남기지 않는다(안전 실패).
- `release_captures`의 빈 `capture_refs`(run 전체 해제)는 run 종료·중단 정리에만 쓰고, 개별 캡처 해제에는 쓰지 않는다.
- 메모리 내용의 확실한 소거가 보안 요구사항이면 전용 버퍼 타입·소거 정책을 별도 설계한다. 이 계약 범위 밖의 후속이다.

적용 사례: S1-33(다른 run/객체/계정/generation/revision 결합 → `capture_binding_mismatch`), S1-31(canary·원문·인증 값 미출력), S1-04(전송 확정 후 캡처 실패 → `sent/unavailable`).

### 2.1 C3-A 캡처 계약 구현 — 병합 완료

2026-10-21, `codex/c3-capture-contracts`에서 첫 경계의 타입·포트를 구현하고 [PR #26](https://github.com/ABC2LAB/abc2lab-dast/pull/26)으로 병합했다. **C3 전체나 Evidence 구현의 완료를 뜻하지 않는다.** 이동찬의 `contracts`와 관련 문서만 변경하며 Gateway·Evidence 소스는 각 담당자가 구현한다.

- 타입: [`abc2lab_contracts.capture`](../../packages/contracts/src/abc2lab_contracts/capture.py)의 `RawHeader`, `RawResponse`, `ExecutedRequestView`, `CaptureRequest`, `CaptureResult`, `ReleaseCapturesRequest`.
- 포트: [`abc2lab_contracts.ports.LocalCapturePort`](../../packages/contracts/src/abc2lab_contracts/ports.py)의 동기 `capture`·`release_captures`. 기존 `CloseResult`·`RequestParameter`·run/ref/status/사유 타입을 재사용한다.
- 생성자는 정확한 불변 타입·tuple·양수 generation·시각을 검증한다. `actual_parameters`는 객체 GET의 비인증 path/query만 허용하며 인증·identify 등 비대상 요청에는 빈 tuple을 쓴다. 정당한 인증 POST의 원문 응답 인계는 유지한다. 어떤 이름·값이 인증 정보인지는 Gateway와 Evidence가 주입된 등록 정보로 검사한다.
- 생성자는 **캡처 맥락/등록 불일치나 1 MiB 초과를 거부하지 않는다.** 구조가 맞는 입력을 포트에 전달해야 구현이 `failed`/None·사유와 참조 정리를 수행할 수 있다. 이 실패를 예외로 바꾸거나 응답을 잘라 성공시키지 않는다. `CaptureResult`는 complete/핸들 또는 failed/사유만 허용하고 partial은 받지 않는다.
- 계약 값의 `repr`에서 원문·경로·핸들을 숨긴다. 직접 필드 접근·`dataclasses.asdict`·pickle을 막는 접근 통제는 아니며, 서비스 조립·전달·로그 경계는 각 구현과 통합 테스트가 검증한다.
- 원문용 정확한 `bytes`의 구조 검증만 추가했다. canonical codec·운영 fingerprint registry·C1/C2 고정 벡터는 변경하지 않으며 캡처 타입과 bytes는 두 fingerprint 경로에서 계속 거부한다. 실행 전용 값의 직렬화나 새 운영 fingerprint wrapper는 제공하지 않는다.

[`test_capture_contracts.py`](../../packages/contracts/tests/test_capture_contracts.py)는 결과 불변식·시각·비인증 파라미터 형태·repr·fingerprint 거부를 검사한다. [`test_no_io_capture.py`](../../packages/contracts/tests/test_no_io_capture.py)는 가짜 등록 view·시계·메모리 포트로 동기 인계, 불일치/한도 실패, 이미 알려진 sent 보존, 취소 시 해당 작업의 핸들만 정리, TTL·용량·멱등 해제를 재생한다. 이 fake는 소비자 예제이며 실제 전송 snapshot 검증·독점 소유권·메모리 소거·영속 저장 구현의 증거가 아니다.

다음 경계는 Evidence 담당 이경준과 정의할 seal/compare·민감값 제거 Evidence·저장 receipt·요청 레시피다. 해당 공개 record와 fingerprint adapter·벡터는 별도 소계약으로 추가한다. C3-A에는 이 포트나 실제 캡처 서비스, HMAC·정규화·레시피 생성·DB 저장을 넣지 않는다. 관련 검토자는 Gateway 최민준과 Evidence 이경준이다.

2026-10-21 Evidence 담당자 제안에 대한 [계약 보완안](evidence-c3-contract.md)을 추가했다. 이동찬은 EvidenceSummary.source_event를 Evidence 자체 감사 링크로 고정하는 방향을 확인했다. CaptureRequest에 Gateway source_event를 추가하지 않으며, ComparisonPayload를 기존 content로 사용하고 원본 비교 감사는 COMPARISON으로 기록한다. 공개 Evidence 타입·레시피 자료형·fingerprint는 [후속 PR #27](https://github.com/ABC2LAB/abc2lab-dast/pull/27)에 병합됐으며 [동결안](evidence-c3-freeze.md)을 따른다.

## 3. C4 — Judge `judge` 경계

C4-B의 정본은 [Judge C4-B 공유 계약](judge-c4-contract.md)이다. 이 초안은 C4-A/C4-B의 상위 흐름을 설명하며, 구현 필드·상태·정책 조회 경계가 다르면 정본을 따른다.

읽기·감사·판정 저장을 포함하므로 **async** 포트다. 내부 (a)(b)(c) 오라클·정규화 비교는 동기 순수 함수로 두고 포트에서 await한다(§2.2).

```python
class JudgePort(Protocol):
    async def judge(self, request: JudgeRequest) -> JudgeResult: ...
```

| Record | 필드 |
|---|---|
| `JudgeRequest` | `run_key: RunKey`, `context: ReadContext`, `case_ref: Ref`, `submission_ref: Ref`, `expected_policy: ExpectedAccessPolicySnapshot?`, `owner_identity: IdentityResult?`, `evaluated_identity: IdentityResult?`, `comparison_ref: Ref?` |
| `JudgeResult` | `run_key: RunKey`, `status: ResultStatus`, `verdict: Verdict?`, `projection_event: VerdictProjected?`, `reason_codes: tuple[ReasonCode, ...]`. complete는 판정과 원본 이벤트를 함께 반환하고 호출 사유는 비움. failed는 둘 다 None이며 명시적 호출·감사 실패 허용목록의 사유만 하나 이상 요구 |
| `Verdict` | `run_key, verdict_ref: Ref, revision: Revision, case_ref, value: CONFIRMED/SUSPECTED/ALLOWED/UNDECIDABLE, policy_check: CheckState, identity_check: CheckState, data_check: CheckState, expected_policy_source: SourceVersion?, comparison_ref: Ref?, evidence_refs: tuple[Ref, ...], oracle_version: SourceVersion, source_event: AuditLink, reason_codes` |
| `VerdictProjected` | `kind=verdict`, `event_ref, run_key, producer: Ref, source_revision: Revision, source_receipt: AuditReceipt, verdict: Verdict`. Judge가 원본 생산자, 전달자가 소유권을 바꾸지 않음(§8) |

**입력 경계:** Judge는 `comparison_ref`로 저장된 `StoredComparison`을 Evidence 읽기 포트로 **직접 가져와** 주체·유효기간·자원·정책 대응을 재검증하며, 호출자가 구성한 StoredComparison이나 원문·`CaptureRef`를 입력으로 받지 않는다. **기대 정책 신뢰(이동찬 리뷰 A):** `expected_policy`는 app이 주입한 `JudgePolicyReader`에 선택적 대조 값으로 전달한다. Reader는 등록 원본과 독립 대조하고 case의 정본을 조회한다. 다른 case에 속한 진짜 정책은 `UNDECIDABLE + expected_access_policy_invalid`, 위조·출처 검증·조회 장애는 `FAILED`로 구분한다. 호출자가 구성해 전달한 정책 내용을 그대로 믿지 않으며, Knowledge resolver나 다른 모듈 DB를 직접 읽지 않는다. Evidence 읽기는 기존 `ReadContext` 접근 권한 검사를 유지한다. `ComparisonRules`(정규화·canary)는 Judge가 소유·정의하고 `app`이 로컬 Evidence에 주입한다(§13-6). 주체/정책 유효성은 각 근거의 `observed_at` 당시로 판단하고, 판정 시각 TTL 경과만으로 당시 유효 근거를 버리지 않는다.

등록 Reader의 정상 부재는 정확히 `(EXPECTED_ACCESS_POLICY_MISSING,)`이며 중복·추가 사유를 허용하지 않는다. 이 정상 부재 마커를 포함한 진단 12개와 canary 성공 마커는 두 Judge 결과의 FAILED에서 금지한다. enum 전수 분류와 실패 허용목록은 [C4-B Judge 계약 §2](judge-c4-contract.md#reasoncode-분리)를 따른다.

**판정 규칙(§7, §9):** 세 `CheckState`가 모두 `yes`일 때만 `value=CONFIRMED`. `SUSPECTED`는 정책 UNKNOWN·서로 다른 검증 주체·비자명 교차 데이터·비교/근거·반사/템플릿 제외를 모두 요구한다. `ALLOWED`는 정책상 직접 또는 실제 공유/위임 허용이 검증된 경우이며 관련 없는 UNKNOWN이 직접 ALLOW를 막지 않는다. 다만 허용 여부를 무효화할 수 있는 UNKNOWN은 `UNDECIDABLE`이다. 세부 구조 조건과 등록 정책 reader는 [C4-B Judge 계약](judge-c4-contract.md)을 정본으로 한다.
- (a) `policy_check`: 신뢰된 등록 정책이 B를 명시적 금지(`expected_access=deny`)하고 `sharing/delegation=resolved_none`. 표시 문구·owner 필드·목록 차이를 정책으로 승격하지 않음. 미해소·불명은 `no`/`unknown`.
- (b) `identity_check`: A·B가 유효하고 서로 다른 검증된 subject(`owner_identity`·`evaluated_identity`의 `status=verified`). 만료·불명은 유보.
- (c) `data_check`: 같은 A 객체의 정상·비자명 실데이터가 B 교차 응답에 나타나고 반사/템플릿 제외. `nontrivial_data_match=yes` + `reflection_excluded`/`template_excluded`. HTTP 200·HMAC 일치·ID echo·owner_id·공통 템플릿만으로 `yes` 불가.

정상적인 정책 부재·실행 당시 만료·부족한 검증 신호는 `UNDECIDABLE`이며, 정책 UNKNOWN이지만 엄격한 신원·교차 데이터 조건이 모두 충족되면 `SUSPECTED`가 가능하다. 원본 변조·run/case/resource/subject 불일치·receipt 오류·검증 경계 장애는 `JudgeResult.failed`다. 판정 작업 자체가 완료된 UNDECIDABLE은 COMPLETE일 수 있다. 자료를 못 읽었다고 Gateway 재전송을 요구하지 않는다.

**SUSPECTED/ALLOWED/UNDECIDABLE 경계(C4-B 확정):**

| 정책·신원·데이터 상황 | 권장 판정 |
|---|---|
| (a)(b)(c) 모두 검증됨 | `CONFIRMED` |
| 정책 UNKNOWN이고 서로 다른 검증 주체·동일 자원·비자명 교차 노출·반사/템플릿 제외 확인 | `SUSPECTED` |
| 정상적인 정책 부재·유효성 불명이며 위 엄격한 신원/데이터 조건도 부족 | `UNDECIDABLE` |
| 유효한 직접 또는 공유/위임 허용과 평가 주체 B의 신원 검증 | `ALLOWED` |

**멱등성과 revision(이동찬 리뷰 C):** 판정 변경은 새 `revision`으로 남기고 과거를 덮어쓰지 않는다. 같은 입력의 재호출과 새 판정을 구분한다. `Verdict.source_event`와 `VerdictProjected.source_receipt`의 생성 순서는 아래 fingerprint 절에서 고정한다.

| 상황 | 처리 |
|---|---|
| 같은 `submission_ref`, 같은 정규 입력 | 기존 `Verdict`·receipt 재사용 |
| 같은 `submission_ref`, 다른 입력 | `idempotency_conflict`(failed), 기존 판정 유지 |
| 새 근거로 재판정 | 새 submission·새 `revision` 발행 |
| 감사 저장 결과 불명 | 기존 기록을 조회·확인, 무조건 재발행하지 않음 |

**fingerprint:** `Verdict`의 payload adapter·golden vector는 `record_kind=verdict`, `schema_version=verdict.v2`로 사용한다(모든 business field 포함, 자체 digest 없음 — [계약 §3](fingerprint-contract.md#3-record별-payload)). v1 Verdict vector·운영 호환 경로는 남기지 않고, 다른 record의 v1 codec/vector는 유지한다. `Verdict.source_event`는 fingerprint 이전에 고정된 `Verdict`의 business field다. `VerdictProjected.source_receipt`는 투영 시 생성되며 `Verdict`의 필드가 아니다 — 투영은 이미 fingerprint된 `Verdict`를 감싸므로 `Verdict` fingerprint는 투영 순서·receipt와 무관하게 결정적이다.

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

`SUSPECTED`·`ALLOWED`·`UNDECIDABLE`의 구조 조건은 C4-B에서 확정했다. 구체적인 정책 원본·관찰 시각·멱등성·CAS·감사 원자성은 Judge 서비스 구현 전에 후속 합의·검증한다.

**구현 PR에서 강화할 경계 테스트(기존 사례에 추가, 새 수용 사례 남발 금지):**

- C3: capture 실패 직후 Gateway·Evidence가 원문 참조를 보유하지 않음, 해제된 핸들 재사용 거부(S1-33·S1-31).
- C3: 한 작업의 `release_captures`가 같은 run의 다른 유효 캡처를 해제하지 않음.
- C3: 등록 요청과 `ExecutedRequestView`의 path/query/binding 한 필드만 달라도 거부(S1-33).
- C4: `expected_access`·sharing·delegation 중 하나만 바뀌어도 `CONFIRMED` 미발행(S1-08·S1-09).
- C4: 같은 submission의 중복·충돌·revision 증가 처리(S1-07~09).

C3-A는 #26, 후속 Evidence 계약은 #27, C4-A Knowledge는 #30, C4-B Judge 계약은 #39로 각각 병합됐다. 제공자 사유 매핑은 #41에서 해소됐다. 각 PR의 타입 테스트와 실제 서비스 실행·영속·통합 검증은 분리하며, 아직 남은 Host·Report 최소 계약과 각 제공자 검증은 [S1 상태 §8](s1-development-status.md#8-현재-서비스-구현과-남은-작업)에서 추적한다.
