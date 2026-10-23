# C4 최소 계약 초안 — Host ↔ WebDiag 경계 (webdiag 소유)

상태: **최소 계약 초안 / 공유 계약 [PR #38](https://github.com/ABC2LAB/abc2lab-dast/pull/38) 병합 완료 (2026-10-22)**. 작성 이경준(webdiag·host·evidence). 이 문서는 **Host↔WebDiag 최소 타입·Protocol**의 설계 기록이며, 구현된 공유 타입은 `abc2lab_contracts.webdiag`와 `WebDiagPort`에 있다. 세션 바인딩·상태 전이·context 생명주기는 후속 [PR #40](https://github.com/ABC2LAB/abc2lab-dast/pull/40)으로 반영됐지만 발견·인증/whoami·관찰·교차 비교 전체 서비스는 후속이다. 공개 필드·상태는 [S1 API 상세 규격](s1-api-spec.md)과 병합된 공유 계약을 따른다.

## 1. 범위와 선행 의존

이 초안은 **Host가 WebDiag를 호출하는 경계**(`WebDiagPort`)를 다룬다. 공유 타입과 포트는 PR #38에서 구현됐다. WebDiag가 소비하는 Gateway/Policy/Session/Evidence 포트는 이미 `abc2lab_contracts.ports`에 있으며, Knowledge 투영 제출은 Host가 기존 `KnowledgePort.project`를 호출해 조정한다. Host 진입점(`start_run/get_status/stop`)은 별도의 [Host 공개 계약 v0.1](host-public-contract-v0.1.md)에서 요청·결과·Protocol을 구현 제안하며, 아직 팀 승인·병합·Host 서비스 구현을 의미하지 않는다. Report 입력/결과·`build_report`는 Report 담당자와 별도 공유 계약 PR로 확정해야 한다.

| 구분 | 타입 | 상태 |
|---|---|---|
| 재사용 (contracts 기존) | `RunKey`·`Ref`·`ResultStatus`·`ReasonCode`·`AttemptSummary`·`AuditLink` (primitives), `SessionHandle`·`SessionResult`·`SessionState`·`IdentityResult` (session), `Observation` (observation), `Candidate`·`CandidateHint` (knowledge), `ObservationProjected` (projection), `ComparisonProjected`·`StoredComparison` (evidence), `ExpectedAccessPolicySnapshot`·`CrossExecutionConfirmation` (registration) | 머지됨 |
| **신규 (이 초안에서 제안, 현재 구현됨)** | `SessionRequest`·`IdentityRequest`·`DiscoveryRequest`·`ObserveRequest`·`AccessCompareRequest`·`DiscoveryResult`·`ObserveResult`·`AccessCompareResult`·`WebDiagProjectionEvent`·`WebDiagPort` | **PR #38 병합**, `abc2lab_contracts.webdiag` |

**선행:** C2 공통 타입과 위 재사용 타입이 선행이다(모두 머지됨). 신규 record는 그 타입을 재사용하며 **임의 dict·`Any`·사본을 만들지 않는다**. S1은 **HTTP 단일 경로**이므로 `web_observe`(브라우저)는 이 초안에서 제외한다.

## 2. `WebDiagPort` 경계

Host가 사례별로 호출한다. 읽기·관찰·비교·인증 대기를 포함하므로 **전부 async**다. Host 내부의 plan/submit/lease/complete/cancel과 Broker는 host 패키지 내부이며 이 Protocol이나 contracts에 넣지 않는다.

```python
class WebDiagPort(Protocol):
    async def collect(self, request: DiscoveryRequest) -> DiscoveryResult: ...
    async def http_observe(self, request: ObserveRequest) -> ObserveResult: ...
    async def access_compare(self, request: AccessCompareRequest) -> AccessCompareResult: ...
    async def acquire_session(self, request: SessionRequest) -> SessionResult: ...
    async def whoami(self, request: IdentityRequest) -> IdentityResult: ...
```

### 2.1 입력 record

| Record | 필드 |
|---|---|
| `SessionRequest` | `run_key: RunKey`, `account_ref: Ref`, `auth_profile_ref: Ref` |
| `IdentityRequest` | `run_key: RunKey`, `session: SessionHandle`, `identity_profile_ref: Ref` |
| `DiscoveryRequest` | `run_key: RunKey`, `seed_operation_refs: tuple[Ref, ...]`, `account_ref: Ref`, `max_candidates: int` |
| `ObserveRequest` | `run_key: RunKey`, `candidate: Candidate`, `account_ref: Ref`, `observation_profile_ref: Ref` |
| `AccessCompareRequest` | `run_key: RunKey`, `case_ref: Ref`, `candidate: Candidate`, `owner_account_ref: Ref`, `evaluated_account_ref: Ref`, `expected_policy: ExpectedAccessPolicySnapshot \| None`, `cross_confirmation: CrossExecutionConfirmation \| None` |

- `request_ref`는 입력에 **없다**. WebDiag가 인증·whoami·복구·기준·교차 각 논리 동작마다 최초 prepare 전 1회 발급·보존하고, Host는 결과의 `attempt_summaries`에서 연결한다(§3). Host가 입력하거나 Gateway가 바꾸지 않는다.
- `candidate`는 Host가 Knowledge `get_case_view`로 읽어 revision까지 검증한 **불변 값**을 그대로 전달한다. WebDiag는 Knowledge 포트를 주입받지 않으며, 전달된 `candidate`와 주입된 동작/자원 등록의 일치를 검사한다. `candidate`는 실행 권한·요청 resolver가 아니며 Gateway/Policy 독립 재검증을 대신하지 않는다.
- `expected_policy`/`cross_confirmation`은 Host가 주입된 `RunRegistration`에서 **선택·전달만** 하고, Gateway/Policy가 주입 원본에 재대조한다. 교차 아닌 호출에는 둘 다 `None`.

### 2.2 출력 record

| Record | 필드 |
|---|---|
| `DiscoveryResult` | `run_key: RunKey`, `status: ResultStatus`, `hints: tuple[CandidateHint, ...]`, `attempt_summaries: tuple[AttemptSummary, ...]`, `reason_codes: tuple[ReasonCode, ...]` |
| `ObserveResult` | `run_key: RunKey`, `status: ResultStatus`, `observation: Observation \| None`, `projection_events: tuple[ObservationProjected, ...]`, `attempt_summaries: tuple[AttemptSummary, ...]`, `reason_codes: tuple[ReasonCode, ...]` |
| `AccessCompareResult` | `run_key: RunKey`, `case_ref: Ref`, `status: ResultStatus`, `owner_identity: IdentityResult \| None`, `evaluated_identity: IdentityResult \| None`, `owner_observation: Observation \| None`, `stored_comparison: StoredComparison \| None`, `stored_evidence_refs: tuple[Ref, ...]`, `projection_events: tuple[WebDiagProjectionEvent, ...]`, `attempt_summaries: tuple[AttemptSummary, ...]`, `reason_codes: tuple[ReasonCode, ...]` |

`SessionResult`·`IdentityResult`는 기존 contracts를 그대로 반환한다(신규 아님).

`WebDiagProjectionEvent`는 폐쇄 union이다:

```python
type WebDiagProjectionEvent = ObservationProjected | ComparisonProjected
```

## 3. 경계 규칙·불변식

**완성도 의미 (`_validate_invariants`로 강제 제안):**
- `DiscoveryResult`: `complete`는 Knowledge 등록 전의 민감값 제거 단서(`hints`)를 반환했다는 뜻이며 ID/revision을 발급하지 않는다(발급은 Host가 Knowledge에 등록). 발견만으로 관찰·검사 완료가 아니다.
- `ObserveResult`: `complete` ⇔ `observation`이 존재하고 그 `ObservationProjected`가 `projection_events`에 있다. `partial`은 저장된 일부를 보존, `failed`도 발생한 `attempt`를 보존.
- `AccessCompareResult`: `complete` ⇔ `stored_comparison`이 존재하고 대응 `ComparisonProjected`가 `projection_events`에 있다. `partial`은 한쪽 근거만 보존(확정 비교 아님), `failed`도 attempt 보존.
- 세 결과 모두 실패·부분에서도 `attempt_summaries`를 보존한다(인증·whoami·기준·교차의 모든 시도). 아직 요청 없는 실패에 가짜 attempt를 만들지 않는다.
- `SessionResult`는 partial이 없고 complete는 confirmed 세션을 요구한다(기존 contracts 불변식). `IdentityResult` verified는 저장 근거+감사 영수증을 요구한다(기존).

**소유권·전달(§8):** `projection_events`의 원본 producer는 WebDiag(`ObservationProjected`)와 Evidence(`ComparisonProjected`)다. WebDiag는 evidence `compare_and_seal`이 준 `ComparisonProjected`를 **변경 없이** 전달하고 새로 만들지 않는다. Host가 이를 `project`로 제출한다. 원본 commit 확인이 없으면 이벤트를 넣지 않고 partial로 남긴다.

**신호≠판정:** `StoredComparison`의 `ComparisonSignals`는 주입 규칙 산출물이며 HMAC 일치만으로 확정이 아니다. WebDiag/Host는 신호를 판정으로 해석하지 않는다(판정은 Judge).

**비노출·캡처 정리:** 결과·로그에 원문·`capture_ref`·run HMAC 키를 넣지 않는다. `seal`/`compare_and_seal`에 넘긴 캡처는 evidence가 finally에서 스스로 release하므로, WebDiag는 받아놓고 seal/compare까지 못 간 캡처만 `LocalCapturePort.release_captures`로 정리한다.

**교차 전송 관문(D-0):** `access_compare`의 실제 교차 전송은 [§13-2 D-0](module-design-confirmed.md#13-열린-결정-착수-전중-팀이-잠글-것) 통과 전까지 무전송 대역으로만 개발·시험한다. `http_observe`는 자기 자원만 관찰하며 교차 요청 창구로 변질될 수 없다(등록 미해소 객체는 실행하지 않음).

**멱등·제출:** `submission_ref`(evidence 저장/비교 제출의 멱등 키)는 WebDiag가 논리 제출마다 1회 발급·재사용한다. 전송 불명·재시도 시 새 캡처로 재-seal하지 말고 evidence `recover_submission`(캡처·대상 재전송 0)을 쓴다.

## 4. fingerprint

이 신규 record들은 **감사 fingerprint 대상이 아니다**(요청/결과 전달 record). 내부에 담기는 `Observation`·`StoredComparison`·투영 이벤트는 이미 자기 payload adapter·벡터를 갖는다. 따라서 이 초안은 [공유 codec](fingerprint-contract.md)에 **새 payload adapter를 추가하지 않는다.** `WebDiagProjectionEvent` union 추가만 있으면 된다.

## 5. 원래 열린 질문의 해소·남은 검증

**검토 경계:** 이동찬(contracts), 최민준(gateway/judge·교차 확인), 이경준(Host/WebDiag 제공자·소비자).

1. **타입 배치 — 해결:** PR #38에서 요청·결과와 `WebDiagProjectionEvent`, `WebDiagPort`를 모두 `abc2lab_contracts.webdiag`에 구현했다. 서비스 내부 구체 구현과는 분리한다.
2. **`max_candidates` — 계약 일부 구현, 서비스 검증 후속:** `DiscoveryRequest` 생성자는 양의 정수 여부를 검사한다. `RunLimits.max_candidates` 및 계정·run별 실행 예산의 실제 상한 교차 검증과 유한 수집은 WebDiag/Host 제공자 통합 테스트에서 확인한다. 현재 공유 생성자의 검사만으로 예산 적용 완료를 주장하지 않는다.
3. **반환 상태 구조 검사 — 해결/후속 분리:** PR #38에서 `DiscoveryResult`, `ObserveResult`, `AccessCompareResult` 생성자의 COMPLETE/FAILED 관련 구조 조건을 일부 강제한다. producer 원본 감사 확인·실제 요청 바인딩·부분 근거·주체 확인과 같은 실행 의미는 제공자 통합 검증이 남아 있다.

**적용 case:** S1-01(정상 관찰) · S1-05(주체 불명/만료 유보) · S1-06(한쪽 저장 → partial) · S1-10(B 자기 객체 없음) · S1-39(WebDiag의 Knowledge 의존 0, candidate 값 전달) · S1-40(동작별 request_ref 1회 발급).

**구현 경계:** 타입·포트는 #38로 병합 완료. 세션 바인딩·상태 전이·context 생명주기 일부는 #40으로 병합 완료. `collect`·`acquire_session`·`whoami`·`http_observe`·`access_compare`의 전체 제공자 흐름과 실제 실행/감사 통합은 후속이며, 이 문서의 제안 시점 문장을 기능 완료 증거로 삼지 않는다.
