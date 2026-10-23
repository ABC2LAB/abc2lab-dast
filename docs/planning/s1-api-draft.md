# S1 API 설계 개요 v0.5 — 상대 구현 없이 개발·테스트하기

상태: **S1 흐름·책임·로컬 fake 개발 설명의 설계 개요 (v0.5 문서) / 구현 현황은 별도 추적**. 이 문서는 당시 D1~D7 협의와 개발 사례의 기록이다. 최신 필드·상태·포트 집계는 [S1 API 상세 규격 v0.8](s1-api-spec.md), 실제 계약 병합·서비스 구현·미완료 항목은 [S1 상태 §8](s1-development-status.md#8-현재-서비스-구현과-남은-작업)를 우선한다. Host 진입점의 시그니처는 [공개 계약 v0.1 제안](host-public-contract-v0.1.md)으로 맞췄으며, 팀 승인·Host 서비스 구현을 뜻하지 않는다. 문서의 설계 흐름은 실제 대상 통신 또는 S1 E2E 검증 완료를 뜻하지 않는다.

목표: **상대 모듈의 완성을 기다리지 않고도 내 모듈을 개발·테스트할 수 있게 한다.** 제공자와 소비자는 아래의 작은 경계와 사례를 함께 검토한다. 모듈 내부 모델·저장 구조·클래스 구성은 각 담당자가 소유한다.

## 1. 요구사항과 S1 범위

- 등록된 두 계정으로 테스트 앱의 읽기 수평 IDOR 한 경로를 발견 → 관찰 → 비교 → 판정 → 보고한다. B의 자기 객체는 필수 입력이 아니다.
- 첫 병렬 개발은 네트워크·브라우저·DB 없는 로컬 fake로 수행한다. 실제 통신·내구성 검증은 후속 통합이다.
- S1 API는 Python 직접 호출용 포트다. REST endpoint·MCP wire schema·전체 도메인 공용 모델은 이번 초안의 범위에 넣지 않는다.
- S2의 위임 다중 홉 조회, AGE, MCP, LLM, ZAP/Nuclei, UI는 후속 범위다.
- 기존 [아키텍처 §4·§8](mcp-architecture.md), [모듈 설계 §5–10](module-design-confirmed.md#5-패키지별-책임공개-포트)의 통신·근거·정책·판정 경계를 유지한다. 충돌하면 아키텍처를 우선하며 이 초안을 수정한다.

## 2. 먼저 합의할 범위

| 합의 대상 | 이번 초안의 제안 | 모듈별 구현에 맡기는 부분 |
|---|---|---|
| 호출 | I/O 서비스 포트 async, 순수 계산·메모리 인계 sync. Host 유한 큐·S1 worker 1개, await 순서·취소·유한 동시성은 [상세 규격 §2.2](s1-api-spec.md#22-비동기-호출과-작업-실행) | 내부 클래스·저장 어댑터·계산 최적화. 공유 포트의 await 여부는 제공자/소비자가 일치시킴 |
| 데이터 | 각 경계를 통과하는 최소 값과 식별자의 의미 | DB row·브라우저 상태·ORM/Pydantic 모델·내부 캐시 |
| 공유 코드 | 최소 타입·Protocol과 [fingerprint 계약의 순수 codec](fingerprint-contract.md)을 경계별 작은 PR로 제공 | 모든 타입의 선행 공용화·거대한 RunContext·범용 utils 작성 |
| 대역 | 소비 모듈의 `tests/fakes/`에 로컬 fake. 같은 사례를 제공자도 검증 | 다른 서비스 구현 import·다른 담당자 DB·실제 서버 기동 |
| 조립 | `app`에서 구현/fake·신뢰된 설정·저장 어댑터를 주입 | 서비스가 상대 구체 구현을 직접 생성하는 코드 |

현재 [기여 규칙](../../CONTRIBUTING.md#모듈-경계와-데이터-계약)은 합의된 공유 타입·포트를 `contracts`에 두도록 한다. 이 초안은 그 규칙을 바꾸지 않는다. 계약의 내용은 제공자와 소비자가 제안하고, 구현은 합의된 경계부터 진행한다. `contracts` 전체 완성을 기다리지 않는다. 경계별 공유 타입이 아직 없으면 내부 순수 로직부터 개발하고 공개 포트 완성으로 표시하지 않는다. 임의 `Any`·dict placeholder나 서로 다른 공용 타입 사본을 만들지 않는다.

## 3. 데이터 소유와 노출 범위

| 데이터 | 정본/생성 책임 | 전달 범위 |
|---|---|---|
| 작업 상태·대여·중지 | Host | 공개 작업 요약 |
| 발견 후보·관찰 투영·graph revision | Knowledge | 민감값 제거 조회 결과 |
| 세션 생명주기·주체 확인 | WebDiag. 인증 비밀·전송 결합은 Gateway/Vault | 비밀 없는 세션·주체 확인 요약만 공개 |
| 준비된 실제 요청 | Gateway | 실행 영역 내부의 `PreparedRequestHandle`만 |
| 요청 전송 허용 결정 | Policy | 해당 요청 바인딩에 대한 결정·사유 |
| 등록 기대 접근 정책 | 관리자의 신뢰된 등록 입력을 `app`이 검증해 불변 snapshot으로 주입 | WebDiag의 적용 범위 확인과 Judge의 기대 권한 판단. Knowledge에는 출처 참조를 투영 |
| 원문 응답·캡처 핸들·run HMAC 키 | Gateway와 실행 영역 로컬 Evidence | 실행 영역 밖·영속 저장·로그로 전달하지 않음 |
| 민감값 제거 근거·비교 결과 | 공개 Evidence 서비스 | 저장 완료된 요약·참조만 공개 |
| 판정·오라클/정규화 규칙 | Judge | 판정·규칙의 선언적 버전/내용. `app`이 규칙을 로컬 Evidence에 주입 |
| 감사 원본 | 작업=Host, 정책=Policy, 전송=Gateway, 근거=Evidence, 판정=Judge | 각 생산자가 자기 저장 어댑터에 기록하고 허용된 감사 페이지를 제공 |

`SafetyPolicy`는 요청을 실행해도 되는지 판단한다. `ExpectedAccessPolicy`는 해당 계정이 자원에 접근할 권한이 있는지 판정하는 근거다. 실행 허용을 정상 접근·취약점 확정으로 해석하지 않는다.

## 4. 식별자와 결과의 공통 의미

아래 이름은 문서용 타입 이름이다. 실제 Python 정의·모듈 경로는 경계별 계약 PR에서 확정한다.

- `RunKey`: `organization_ref`, `target_ref`, `environment_ref`, `run_ref` 네 식별자. 다른 실행·대상·조직의 자료와 혼용하지 않는다. 설정·예산·세션 전체를 넣지 않는다.
- `request_ref`: WebDiag가 인증·whoami·복구·기준·교차 동작마다 최초 prepare 전에 발급·보존하는 논리 요청 ID. Host는 run/task/case를, Gateway는 binding_id/attempt_ref를 발급한다. Host는 request_ref를 입력하지 않고 결과·감사에서 연결한다. unknown을 새 ID로 자동 재전송하지 않는다.
- 설정·정책·규칙 snapshot은 출처·revision·유효 범위를 포함한다. 같은 식별자/revision의 내용을 변경하지 않는다. 계정/세션은 별칭·generation으로 연결한다.
- `complete`는 해당 작업 결과가 완성됐다는 뜻이다. 부분 결과는 `partial`, 수행/확인 불가는 `failed`와 사유로 보존한다. 취소·만료·자료 부재·자료 권한 거부는 사유로 구분하고 성공한 빈 결과로 바꾸지 않는다.
- 전송 상태의 정본 표기는 `sent`, `not_sent`, `unknown`이다. 전송 후 응답·캡처 실패는 `sent`를 유지한다. `unknown`은 자동 재전송하지 않는다.
- 오류 설명 대신 `reason_codes`와 관련 참조를 전달한다. 원문 예외·traceback·쿼리·쿠키·토큰을 공유하지 않는다. 프로그래밍 오류를 정상 결과로 삼키지 않는다.
- 결과에 존재하지 않는 참조는 `None`이다. 가짜 참조·빈 문자열을 채우지 않는다. 완료되지 않은 저장의 참조를 사용 가능한 근거로 발행하지 않는다.
- 시간은 명시적인 timezone-aware UTC 감사 시각과 producer 순번을 사용한다. timeout·경과 시간에는 monotonic clock을 쓴다. 벽시계만으로 생산자 간 인과 순서를 정하지 않는다.

감사 페이지에서도 정책 사건의 policy_outcome=allow/block과 Gateway 전송 사건의 send_status=sent/not_sent/unknown을 구분한다. [모듈 설계 §8](module-design-confirmed.md#8-근거감사-체인)도 같은 표기를 사용한다. 정책 차단만 보고 실제 미전송을 추정하지 않으며 Gateway의 해당 시도 기록이 확인돼야 not_sent를 연결한다.

## 5. API 경계 목록

시그니처의 모든 입력·결과는 아래 절에서 의미를 정의한 타입이다. 표는 구현 코드가 아니다. async def 포트는 await해 결과를 얻으며, capture/read_session_binding/release_captures는 메모리 전용 def 포트다. 실행 생성 후에는 `RunKey`를 각 요청에 포함하며 생략된 global state에서 얻지 않는다. `start_run`은 Host의 검증·수락·큐 수용 뒤 queued run을 반환하고 전체 진단은 worker가 실행한다.

### 5.1 Host → WebDiag / 사용자 → Host

| API 제안 | 최소 입력 | 결과·실패 의미 | 제공자 / 소비자 |
|---|---|---|---|
| `async def start_run(request: StartRunRequest) -> StartRunResult` | 대상/환경·등록 설정 참조·submission_ref·필수 ReadContext. 범위·계정·프로필·예산·기대 정책은 app이 주입 | complete 수락/partial 수락 미확정/failed 거절. 같은 키로 수락 여부 재확인, 중복 생성/배정 없음 | Host / 진입점 |
| `async def get_status(request: GetRunStatusRequest) -> GetRunStatusResult` | 실행 키·필수 ReadContext | 업무 `revision`과 별도 `snapshot_revision`을 가진 일관 상태 snapshot 또는 partial/failed. partial은 `GetRunStatusResult.missing_task_refs`로 정확한 누락 Task를 명시하고 전송 집계는 전체 Run 기준을 유지. 감사 UNKNOWN만으로 partial이 되지 않으며 호출마다 현재 권한을 재검증 | Host / 진입점 |
| `async def stop(request: StopRunRequest) -> StopReceipt` | 실행 키·필수 ReadContext | 접수/실제 정리 종료/적용 대상 아님/불명을 구분하고 requested_at 존재 조건을 따른다. 진행 중 전송의 불명을 지우지 않음 | Host / 진입점 |
| `async def collect(request: DiscoveryRequest) -> DiscoveryResult` | 실행 키·허가된 seed·계정·유한 탐색 상한 | CandidateHint 단서·출처·관찰 필요 조건·모든 전송 시도·complete/partial/failed. 후보 ID/revision은 Host가 Knowledge 등록 후 받음 | WebDiag / Host |
| `async def http_observe(request: ObserveRequest) -> ObserveResult` | 실행 키·Host가 조회한 자기 자원 Candidate 값·계정·관찰 프로필 | 아래 Observation·원본 projection_events 또는 차단·실패·부분 결과. 교차 자원 관찰로 전환하지 않음 | WebDiag / Host |
| `async def access_compare(request: AccessCompareRequest) -> AccessCompareResult` | 실행 키·case_ref·Candidate 값·소유자/평가 계정·선택한 등록 기대 정책/교차 확인 | 저장 완료 비교·원본 projection_events·근거 참조와 미충족 조건. 실제 교차 요청은 이 기능 내부에서만 조정 | WebDiag / Host |

S1은 HTTP 단일 경로이며 web_observe는 후속 브라우저 어댑터다. collect는 민감값을 제거한 단서만 반환하고 **Host가 Knowledge 후보 등록·조회·revision 검증을 수행**한다. Host는 ObserveRequest/AccessCompareRequest에 Candidate 전체를 값으로 전달한다. WebDiag에는 Knowledge 포트를 주입하지 않는다. 후보 발견만으로 관찰·검사 완료로 표시하지 않는다.

Host의 plan·submit/lease/complete/cancel은 host 내부 Protocol이며 S1 contracts에 포함하지 않는다. tools_for/call Broker·MCP/LLM 라우팅은 S1에서 구현·호출하지 않는다. 유한 ready 큐·worker 1개를 사용하고 get_status/stop은 검사 worker를 기다리지 않는 제어 경로로 둔다. 첫 Planner는 A의 기준 관찰과 access_compare 작업을 구성하며 B 자기 객체·4응답 고정 세트를 요구하지 않는다. 공개 포트 수는 [상세 규격 §3.1](s1-api-spec.md#31-s1-포트-수-대조)의 26 async+3 sync다.

### 5.2 WebDiag 인증 경계

| API 제안 | 최소 입력 | 결과·실패 의미 |
|---|---|---|
| `async def acquire_session(request: SessionRequest) -> SessionResult` | 실행 키·계정 별칭·서버 등록 인증 프로필 | `SessionHandle` 또는 명시적 인증 실패. 비밀번호·쿠키를 입력/결과의 공개 값으로 쓰지 않음 |
| `async def whoami(request: IdentityRequest) -> IdentityResult` | 실행 키·세션 핸들·등록된 주체 확인 프로필 | 검증된 subject 별칭·계정·generation·근거 참조·유효 시각, 또는 `unknown/expired/mismatch` |

`SessionHandle`은 WebDiag가 소유하는 불투명 식별자이며 실행 키·계정·generation·유한 유효기간에 결합한다. Credential Vault의 전송 비밀은 Gateway만 해석한다. HTTP 200·쿠키 발행만으로 `IdentityResult`를 verified로 만들지 않는다. generation이 바뀌거나 만료·취소되면 이전 확인을 재사용하지 않는다.

로그인·whoami 요청도 Policy/Gateway를 통과한다. WebDiag가 상태·generation·주체 확인을 소유하고 Gateway가 계정별 전송 context·비밀을 소유한다. lease·정상 복구 1회·종료·유한 TTL의 초기 선택은 [상세 규격 §4](s1-api-spec.md#4-인증세션-통제)에 명시한다. 첫 fake는 만료·generation 변경·종료를 주입한다.

### 5.3 WebDiag → Gateway → Policy: 실행 영역 전용

| API 제안 | 입력 | 결과·책임 |
|---|---|---|
| `async def prepare(request: ExecutionRequest) -> PrepareResult` | 실행 키·요청 ID·구체 목적지/method·등록 동작·전송 입력·세션 바인딩·목적·실행 프로필·교차 실행 확인 기록(교차 시 필수) | Gateway가 실제 요청을 고정하고 `PreparedRequestHandle`과 비밀 없는 `PolicyInput`을 생성. 준비 실패는 전송 0건 |
| `async def evaluate(request: PolicyInput) -> PolicyDecisionResult` | 아래 정책 view와 신뢰된 안전 설정 snapshot | 저장된 PolicyDecision 또는 실패. 정상 결정은 `allow/block`, 불명·만료·누락은 block |
| `async def execute(request: ExecuteRequest) -> AttemptResult` | 실행 키·준비 핸들·정책 결정 | Gateway가 바인딩/현재 조건 재검사 후 시도·전송 상태·캡처 상태·사유를 반환 |

**이전 초안의 숨은 등록소 문제를 피하는 제안:**

1. WebDiag가 구체 실행 요청을 만든다. 원문 목적지·전송 입력은 실행 영역 내부 값이다.
2. Gateway가 요청을 준비·소유하고, 자기 Gateway 인스턴스가 유한 TTL 안에서만 해석하는 준비 핸들을 발급한다. 소유 인스턴스·실행·계정/세대가 다르거나 만료·소비된 핸들은 거부한다. 핸들은 공개 Host/MCP 결과로 내보내지 않는다.
3. Gateway가 **값으로 제공하는** 불변 `PolicyInput`에는 실행 키, binding ID, canonical origin, method, 등록 operation/목적, 계정·검증 subject 상태·세션 generation, 안전 범위/프로필/유한 예산 설정의 snapshot과 revision, 교차 실행 확인 snapshot(교차 시 필수)을 포함한다. 실제 정책 확인에 필요한 경로/입력 제약은 검증된 정책용 속성으로 제공한다. 제거·누락 때문에 판단할 수 없으면 block한다. 남은 예산은 Gateway가 전송 직전에 현재 값으로 원자 차감한다.
4. `app`은 관리자 등록 설정을 검증한 뒤 Policy와 Gateway에 주입한다. Policy는 Gateway 저장소나 Vault를 조회하지 않는다. 각 모듈의 설정 읽기·취소 확인용 내부 포트는 해당 담당자가 소유하고 로컬 fake로 시험한다. snapshot의 issuer·출처·revision·유효성/취소를 확인하지 않은 입력을 신뢰하지 않는다.
5. Policy는 받은 binding ID에만 결정을 연결한다. Gateway는 실제 준비 요청·view가 변경되지 않았는지 확인하고 결정의 출처·유효성도 검사한다. binding ID 문자열 일치만으로 권한이나 요청 무결성을 증명했다고 보지 않는다. 위조 view·다른 준비 요청에 대한 allow를 거부한다.
6. Gateway는 실제 연결 목적지·Host/SNI·origin·인증·profile·예산을 다시 확인한다. 파생 요청·redirect·재시도·브라우저 하위 요청도 요청별로 통제한다.

`prepare`와 binding 표현은 **신규 API 설계안**이다. 이번 기준은 전체 입력을 불변 snapshot으로 고정하고 15초·단일 execute로 소비한다. [상세 규격 §5](s1-api-spec.md#5-gateway와-policy의-실행-경계)에 canonicalization과 재검사를 명시한다. `RequestSpecRef`만 던지고 서로 미정 저장 구조를 맞추는 방식은 사용하지 않는다.

**Policy/Gateway fake의 최소 필드 제안:**

| `PolicyInput` 필드 | 필수 의미 |
|---|---|
| `run_key`, `request_ref`, `binding_id` | 실행·논리 요청·Gateway가 소유한 불변 준비 snapshot 식별 |
| `origin`, `method`, `operation_ref`, `purpose` | canonical scheme/host/port, 대문자 method, 등록 동작, `observe/authenticate/identify/access_compare` |
| `policy_attributes` | 적용 경로/입력 제약에 필요한 비밀 없는 구조화된 값과 검증 출처. 별도 타입으로 정의하고 임의 dict로 대체하지 않음 |
| `account_ref`, `session_generation`, `subject_ref`, `identity_status` | 익명 관찰에는 `None` 허용. 교차 요청은 유효한 계정·실제 subject 확인 필요 |
| `scope`, `profile`, `budget` | app에서 검증·주입한 적용 설정의 값·출처·revision·유효 범위. Policy의 자체 규칙과 대조 |
| `operation_revision`, `policy_attributes.resource_binding_ref/revision` | 등록 동작·구체 객체의 불변 바인딩을 식별. Gateway는 실제 파라미터 값도 대조 |
| `owner_identity`, `expected_policy` | 교차 시 소유자 주체 확인과 등록 기대 정책 snapshot. Gateway가 신뢰된 현재 상태/등록 입력에 대조 |
| `cross_confirmation` | 교차 시 필수인 유효한 확인 snapshot. 다른 목적에는 None. Host는 등록 원본에서 선택·전달만 하며 Gateway/Policy가 전체 내용을 재검증 |

Gateway는 준비 요청과 위 view를 같은 불변 `BoundRequestSnapshot`으로 소유한다. `PolicyDecision`의 최소 값은 `decision_ref`, `binding_id`, **`evaluated_view_fingerprint`**, `outcome`, `reason_codes`, `audit_receipt`다. Policy는 실제 평가한 view의 모든 필수 필드로 fingerprint를 계산하며, 입력에 적힌 fingerprint를 그대로 신뢰해 복사하지 않는다. Gateway는 저장한 view로 계산한 값과 결정의 값을 대조하고 실제 준비 요청도 snapshot과 일치하는지 검사한다. fake에서도 view 한 필드만 바꾼 경우를 거부해야 한다.

fingerprint는 [공유 codec 계약](fingerprint-contract.md)의 중첩 변환·버전/kind envelope·고정 벡터를 따른다. contracts의 단일 순수 구현을 재사용하며 PolicyInput.schema_version=policy_input.v1은 문서 판번호와 별개다. 인증·권한 부여를 대신하지 않으며 Policy의 실제 저장 기록과 바인딩도 확인한다. 준비 핸들 거부는 prepared_handle_invalid/prepared_handle_expired/prepared_handle_foreign_scope/prepared_handle_consumed를 구분하고 모두 not_sent다. 가상 transport 호출 기록은 0건이어야 한다.

`AttemptResult` 최소 값: 실행 키·`request_ref`·`attempt_ref`·`decision_ref`·`binding_id`·`send_status`·캡처 상태·실행 전용 `capture_ref | None`·사유·감사 연결. 전송 거부는 `not_sent`, 미확정 전송은 `unknown`으로 보존한다. 전송 후 캡처 실패는 `sent/unavailable`이다. `capture_ref`가 있어도 공개 Evidence 저장 완료는 별개다.

캡처 가용 상태의 정본 필드명은 `capture_status`이며 다음 조합만 허용한다.

| `send_status` | `capture_status` | 실행 전용 `capture_ref` | 의미 |
|---|---|---|---|
| `sent` | `captured` | 있음 | 캡처 버퍼 존재. 공개 근거 봉인/저장 완료는 별도 |
| `sent` | `unavailable` | `None` | 전송은 확실하지만 응답/캡처가 없음 |
| `not_sent` | `not_applicable` | `None` | 확실한 미전송 |
| `unknown` | `indeterminate` | `None` | 전송 여부 불명 |

이 상태는 봉인·저장 작업의 `complete/partial/failed`와 구분한다. WebDiag는 모든 결과(실패·부분 포함)에 `attempt_summaries`를 전달한다. 각 공개 `AttemptSummary`는 실행 키·`request_ref`·`attempt_ref`·원래 `send_status`·사유·감사 참조만 담으며 캡처/준비 핸들은 제외한다. Host는 이를 작업 결과에 보존하고 Report는 3상태별로 집계한다. 기록이 빠진 범위는 감사 미확인으로 남기고 임의로 `not_sent`를 생성하지 않는다.

실제 전송 전에 정책 결정은 Policy의 저장 어댑터에, 요청 intent는 Gateway의 저장 어댑터에 내구 기록한다. [상세 규격 §10](s1-api-spec.md#10-감사-커밋과-조회)의 `verify_committed`로 실제 producer 기록과 receipt/binding의 일치를 확인한다. 두 기록의 완료를 확인하지 못하면 Gateway가 전송을 차단한다. 공유 DB schema를 직접 읽지 않는다. 메모리 fake는 이 완료/실패를 흉내 낼 뿐 실제 내구성을 증명하지 않는다.

### 5.4 Gateway/WebDiag → 실행 로컬 Evidence → 공개 Evidence

| API 제안 | 최소 입력 | 결과·실패 의미 |
|---|---|---|
| `def capture(request: CaptureRequest) -> CaptureResult` | 실행 영역 응답 버퍼와 실행·요청·계정/generation·관찰 시각 | 실행 전용 캡처 핸들 또는 캡처 실패. 전송 상태는 변경하지 않음 |
| `async def seal(request: SealRequest) -> SealResult` | 유효한 캡처 핸들·민감값 제거 규칙 | 공개 Evidence 저장 완료 receipt·참조 또는 미완료/실패 |
| `async def compare_and_seal(request: CompareRequest) -> CompareOutcome` | 기준/교차 캡처 핸들·의도한 두 계정/동일 객체 맥락·정규화/오라클 규칙 버전 | 두 근거와 비교 결과의 저장 완료를 확인한 `StoredComparison`, 또는 부분/실패 |
| `async def store_evidence(request: RedactedBundle) -> StoreOutcome` | 민감값 제거 자료·출처·실행/자료 권한·submission_ref 멱등 키 | 저장 완료 receipt 또는 부분/실패. 같은 키/내용 재호출은 멱등, 같은 키/다른 내용은 충돌 |
| `async def evidence_read_summary(request: EvidenceReadRequest) -> EvidenceReadResult` | 근거 참조·실행 키·호출자/자료 권한 | 허용 요약 또는 not_found/access_denied/미완료/실패 |

상위 3개는 실행 영역 전용, 하위 2개는 공개 Evidence 서비스 경계다. `capture`는 **Gateway가 실행 영역의 로컬 Evidence에 호출하는 private 포트**다. 원문 버퍼의 소유권/정리 책임을 로컬 Evidence로 넘기며 다른 공개 호출자나 Host가 중계하지 않는다. 이 private 포트의 단위 fake는 실행 영역 테스트 안에서만 가상 버퍼를 받는다. 공개 Evidence fake는 민감값 제거 자료만 받는다.

캡처 핸들은 `active -> released/expired`다. 60초 TTL·단일 1 MiB·run당 active 8개를 초기 상한으로 두고 완료·실패·중지 시 버퍼와 핸들을 해제한다. released/expired는 다시 읽거나 비교할 수 없다. 공개 저장이 partial이면 완료된 불변 근거는 보존하지만 원문을 공개 저장소에서 복구하거나 대상에 자동 재요청하지 않는다. [상세 규격 §7](s1-api-spec.md#7-evidence-실행-전용과-공개-저장)에 정리 포트를 명시한다. 원문 버퍼·캡처 핸들·HMAC 키를 하위 API나 로그에 넣지 않는다.

`CompareOutcome`은 `complete/partial/failed`, 성공 저장 receipt 목록, 사유를 보존한다. **`StoredComparison`은 기준·교차 두 근거와 비교 결과가 모두 저장 완료된 경우에만 존재**한다. 한쪽 저장 실패 시 이미 저장된 불변 근거는 보존하되 확정 가능한 비교 결과로 발행하지 않는다.

### 5.5 Host → Knowledge

| API 제안 | 최소 입력 | 결과·실패 의미 |
|---|---|---|
| `async def register_candidates(request: CandidateSubmission) -> CandidateAck` | 실행 키·동작/경로 후보·추출 출처/버전·근거·미해결 조건 | Knowledge가 정규화·중복·출처를 검증한 후보 ID/revision. 단서는 관찰 사실과 구분 |
| `async def project(request: ProjectionSubmission) -> ProjectionAck` | 실행 키·불변 원본 이벤트 ID·생산자·원본 revision·저장 완료 근거 참조 | 적용 revision/이미 적용됨 또는 거부·지연·실패. 같은 ID/다른 내용은 충돌 |
| `async def get_case_view(request: CaseReadRequest) -> CaseReadResult` | 실행 키·사례/자원 참조·조회자 권한·snapshot·유한 반환 상한 | 후보·관찰·정책/근거/판정 참조·revision·누락/최신성·`complete/partial/failed` |

후보 정본과 정규화는 Knowledge가 소유한다. **Host가 단서 등록·후보 조회·모든 투영 제출을 조정**한다. Observation/WebDiag, Comparison/Evidence, Verdict/Judge, 기대 정책/app 등록 journal이 각각 원본 producer이며 Host는 commit된 이벤트를 변경 없이 전달한다. 반환 필드와 이벤트별 제출 시점은 [상세 규격 §8](s1-api-spec.md#8-knowledge의-후보와-투영)에 정의한다. deferred 투영을 재제출할 때 대상 요청을 다시 보내지 않는다. 검증된 Projector만 그래프를 갱신하며 A가 X를 조회했다는 사실에서 A가 X를 소유한다고 추론하지 않는다.

S1은 `store_memory`로 테스트한다. 다른 서비스의 작업/정책/근거 정본을 Knowledge로 옮기지 않는다. `reachable_subjects`와 다중 홉 위임 질의는 S2에서 별도 계약으로 제안한다.

### 5.6 Host → Judge / Report

| API 제안 | 최소 입력 | 결과·실패 의미 |
|---|---|---|
| `async def judge(request: JudgeRequest) -> JudgeResult` | 실행 키·호출자 `ReadContext`·사례 참조·등록 기대 접근 정책 snapshot 또는 부재·A/B 주체 확인·저장 완료 비교 참조 | `Verdict` 또는 판정 자체의 처리 실패. Verdict는 `CONFIRMED/SUSPECTED/ALLOWED/UNDECIDABLE`·조건·근거·버전·사유·revision |
| `async def read_case_policy(request: JudgePolicyReadRequest) -> JudgePolicyReadResult` | 실행 키·호출자 `ReadContext`·사례 참조·선택적 기대 정책 대조 값 | app이 주입한 등록 정본 정책 또는 정상 부재/조회 실패. Host의 값만으로 정책을 신뢰하지 않음 |
| `async def build_report(request: ReportInput) -> ReportResult` | 실행 키·관찰/판정/작업 요약·생산자별 기대 기록. 근거/요청 레시피·감사는 주입된 읽기 포트로 조회 | DiagnosisReport와 PoC 상태/절차 또는 생성 실패. Report는 재전송 없이 제한·전송 불명·감사 완전성을 보존 |
| `async def read_audit(request: AuditReadRequest) -> AuditPage` | 실행 키·호출자 권한·producer/cursor·유한 반환 상한 | 각 생산자의 허용 이벤트·순번·연결 참조·다음 cursor·완전성/실패. 각 소유 서비스가 제공 |

Host가 작업을 조정하고 `app`이 Judge/Report가 소비할 읽기 포트를 주입한다. Report가 타 서비스 DB를 읽지 않는다. Host는 진단 작업 발급을 멈추고 Report task 생성 전에 app이 정한 유한 기한 안에서 각 생산자의 종료·감사 봉인을 시도한다. `read_audit`는 봉인을 요청하는 포트가 아니며 app이 주입한 생산자 소유의 내부 수명주기 경계가 이를 수행한다. 봉인·조회 실패 생산자도 기대 목록에 남기고 `last_sequence=None`과 감사 공백을 전달해 부분 보고를 허용한다. Report는 확인된 유효한 진단 prefix와 근거를 검증하며 미확정을 감사 완료로 바꾸지 않는다. Report task lifecycle과 cutoff 이후 Run/Task revision은 별도 private operations audit에 기록하고 `ReportInput.tasks`에서 제외한다. `ReportInput.tasks`는 cutoff 당시 diagnostic journal에 마지막 확정된 Task별 업무 revision으로 고정하며 현재 공개 Task의 post-cutoff revision으로 대체하지 않는다. 동일 attempt_ref를 다른 Task에서 재사용할 경우 내용은 완전히 같아야 하고, `send_counts`는 전체 Run의 고유 attempt_ref별 집계다(COMPLETE 정확 일치, PARTIAL 관찰 하한). Report는 공개 RunStatus/TaskSummary만으로 run.v1/task.v1 digest를 재계산할 수 없으므로, diagnostic reader가 제공한 Host RUN/TASK binding·receipt를 Host verify_committed로 확인하는 **제공자 attestation**만 주장한다. 공개 RunStatus에는 Report task를 포함한 모든 task를 보존한다. 감사는 기대 request/event ID와 실제 연결을 비교한다. A·B가 필요한데 A·A 두 건이 있는 경우를 완료로 처리하지 않는다. 생산자별 저장 내구성과 조회 snapshot을 확인하지 못하면 감사 완전성은 unknown이다. 종료·봉인 확인과 운영 감사의 수위 검증은 [Host 계약](host-public-contract-v0.1.md#4-진단-감사와-운영-감사--독립-경계)을 따른다.

Judge는 다음 셋을 각각 확인한다: **(a)** 현재 적용되는 등록 기대 정책과 공유/위임 예외 해소, **(b)** A·B의 유효한 실제 subject, **(c)** 같은 소유자 객체의 정상 응답에 비자명 실데이터가 있고 교차 응답이 그것을 반환한다는 근거. HTTP 200·HMAC 일치·ID echo·owner_id·공통 템플릿만으로 확정하지 않는다. 규칙·검증 canary는 Judge가 소유하고 `app`이 로컬 Evidence에 주입한다. ([오라클 기준](module-design-confirmed.md#7-확정-오라클--읽기-전용-수평-idor-judge-패키지))

## 6. 경계를 통과하는 핵심 결과

| 결과 | 최소 의미 값 | 포함하지 않는 값 |
|---|---|---|
| `Observation` | 실행 키·요청/관찰 ID·계정/generation·주체 확인 참조·자원/동작·정상/로그인/오류/불명 응답 구분·저장 완료 근거 참조·제한 | 응답 원문·쿠키·캡처 핸들 |
| `ObserveResult` | `complete/partial/failed`·`Observation` 또는 `None`·모든 시도의 `attempt_summaries`·사유. 관찰 미완료여도 시도 요약은 보존 | 캡처 핸들·완료되지 않은 근거 |
| `AccessCompareResult` | 실행 키·사례/자원·기준/교차 계정·관찰·저장 완료 비교 참조 또는 `None`·`complete/partial/failed`·모든 시도의 `attempt_summaries`·미충족 조건 | 취약점 최종 판정·원문·캡처 핸들 |
| `StoredComparison` | 두 근거·동일 객체/계정 맥락 확인·정상/오류/로그인/반사 대조·비자명 객체 구분 조건·정규화/오라클 버전·비교 결과·완료 receipt | HMAC 키·원문. 일치만으로 취약점 확정하는 값 |
| `ExpectedAccessPolicy` | 출처·revision·적용 자원/동작·허용/금지 subject/role·공유/위임 예외·유효 범위/시각·검증 상태 | 평가 정답·`expected_verdict` |
| `Verdict` | 위 API의 판정 값·각 조건 평가·신뢰된 근거와 정책 출처·한계 | 전송 지시·캡처 핸들·공유/위임을 임의 보충한 정책 |
| `AuditPage` | 실행 키·producer·event ID/순번·작업/정책/시도/근거/판정 연결·시각·누락/조회 한계 | 원문 요청/응답·실행 비밀·오류 traceback |

## 7. 구체적인 입출력 예시

예시는 전체 record가 아닌 설명용 JSON 발췌다. 최종 wire schema나 외부 API를 정의하지 않는다. 생략된 실행 키·Candidate 필드·정책/주체 확인·저장 receipt·원본 projection_event(s)는 위 타입 정의에 따라 포함해야 한다. 문자열은 가상 식별자이며 실행 권한을 부여하지 않는다.

실행 영역 내부에서 `execute`가 전송 여부를 확인하지 못한 예:

```json
{
  "request": {
    "prepared_handle": "prepared-1",
    "decision": {"decision_ref": "decision-1", "outcome": "allow", "binding_id": "binding-1"}
  },
  "response": {
    "request_ref": "request-1", "attempt_ref": "attempt-1", "send_status": "unknown",
    "capture_status": "indeterminate", "capture_ref": null,
    "reason_codes": ["send_acknowledgement_lost"]
  }
}
```

Host에 반환하는 `access_compare` 부분 결과 예:

```json
{
  "request": {"candidate": {"candidate_ref": "candidate-1", "revision": 1, "resource_ref": "resource-1"}, "owner_account_ref": "account-a", "evaluated_account_ref": "account-b"},
  "response": {
    "case_ref": "case-1", "status": "partial",
    "stored_evidence_refs": ["evidence-owner-1"], "stored_comparison": null,
    "attempt_summaries": [
      {"request_ref": "request-owner-1", "attempt_ref": "attempt-owner-1", "send_status": "sent"},
      {"request_ref": "request-cross-1", "attempt_ref": "attempt-cross-1", "send_status": "sent"}
    ],
    "reason_codes": ["cross_evidence_store_failed"]
  }
}
```

전송 불명을 Host에 전달하는 `http_observe` 실패 결과 예:

```json
{
  "request": {"candidate": {"candidate_ref": "candidate-1", "revision": 1}, "account_ref": "account-a"},
  "response": {
    "status": "failed", "observation": null,
    "attempt_summaries": [
      {"request_ref": "request-1", "attempt_ref": "attempt-1", "send_status": "unknown"}
    ],
    "reason_codes": ["send_acknowledgement_lost"]
  }
}
```

Judge가 기대 접근 정책을 확인할 수 없는 예:

```json
{
  "request": {"case_ref": "case-1", "expected_policy": null, "comparison_ref": "comparison-1"},
  "response": {
    "status": "complete",
    "verdict": {"case_ref": "case-1", "value": "UNDECIDABLE", "comparison_ref": "comparison-1", "reason_codes": ["expected_access_policy_missing"]},
    "reason_codes": []
  }
}
```

## 8. 담당별 첫 PR과 대체할 의존성

| 담당 | 첫 구현 범위 | 자기 테스트에 둘 fake | API 검토 상대 |
|---|---|---|---|
| 이동찬 | C1 공유 codec → C2 최소 실행 계약 PR. Knowledge 메모리·app 조립·eval 평가기는 필요한 경계별 별도 PR | Evidence 읽기/저장 receipt, WebDiag 결과, Judge 판정, producer 감사 페이지 | 이경준·최민준 |
| 최민준 | Policy 기본 거부·Gateway prepare/execute 경계와 무전송 transport. Judge 순수 오라클·Report 집계는 별도 작은 PR | 설정/취소 provider, 감사 journal, 세션, 로컬 Evidence. Judge에는 저장된 비교·정책·주체 fixture | 이경준·이동찬 |
| 이경준 | WebDiag 단일 seed/HTTP 관찰·A/B 주체 확인·비교 조정. Host 작업 계획/중지와 Evidence 로컬 캡처·저장은 별도 작은 PR | WebDiag에는 Gateway/Policy/로컬 Evidence. Host에는 WebDiag/Knowledge/Judge/Report, Evidence에는 저장 실패·등록 규칙 fake | 최민준·이동찬 |

한 사람의 전체 담당 패키지를 한 PR에 넣지 않는다. 정규화 규칙·canary 초안은 최민준이 정의하고 이경준이 그 입력으로 Evidence를 테스트한다. 이경준은 최민준의 실제 Gateway를 기다리지 않고 같은 결과 의미의 fake를 사용한다. 이동찬은 각 fake를 조립해 호출 연결을 먼저 확인한다. 담당 배정의 정본은 [모듈 개발 가이드](../module-development.md#담당-배정)다. 일정과 실제 착수 지시는 PM이 팀과 조율한다.

`eval/`의 정답은 평가기만 읽는다. 모듈의 로컬 테스트 fixture와 예시 응답은 허구의 입력/예상 출력이며 제품 입력에 `expected_verdict`나 평가 label을 넣지 않는다. `eval/` 하네스 추가 시 별도 실행 명령·CI 수집을 정의한다. 현재 `check eval`은 없다. ([평가 영역](../../eval/README.md))

## 9. 독립 개발·초기 통합 수용 기준

아래는 **작성할 테스트 요구사항**이다. 현재 테스트가 구현돼 있거나 통과했다는 뜻이 아니다. 제공자와 소비자는 같은 case ID의 관찰 가능한 결과를 확인한다.

| ID | 입력/장애 주입 | 통과 기준 |
|---|---|---|
| S1-01 | 정상 허용 자기 관찰 | Gateway 요청 기록 1건, 저장 완료 Evidence가 있는 공개 Observation 반환 |
| S1-02 | policy block / 바인딩 불일치 / 위조 view / origin 밖 redirect | 해당 금지 전송 0건, 각각 다른 사유와 감사 기록 |
| S1-03 | 전송 확인 중 연결 끊김 | `unknown`, capture 없음, 자동 재전송 0회, 상태/보고에서 미전송으로 집계하지 않음 |
| S1-04 | 전송 확정 후 캡처 실패 | `sent/unavailable`, 공개 완료 근거 없음, 실패 사유와 이미 발생한 전송 보존 |
| S1-05 | A 또는 B 주체 불명·만료·generation 변경 | 오래된 주체 확인을 재사용하지 않음. 교차 전송 0건, Judge에 불충족 사유 보존 |
| S1-06 | 비교 근거 한쪽만 저장 성공 | 성공 근거는 불변 보존, `partial`, `StoredComparison` 없음, `CONFIRMED` 없음 |
| S1-07 | 기대 정책 누락·공유/위임 예외 불명 | 허가 없는 교차 전송 0건. Judge 단위 입력에서는 `UNDECIDABLE` 또는 근거 있는 `SUSPECTED`, 확정 없음 |
| S1-08 | 정책상 B 금지·A/B 유효·동일 객체의 비자명 실데이터 교차 반환·근거 저장 완료 | Judge가 각 (a)(b)(c) 근거를 연결한 `CONFIRMED` 반환 |
| S1-09 | 순수 ID echo·owner_id 단독·공통 템플릿·로그인/오류 응답·구분을 지우는 정규화 | 비교가 일치해도 `CONFIRMED` 없음, 부족한 조건·규칙 버전 보존 |
| S1-10 | B 자기 객체가 없는 유효 사례 | B 자기 객체가 없다는 사유만으로 차단/오류 처리하지 않음. 필요한 기준은 A와 교차 객체 |
| S1-11 | 전송 전 intent/정책 내구 저장 실패 또는 실행 중지 | 새 요청 0건, 실패/중지 상태와 이미 전송된 시도의 unknown 보존 |
| S1-12 | 동일 원본 이벤트 재제출 / 동일 ID 다른 내용 / 감사 A·A와 기대 A·B | 멱등 처리 / 충돌 / 감사 미완료를 각각 구분. 정책 출처 없는 OWNS 생성 0건 |
| S1-13 | 공개 결과·로그·보고·제품 경로의 fixture 접근 검사 | 원문·쿠키·토큰·캡처 핸들·HMAC 키·평가 GT 없음 |

모듈 첫 PR의 완료 조건: 문서의 적용 case ID 명시, 소비하는 로컬 fake/fixture, 해당 `check <module>` 통과, 다른 서비스 구현 import 없음. fake는 구조적 Protocol 검사와 행동 사례를 모두 확인한다. 구조적 타입 적합성만으로 인가·내구성·실제 네트워크 통제를 증명하지 않는다.

초기 통합은 `app/tests/`에서 모든 상대를 fake로 조립해 위 상태/근거 연결을 확인한다. 이후 한 모듈씩 실제 구현으로 교체해 같은 사례를 반복한다. 실제 네트워크·저장 통합은 `integration` marker와 별도 준비/실행 방법을 갖춘다. 기본 pytest는 integration을 제외한다.

상세 규격의 추가 사례 S1-14~28과 [PoC 사례 S1-29~36](poc-report-design.md#6-예시와-구현-검증)도 해당 구현 PR에서 검증한다. PoC는 원 실행의 레시피·근거를 설명하며 S1 별도 재실행 상태는 not_run이다. [가상 예시 보고서](../examples/s1-poc-report.example.md)를 실제 발견/검증 결과로 사용하지 않는다.

팀 리뷰 보완 사례 S1-37~42는 [상세 규격 §11](s1-api-spec.md#11-초기-한도-사유-코드와-개발-사례)에 정의한다. 공유 codec·identity 축약·Host 투영·request ID 발급·등록 재검증·전송 직전 최신 세션/잔여 예산을 검증한다.

## 10. 선택한 초기 설계와 팀 리뷰

| 항목 | 이번에 선택한 기준안 | 검토자 | 독립 개발·통합에서 확인할 것 |
|---|---|---|---|
| D1 요청 준비·바인딩 | Gateway 소유 불변 요청/view·15초·단일 소비, Policy에 값 전달·fingerprint 대조 | 최민준·이경준 | 가상 binding/핸들의 변조·위조·만료·중복 소비를 무전송으로 검증 |
| D2 기대 정책 등록/공급 | 신뢰된 등록 입력을 app이 검증, 구체 A/B·객체·동작의 불변 snapshot 주입 | 이동찬·최민준·이경준 | 정책 부재/만료·예외 불명을 보존. 관찰/GT에서 정책 생성 금지 |
| D3 세션·캡처 lifecycle | WebDiag 상태/generation, Gateway 통신 context, Evidence 캡처 단독 소유. TTL/복구/정리 필드 명시 | 이경준·최민준 | 주체 불일치·구세대·복구 충돌·실패 정리를 fake clock으로 검증 |
| D4 전송 전 감사 | producer별 journal + verify_committed. Policy 결정/Gateway intent 둘 다 실제 commit 확인 | 최민준·이경준·이동찬 | 위조 receipt/조회 실패는 무전송. 실제 내구성은 통합에서 별도 검증 |
| D5 최소 타입·비동기 실행 | I/O 포트 async·계산/메모리 인계 sync, 유한 큐·S1 worker 1개·취소/timeout·동시성 상한. 필수 필드·None·enum·사유 코드와 경계별 작은 계약 PR | 전원 | async fake와 Event로 경합 검증, 취소 후 전송 상태 보존. status/send_status/verdict 혼합 금지 |
| D6 fingerprint 소유권 | contracts의 stdlib-only 무상태 codec·명시적 payload·고정 벡터. 문서 판번호와 wire version 분리 | 전원 | 같은 PolicyInput은 동일 bytes/digest, 한 업무 필드 변경은 다른 digest, 임의 receipt 필터 금지 |
| D7 Knowledge 호출 조정 | Host가 후보 등록/조회/revision 검사와 원본 producer 이벤트의 project를 조정 | 이동찬·이경준 | WebDiag의 Knowledge 의존 0개, Host가 producer를 바꾸지 않음, deferred 재투영에 대상 재전송 0건 |

이번 기준안은 팀원이 입력/출력과 실패 사례를 더블 체크할 출발점이다. PM은 리뷰에 따른 수정·담당·적용 revision을 기록한다. 실제 교차 요청 전에는 [기존 D-0 단일 관문](module-design-confirmed.md#13-열린-결정-착수-전중-팀이-잠글-것)과 대상 허가·기대 정책·주체·안전 정책·Gateway 재검사를 충족해야 한다. 이 요구는 fake 개발의 대기 조건이 아니다.

## 11. 병렬 착수·검증 순서

1. **경계 리뷰·새 계약 PR:** C1~C4-A/C4-B와 Host↔WebDiag 공개 계약은 [착수 상태](s1-development-status.md)에 기록된 PR까지 병합됐다. 남은 Host `start_run/get_status/stop` 및 Report `build_report` 공유 타입·Protocol은 각 담당자와 작은 별도 계약 PR로 확정한다. Knowledge·app 등록은 기존 공개 계약으로 병렬 착수 가능하다. CLOSED/unmerged PR #8은 선행조건이 아니다.
2. **독립 구현:** §8의 첫 PR을 병렬 진행한다. I/O fake도 async def로 구현하고 순수 로직은 동기로 시험한다. S1-01~42의 해당 모듈별 수용 사례를 Event·fake clock과 무전송 fake로 단계별 검증한다. 계획된 전 사례를 이미 검증했다고 표시하지 않는다. `uv run --no-project --python 3.13.15 scripts/dev.py check <module>`을 실행하며 구현 간 내부 import를 추가하지 않는다.
3. **초기 조립:** 이동찬이 `app/tests/`에서 실제 외부 통신 없는 fake 시나리오를 조립한다. fake Gateway의 허용 시도 기록 1건은 실제 HTTP 전송 1건을 뜻하지 않는다. 실제 모듈 교체 때 제공자·소비자의 동일 case ID 결과를 비교한다. 전체 검사는 `check all`을 사용한다.
4. **실제 통합:** 필요한 실행 허가·역할 분리·내구 감사·인증/예산·비밀 보호·실제 전송 통제를 검증한 경로만 테스트 앱에 연결한다. 실제 통합 통과를 fake 테스트와 구분한다.

주요 위험과 대응: opaque 참조의 숨은 저장 구조 결합은 §5.3의 Gateway 소유/값 전달로 줄인다. 공용 타입 비대화는 경계별 최소 PR과 모듈 내부 소유로 제한한다. fake/실제 의미 불일치는 동일 case ID의 전송 기록·상태·근거/감사 연결 비교로 검증한다. 실제 내구성/인가를 fake 통과로 오인하지 않는다.

현재 기준 main(2026-10-23, `f649487`)에는 C1·C2, C3 Evidence 계약(#26·#27), C4-A Knowledge 계약(#30), Host↔WebDiag 계약(#38), C4-B Judge 계약(#39)과 Judge ReasonCode 매핑(#41), 웹 목업(#44)이 병합됐다. Host 공개 계약 v0.1은 현재 브랜치에서 contracts 구현 제안·문서화 중이며 팀 승인·병합·Host 서비스 구현을 뜻하지 않는다. Evidence 메모리 구현·PoC 요청 레시피(#35·#36)와 WebDiag 세션 기반(#40)도 부분 구현됐지만, 실제 S1 통합은 완료되지 않았다. Report의 보고 요청/결과는 별도 공유 계약으로 남아 있다. 이 문서의 C1/C2 첫 PR 표현은 당시의 개발 지침 이력으로만 읽고, 현행 구현·검증·남은 작업의 정본은 [S1 상태](s1-development-status.md#8-현재-서비스-구현과-남은-작업)를 따른다. 무전송 fake 검증을 실제 영속·대상 통신·S1 실행 성공으로 간주하지 않는다.
