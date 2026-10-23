# S1 착수 상태와 계약 PR 순서

확인 기준: **2026-10-23, 최신 main `f649487` (PR #44까지)**. C1·C2·C3·C4-A에 이어 C4-B Judge 공유 계약도 [PR #39](https://github.com/ABC2LAB/abc2lab-dast/pull/39)로 병합됐다. Host↔WebDiag 공유 계약은 PR #38, WebDiag 세션 기반은 PR #40, Judge 사유 코드 매핑은 PR #41, 웹 목업은 PR #44로 반영됐다. 이번 브랜치에는 [Host 공개 계약 v0.1](host-public-contract-v0.1.md)의 contracts 구현 제안과 검증 문서가 추가되어 있으나 아직 병합·팀 승인·Host 서비스 구현 완료가 아니다. 공유 계약 병합과 각 서비스의 실제 구현·영속 journal·S1 통합·대상 전송 허가는 서로 구분한다. 현재 서비스 구현과 남은 작업은 [§8](#8-현재-서비스-구현과-남은-작업), 담당 배정은 [모듈 개발 가이드](../module-development.md#담당-배정)를 따른다. 각 팀원의 개인 status.md/plan.md/CLAUDE.md는 이 저장소에 없으므로 여기서 수정하지 않는다.

## 0. 현재 선행조건

| 항목 | 확인한 상태 | 개발에 미치는 영향 |
|---|---|---|
| [PR #8](https://github.com/ABC2LAB/abc2lab-dast/pull/8) | CLOSED, 병합되지 않음 | 기존 실행 관문 타입은 제공되지 않는다. #8 병합을 대기하거나 해당 브랜치를 복원하지 않는다 |
| [PR #9](https://github.com/ABC2LAB/abc2lab-dast/pull/9) | MERGED, 문서 변경 | v0.3 설계가 main에 들어갔으며 타입·Protocol·fake 구현은 없음 |
| [PR #10](https://github.com/ABC2LAB/abc2lab-dast/pull/10) | MERGED, PoC·팀 리뷰 설계 보완 | v0.5 문서·미실행 예시·정적 벡터가 main에 반영됨. 자동 생성기·공유 codec 구현 완료가 아님 |
| contracts 패키지 | C1·C2·C3·C4-A·C4-B와 WebDiag 공유 계약 병합 완료 | 공통·실행·근거·후보/투영·Judge·WebDiag 타입과 포트 사용 가능. Host·Report 공개 계약은 후속 |
| [PR #15](https://github.com/ABC2LAB/abc2lab-dast/pull/15) | MERGED, C1 코드·테스트·계약 문서 | `primitive-v1` bytes/SHA-256 검증, 불변 snapshot 및 미등록 운영 record 거부 구현 |
| [PR #20](https://github.com/ABC2LAB/abc2lab-dast/pull/20) | MERGED, C2 실행·세션·감사 계약 | 5개 운영 kind의 typed adapter, 저장 전 내용 타입, 8개 포트·무전송 예제 구현. 실제 서비스와 감사 내구성 구현은 후속 |
| [PR #26](https://github.com/ABC2LAB/abc2lab-dast/pull/26) | MERGED, C3-A 동기 캡처 계약 | 실행 전용 타입·`LocalCapturePort`·무전송 예제 사용 가능. 실제 Gateway/Evidence 캡처 구현은 각 담당자 책임 |
| [PR #27](https://github.com/ABC2LAB/abc2lab-dast/pull/27) | MERGED, 후속 C3 공유 계약과 리뷰 보완 | Evidence·Comparison·recipe·저장/조회·봉인/복구 포트와 fingerprint 사용 가능. 실제 제공자 구현·통합 검증 완료를 뜻하지 않음 |
| [PR #35](https://github.com/ABC2LAB/abc2lab-dast/pull/35)·[PR #36](https://github.com/ABC2LAB/abc2lab-dast/pull/36) | MERGED, Evidence 로컬 캡처·저장·비교·복구 및 요청 레시피 | 메모리·무전송 구현 완료 범위. Gateway 실제 연계, 내구 감사·복구·인가 통합은 후속 |
| [PR #30](https://github.com/ABC2LAB/abc2lab-dast/pull/30) | MERGED, C4-A Knowledge 공유 계약 | 후보·투영·조회 타입, KnowledgePort, typed fingerprint·고정 벡터·무전송 테스트 사용 가능. 실제 Knowledge 서비스 구현 및 통합 검증은 후속 |
| [PR #38](https://github.com/ABC2LAB/abc2lab-dast/pull/38) | MERGED, Host↔WebDiag 공유 계약 | WebDiag 요청·결과와 `WebDiagPort` 사용 가능. Host 진입점과 Report 계약은 포함하지 않음 |
| [PR #39](https://github.com/ABC2LAB/abc2lab-dast/pull/39) | MERGED, C4-B Judge 공유 계약 | `JudgeRequest`·`JudgeResult`·`JudgePort`와 app 주입 `JudgePolicyReader`, `verdict.v2`·ALLOWED·ReasonCode 9개 및 실패 사유 분류. 실제 Judge 서비스·등록 저장소·영속 journal 확장은 후속 |
| [PR #40](https://github.com/ABC2LAB/abc2lab-dast/pull/40) | MERGED, WebDiag 세션 기반 | 바인딩 저장소·상태 전이·context open/close 구현. 발견·whoami·관찰·교차 비교 전체 구현은 후속 |
| [PR #41](https://github.com/ABC2LAB/abc2lab-dast/pull/41) | MERGED, Judge 사유 코드 매핑 | 미대응 9개를 공개 ReasonCode로 매핑하고 관련 xfail 해소. `JudgePort.judge` 전체 조립·내부 ALLOWED 경로는 후속 |
| Host 공개 계약 v0.1 | 현재 브랜치의 contracts 구현 제안·문서화, 아직 Draft 팀 리뷰 전 | `start_run/get_status/stop`의 요청·결과·`ReadContext`, Run 업무 revision과 `snapshot_revision`, 진단 journal cutoff 후 Report lifecycle/Run finalization의 독립 operations audit, `FINALIZING`·`NOT_APPLICABLE`, 독립 진단·운영 감사 completeness와 `run.v1`/`task.v1` fingerprint를 기준으로 Host 서비스 인수 테스트를 후속 수행 |
| [PR #14](https://github.com/ABC2LAB/abc2lab-dast/pull/14)·[PR #16](https://github.com/ABC2LAB/abc2lab-dast/pull/16) | MERGED, C3·C4 최소 계약 초안과 리뷰 반영 | capture·Judge 소유 경계의 문서 제안. C2나 C3·C4 구현·벡터·fake가 제공된 것은 아님 |

Policy/Gateway 공개 포트와 그 fake의 공유 선행조건인 **C2 실행 경계 계약 PR #20의 병합이 완료됐다.** 각 담당자는 최신 main의 contracts를 사용해 상대 서비스 구현을 기다리지 않고 자기 모듈과 로컬 fake를 개발·시험한다. 폐기된 PR #8을 선행조건으로 삼지 않는다. 공개 계약 대신 임의 Any·dict·서비스별 타입 사본을 만들지 않으며, 추가로 필요한 C3·C4 경계는 작은 계약 PR로 정의한다.

## 1. 작은 계약 PR로 다시 시작

| 단계 | 이동찬의 제안 범위 | 병합 후 가능한 작업 | 관련 리뷰 |
|---|---|---|---|
| C1 fingerprint codec (**MERGED, PR #15**) | [정규 바이트·검증 경로](fingerprint-contract.md#21-정규-바이트와-운영-계약-검증의-분리), stdlib-only canonical codec·demo 저수준 벡터·빈 운영 registry의 거부 검사 구현 완료 | 공통 canonical codec 사용 가능. 운영 record fingerprint 발행은 C2 typed adapter 검증 범위로 이동 | mminjun·31-no3won·sleepingman1222 |
| C2 실행 경계 (**MERGED, PR #20**) | 공통 Ref/RunKey/SourceVersion/상태, PolicyInput/Decision 및 필요한 등록·세션 snapshot, prepare/evaluate/execute·세션 읽기·commit 검증/감사 조회의 최소 Protocol. PolicyDecisionContent/IdentityContent precommit lifecycle, typed wrapper·adapter·운영 벡터와 무전송 예제 포함 | Policy/Gateway가 등록된 타입별 fingerprint와 contracts를 사용하는 병렬 개발·검증 | mminjun·31-no3won·sleepingman1222 |
| C3 로컬 Evidence (**C3-A #26 / 후속 #27 MERGED**) | capture/release 타입·동기 포트·무전송 예제 병합. 후속 PR에서 seal/compare·민감값 제거 근거·ComparisonProjected·저장 receipt·PoC 요청 레시피·복구 계약 구현 | C3-A로 Gateway의 캡처 인계와 Evidence 로컬 fake 연결. 추가 공유 계약도 #27 병합으로 사용 가능 | 31-no3won·mminjun |
| C4 발견·투영·보고 | Knowledge #30·Judge/정책 조회 #39·WebDiag #38 공유 계약 병합 완료. 남은 Host·Report 공개 계약은 담당자와 별도 확정 | 실제 서비스 구현과 무전송 연결을 병행하고 app에서 한 경계씩 교체 | 31-no3won·mminjun·sleepingman1222 |

C2를 위해 C3/C4의 전체 도메인을 먼저 정의하지 않는다. 아직 없는 capture 서비스 등은 실제 연동 전 해당 소계약을 병합한다. C2만으로 전체 Gateway/Evidence 연동이나 S1이 완료된 것으로 표시하지 않는다. 후속 단계의 내부 로직은 필요한 계약 준비와 병행할 수 있다. C3·C4의 gateway/judge 소유 경계(capture·Judge)는 [C3·C4 최소 계약 초안](c3-c4-contract-draft.md)에서 병렬로 제안한다.

### 1.1 C2 구현 범위와 검증 경계

현재 main에는 `primitives.py`, `registration.py`, `audit.py`, `session.py`, `execution.py`, `ports.py`와 contracts-owned fingerprint adapter가 있다. 공개 범위는 Gateway `prepare/execute/open_session_context/close_session_context`, Policy `evaluate`, `SessionBindingReader.read_session_binding`, 감사 `verify_committed/read_audit`의 8개 포트다. `tests/test_no_io_pipeline.py`의 fake는 prepare → evaluate → execute 흐름과 block/commit-unknown/send-unknown 보존을 네트워크·브라우저·DB 없이 검증한다. 이 fake는 실제 Gateway/Policy 구현, journal 내구성, 인가 증명 또는 취약점 진단을 대체하지 않는다.

PolicyDecisionContent와 IdentityContent는 각각 저장 전 fingerprint를 계산한 뒤 producer commit과 receipt를 거쳐 최종 결과로 조립한다. 최종 결과의 receipt는 consumer가 실제 producer 기록과 재계산·`verify_committed`로 확인한다. 이 결정은 기존 PolicyInput wire version과 C1 golden bytes를 바꾸지 않는다.

RunRegistration은 **app 소유의 내부 등록 집계 타입**으로 `app/src/abc2lab_app/registration.py`에 둘 예정이다. 각 서비스에는 필요한 불변 snapshot·설정만 주입하며 서비스가 app 타입을 import하지 않는다. C1의 `packages/contracts/src/abc2lab_contracts/fingerprint.py`는 이미 구현됐다. C2의 snapshot·요청·반환·Protocol과 업무별 fingerprint adapter는 `packages/contracts/src/abc2lab_contracts/`의 병합된 공유 계약을 사용한다.

## 2. 병렬 개발의 고정 책임

- Host: run/task/case ID, 작업·중복·취소, 후보 등록/조회/revision 검사와 모든 Projection 제출.
- WebDiag: 단서 반환, 인증·세션 상태, 모든 논리 HTTP request_ref 발급과 관찰/교차 실행 조정. Knowledge 포트를 받지 않음.
- Gateway/Policy: 실제 요청·현재 세션·등록 정책 독립 재검증, 같은 codec의 view fingerprint, 전송 직전 예산·상태 원자 검사.
- 각 원본 producer: 자기 journal과 불변 Projection 이벤트. Host는 다른 producer의 receipt·내용을 생성하거나 수정하지 않음.
- Evidence/Report: 근거·요청 레시피·PoC 절차와 누락 사유 보존. 보고서 생성이 추가 대상 요청을 보내지 않음.

C3 복구와 C4-B 정책 조회를 포함한 29포트의 명시적 목록은 [상세 규격 §3.1](s1-api-spec.md#31-s1-포트-수-대조), 전송 직전 세션 재조회와 감사는 [§10](s1-api-spec.md#10-감사-커밋과-조회), 새로운 검증 사례 S1-37~42는 [§11](s1-api-spec.md#11-초기-한도-사유-코드와-개발-사례)을 따른다. 현재 사례는 후속 테스트 요구사항이다.

## 3. C1 구현 확인과 재검증

C1 코드는 PR #15로 이미 병합됐다. 이번 확인에서는 [codec 구현](../../packages/contracts/src/abc2lab_contracts/fingerprint.py)과 [테스트](../../packages/contracts/tests/test_fingerprint.py)를 [공유 codec 계약](fingerprint-contract.md)·정적 벡터와 대조했다. API 사용 방법과 시각 경계의 현재 한계는 [공개 API 절](fingerprint-contract.md#22-c1-공개-api와-사용)에 기록한다.

| 확인 범위 | C1에서 확인하는 것 | 남아 있는 범위 |
|---|---|---|
| 정규 바이트 | `primitive-v1` 정확한 UTF-8 bytes·테스트 내 SHA-256, 중첩 키 정렬·tuple 순서·null/생략 구분·UTC 정규화 | 업무 record별 typed wrapper·payload adapter와 운영 벡터 5개는 C2 |
| 불변 snapshot | 원본 dict·mapping proxy와 참조 분리, 중복 키·순환 입력·가변 값 거부 | 호출자가 snapshot 생성 중 일관된 입력을 제공해야 함 |
| 입력 거부 | float·NaN·Infinity·list·set·bytes·Decimal·naive datetime·비문자 key·미등록 dataclass/enum·lone surrogate 거부 | 업무별 필드 allowlist·지원 schema/type 검사와 시각 허용 범위는 C2 |
| 운영 경계 | C1의 빈 고정 registry가 demo·미등록 운영 record를 거부 | C2 typed wrapper·Protocol·운영 fingerprint·무전송 예제는 PR #20으로 병합. S1-01~42의 실제 서비스 행동 검증은 후속 |

재검증 명령은 다음과 같다. 실제 대상·브라우저·DB 없이 Ruff lint/format, mypy와 contracts 테스트를 격리 실행한다.

```bash
uv run --no-project --python 3.13.15 scripts/dev.py check contracts
```

2026-10-21 재검증 결과: Ruff lint/format 통과, mypy 4개 파일 통과, contracts 테스트 **36개 통과**(fingerprint 35개·패키지 smoke 1개). Import Linter도 **6개 경계 유지·위반 0개**였다. 사용 예시를 실제 실행했고, 정적 문서 검사에서 로컬 링크/anchor·JSON 예시·27개 포트 목록·42개 예정 case ID와 고정 벡터 6개의 bytes/SHA-256 일치를 확인했다. 운영 벡터 5개의 정적 일치는 C2 typed adapter 테스트 통과로 집계하지 않는다.

독립 코드 검토와 아키텍처 검토에서 C1의 필수 수정 사항은 없었다. 시각 극단값의 `OverflowError`는 현재 한계로 기록했으며, C2 등록 전에 필요한 타입·버전·필드 검사는 [운영 계약 경계](fingerprint-contract.md#21-정규-바이트와-운영-계약-검증의-분리)에 명시했다. 이 구현 검토 기록은 팀원별 PR 승인 기록과 구분한다.

문서·고정 벡터의 정적 일치 확인은 위 codec 테스트와 구분한다. 현재 테스트의 성공이 S1 서비스 실행·인가·감사 내구성·실제 취약점 진단 완료를 의미하지 않는다.

## 4. C2 구현과 검증

2026-10-21, `codex/c2-execution-contracts`에서 C2 계약 구현을 검증했다. `PolicyDecisionContent`·`IdentityContent`를 추가해 저장 전 fingerprint 계산과 영수증 발급의 순환을 해소했다. 최종 결과의 기존 필드·영수증 필수 조건·서비스 호출과 `policy_input.v1`은 유지한다.

| 검증 | 결과 |
|---|---|
| `scripts/dev.py check contracts` | Ruff lint/format, mypy 18개 파일, contracts 테스트 **90개 통과** |
| 전체 기본 pytest / mypy | **104개 통과** / 41개 소스 파일 통과 |
| Import Linter | **6개 경계 유지, 위반 0개** |
| `uv build --package abc2lab-contracts` | wheel·sdist 생성 성공 |
| 운영 fingerprint | 5개 기존 벡터의 정확한 UTF-8 bytes·SHA-256 일치, 저장 전·후 내용 digest 일치 |
| 무전송 소비자 예제 | prepare→evaluate→execute, block·감사 확인 unknown·전송 unknown·위조 allow 거부의 5개 테스트 통과 |

독립 코드 검토와 아키텍처 검토의 지적을 반영해 감사 수위·cursor/snapshot·실패한 세션의 confirmed 표시를 검증했다. 재검토에서 남은 코드·명세 지적과 아키텍처 차단 사항은 없었다. 이는 팀원의 GitHub 승인 리뷰를 대신하지 않는다.

C2는 [PR #20](https://github.com/ABC2LAB/abc2lab-dast/pull/20)으로 병합됐다. 각 담당자는 이 계약으로 독립 개발하며 실제 Policy/Gateway/WebDiag·영속 journal·세션/예산 통제·HTTP/DB·C3/C4 및 S1 전체 행동 수용 사례는 후속 검증 범위다. C2 구현은 의존성·`uv.lock`·기존 고정 벡터 파일을 변경하지 않았다.

## 5. C3-A 캡처 계약 — 병합 완료

2026-10-21, `codex/c3-capture-contracts`에서 `contracts`의 첫 C3 경계를 구현하고 검증했으며 [PR #26](https://github.com/ABC2LAB/abc2lab-dast/pull/26)으로 병합됐다. [C3-A 구현 범위](c3-c4-contract-draft.md#21-c3-a-캡처-계약-구현--병합-완료)는 실행 전용 타입 6개와 `LocalCapturePort`의 동기 메서드 2개다. C2의 8개 포트와 scalar/상태/사유 타입은 유지한다. 기존 S1의 동기 포트 2개를 하나의 `LocalCapturePort` Protocol로 정의하며 S1 전체 포트 수는 늘리지 않는다. 아래는 C3-A 구현 당시 검증 기록이다.

| 검증 | 결과 |
|---|---|
| `scripts/dev.py check contracts` | Ruff lint/format·mypy 21개 파일·contracts 테스트 **130개 통과** |
| 전체 기본 pytest / mypy | **207개 통과** / 48개 소스 파일 통과 |
| Import Linter | **6개 경계 유지, 위반 0개** |
| `uv build --package abc2lab-contracts` | wheel·sdist 생성 성공 |
| 변경 범위 | contracts와 관련 공유 문서만 변경. 타 서비스·의존성·uv.lock·fingerprint codec/registry·기존 벡터 변경 없음 |

`capture.py`의 타입은 불변·repr 비노출을 적용하며 공개 JSON/MCP·저장·fingerprint 대상으로 사용하지 않는다. 포트 구현이 등록과 캡처 맥락·한도·수명·참조 정리를 검사하며, 테스트용 fake의 통과를 실제 Evidence·Gateway 구현이나 전송 허가로 집계하지 않는다.

seal/compare·Evidence 공개 저장/조회·ComparisonProjected·요청 레시피와 업무별 fingerprint는 후속 계약이다. Evidence 담당 이경준·Gateway 담당 최민준의 경계 검토 후 한 단계씩 연결하며, 이동찬은 해당 서비스 소스를 수정하지 않는다.

2026-10-21, 이경준의 후속 제안을 검토하고 [Evidence C3 계약 보완안](evidence-c3-contract.md)을 기록했다. EvidenceSummary.source_event는 Evidence가 fingerprint 전에 고정하는 자체 artifact 감사 링크로 이동찬이 확인했다. Gateway 결과 commit을 capture 선행조건으로 두지 않는다. EvidenceSummary/ComparisonPayload에는 별도 Content 타입을 추가하지 않는다. 후속 구현과 리뷰 상태는 아래 §6으로 연결한다.

## 6. 후속 C3 Evidence 계약 — PR #27 병합 완료

`feat/c3-evidence-contracts`에서 [C3 동결안](evidence-c3-freeze.md)의 공유 타입·실행 전용/공개 포트·recipe·`evidence.v1`/`comparison.v1` typed fingerprint와 고정 벡터를 구현했다. [PR #27](https://github.com/ABC2LAB/abc2lab-dast/pull/27)은 2026-10-22 병합됐고 로컬 main과 C4 작업 브랜치에 반영했다. 각 담당자는 병합된 계약으로 실제 서비스 구현과 통합 검증을 이어간다.

리뷰 보완으로 결과와 receipt의 run·상태·사유, 함께 제공된 payload의 fingerprint, Evidence/recipe의 동작·자원 일치와 경로 형태를 검증한다. 이동찬 확인에 따라 일부 저장 성공 후 나머지 복구가 불가능해도 성공 receipt는 `PARTIAL`에 보존한다. 무전송 fake는 등록과 다른 recipe가 저장 전에 거부됨을 검사하며 실제 인가·저장 서비스의 검증을 대신하지 않는다.

2026-10-21 로컬 검증: `scripts/dev.py check contracts`의 Ruff lint/format·mypy 25개 파일·테스트 **172개**, 전체 기본 pytest **254개**·mypy **51개 파일**, Import Linter **6개 경계 유지·위반 0개**, contracts wheel·sdist 빌드 모두 통과했다. 실제 제출 내구 기록·감사·Lease/Fencing·재시작 복구는 Evidence 제공자의 후속 구현·검증 범위이며 이 결과에 포함하지 않는다.

2026-10-22 리뷰 보완: [동결안 §6](evidence-c3-freeze.md#6-감사-연결비교-진단과-남은-리스크)에 EVIDENCE binding.attempt_ref → 주입된 Gateway ATTEMPT 감사 조회/검증 경로를 고정했다. 공개 AuditPage에 전체 AttemptRecord가 없다는 검증 한계를 명시하고, Gateway가 원본 digest·전송 metadata를 보장하도록 구분한다. 비교 UNKNOWN의 신호별 사유와 canary 3상태는 Evidence COMPARISON 감사 metadata에서 확인한다. `validate_evidence_audit`·`validate_comparison_audit`와 복구 kind/반환 타입/run을 검사하는 `validate_recovery_result`를 추가했다. evidence.v1/comparison.v1 payload와 기존 고정 벡터, capture 입력 및 서비스 포트 시그니처는 유지한다. 이 보완은 PR #27에 포함됐으며 서비스 구현 완료가 아니다.

보완 후 로컬 검증: `scripts/dev.py check contracts`에서 Ruff lint/format·mypy **26개 파일**·테스트 **230개 통과**(추가 회귀 사례 58개), `scripts/dev.py check all`에서 전체 pytest **312개**·mypy **51개 파일**·Import Linter **6개 경계 유지/위반 0개**, 전체 패키지 wheel·sdist 빌드와 외부 라이브러리 import smoke가 통과했다. 테스트는 순수 계약 검증이며 실제 Gateway/Evidence 감사 조회·commit·전송 증명의 통합 검증은 후속 제공자 책임이다. GitHub CI와 사람의 PR 승인은 이 로컬 검증과 별도로 확인한다.

같은 날 추가 리뷰의 주체 구분·레시피 부재 기준을 [동결안 §6.3·§6.4](evidence-c3-freeze.md#63-owner--evaluated-주체-구분-2026-10-22-보완)에 반영했다. 동일 주체 비교를 NO/UNKNOWN으로 보존하되 같은 identity_ref의 distinct YES는 구조적으로 거부한다. recipe_missing/unsupported/not_exportable의 선택 기준은 생성·공개 능력에 따라 제공자가 판단하며 실제 바인딩 실패와 구분한다. 추가 신원 경계 회귀 **5개**, contracts **235개**·전체 **317개** 테스트와 기존 Ruff·mypy·6개 의존 경계·전체 패키지 빌드·import smoke가 통과했다. 다른 담당 서비스 구현과 fingerprint adapter·고정 벡터는 변경하지 않았다.

## 7. C4-A Knowledge 공유 계약 — PR #30 병합 완료

`codex/c4-knowledge-contracts`에서 [C4-A 계약](knowledge-c4-contract.md)의 비동기 `KnowledgePort` 3개 메서드, 후보·조회·투영 상태 타입과 폐쇄 `ProjectionEvent`를 추가했다. 선행 의존성 C3 [PR #27](https://github.com/ABC2LAB/abc2lab-dast/pull/27)은 병합됐으며 C4-A는 [PR #30](https://github.com/ABC2LAB/abc2lab-dast/pull/30)으로 병합 완료됐다. 실제 Knowledge 서비스 구현·통합 검증은 후속 작업이다.

Observation/Verdict payload와 원본 projection, 기존 ExpectedAccessPolicySnapshot의 projection을 최소 공유 자료형으로 정의하고 typed fingerprint wrapper·adapter·고정 벡터를 추가한다. 이 변경은 WebDiag·Judge·Report의 서비스/호출 포트나 Knowledge의 실제 메모리 저장소를 구현하는 범위가 아니다. 무전송 예제는 명시적으로 연결한 한 후보와 Observation으로 등록→조회→검증·투영→재조회를 재생한다. 이경준(Host/WebDiag/Evidence)·최민준(Judge/Policy/Report)의 영향 경계 리뷰가 필요하다.

2026-10-21 로컬 검증: 격리 `check contracts`에서 Ruff·mypy 33개 파일·계약 테스트 221개, 전체 pytest 303개·mypy 55개 파일, Import Linter 6개 경계와 contracts wheel·sdist 빌드가 통과했다. 기존 fingerprint 벡터 8개를 유지하고 새 3개 wrapper의 정규 bytes·digest를 고정했다. 실제 서비스·통합·GitHub CI·팀원 승인 완료와 구분한다.

## 8. 현재 서비스 구현과 남은 작업

2026-10-22 `main`의 `8f6fdd2` 소스와 PR 병합 기록을 대조한 상태다. 앞 절의 테스트 수치는 각 계약 PR 당시의 이력이다. S1 규격의 29포트 집계는 설계된 호출 목록이며, 모든 포트의 공유 타입·실제 제공자가 구현됐다는 뜻이 아니다.

| 영역·담당 | 현재 구현 범위 | 남은 작업 |
|---|---|---|
| contracts·이동찬 | C1~C3, C4-A Knowledge, C4-B Judge, WebDiag 공유 타입·포트·fingerprint와 계약 테스트. Host 공개 계약 v0.1은 현재 브랜치에서 구현 제안·문서화 | Host 계약 리뷰·병합 후 start_run/get_status/stop 서비스 인수, ReportInput/ReportResult/build_report 최소 공개 계약을 각 담당자와 별도 확정 |
| knowledge·이동찬 | 패키지 골격과 smoke 테스트 | 메모리 register_candidates/project/get_case_view, 후보 중복·이벤트 연결·snapshot 규칙, 인가·원본 감사 검증. AGE 어댑터는 후속 |
| app·이동찬 | 조립 루트 골격 | case↔정책 정본·등록 조회 제공자, ReadContext·검증 포트와 구현 주입, 무전송 S1 조립·이후 실제 어댑터 연결 |
| eval·이동찬 | [담당 범위 안내](../../eval/README.md) | 평가 하네스·데이터/라벨·지표·재현 절차와 CI 실행 경로. GT를 제품 입력에서 격리 |
| gateway·최민준 | prepare, 등록/세션 대조와 준비 핸들 | execute·실제 transport·전송 직전 통제·캡처 인계·내구 감사와 세션 context 제공자 |
| policy·최민준 | 순수 평가, PolicyService.evaluate와 메모리 journal | app 주입·Gateway 연동, 내구 저장·감사 및 장애/복구 통합 검증 |
| judge·최민준 | 순수 오라클, VerdictPublisher와 메모리 journal, PR #41의 사유 9개 매핑 | JudgePort.judge에서 정책 reader·신원·Evidence 검증 연결, ALLOWED 서비스 관문, 영속화·멱등성/CAS·시각 검증 |
| report·최민준 | 패키지 골격과 smoke 테스트 | build_report, 감사 완결성·누락·전송 unknown 보존, Evidence/Comparison/Verdict와 무전송 PoC 보고 |
| webdiag·이경준 | PR #40의 세션 바인딩·상태 전이·context 생명주기 | 발견·인증/whoami·관찰·교차 비교, Gateway/Policy/Evidence 조정과 원본 이벤트 반환 |
| host·이경준 | 패키지 골격과 smoke 테스트. Host 공개 계약 v0.1은 [계약 문서](host-public-contract-v0.1.md)와 현재 contracts 제안으로 Draft 검토 중 | run/task/case 관리, 유한 큐·worker·취소, `FINALIZING`·stop 상태, 일관 업무 revision/`snapshot_revision`, 진단 cutoff·Report lifecycle·독립 operations audit, 후보 등록/조회·투영과 감사 기대 수위 조립 |
| evidence·이경준 | PR #35·#36의 capture·seal/compare·recover·레시피와 메모리 저장/조회 | 실제 Gateway 연동, 내구 저장·감사와 재시작 복구·인가 통합 검증 |

### 8.1 이동찬 담당 작업의 착수 우선순위 (제안)

이 표는 구현 완료를 뜻하지 않는 **현재 계획**이며, 일정·담당 승인을 대신하지 않는다. 개별 PR에는 확정한 공개 계약, 관련 소비자와 인수 테스트를 명시한다.

| 우선 | 작업 | 다음 PR의 완료 기준 | 의존/리뷰 |
|---|---|---|---|
| 1 | Host 공개 계약 | [Host 공개 계약 v0.1](host-public-contract-v0.1.md)의 요청·결과·Protocol·상태/취소/멱등·감사 기준을 팀 리뷰하고 contracts PR로 병합. 현재 문서는 구현 완료나 Host 서비스 인수 완료를 주장하지 않음 | Host 이경준과 협의, contracts 이동찬 구현 |
| 1 | Report 공개 계약 | `ReportInput`·`ReportResult`·`build_report` 및 감사·근거·부분 결과 규칙 확정과 테스트 | Report 최민준과 협의, Host 이경준 소비 검토; Host와 **별도 PR** |
| 2 | Knowledge 메모리 제공자 | `register_candidates/project/get_case_view`의 동일 제출 멱등·충돌·revision·인가·감사 원본 검증·한도 | C4-A #30 사용; Host/Report 계약 없이 병렬 착수 가능 |
| 3 | app 신뢰된 등록 정본 | `RunRegistration`·run/case↔자원/동작/주체/정책 원본 저장 및 `JudgePolicyReader`의 정상 부재/검증 실패 구분 | C4-B #39 사용; Judge 최민준과 J-ALLOW-02 검토. Knowledge 관찰 자료나 GT로 허용 정책을 만들지 않음 |
| 4 | app 무전송 S1 조립 | 서비스 Port/Fake 주입·기존 원본 이벤트 전달·취소/전송 unknown/부분 기록 불변 테스트 | Host·Report 계약, 각 서비스 제공자의 검증 가능한 범위에 맞춰 단계별 연결 |
| 5 | eval 평가 하네스 | GT 격리·코퍼스/라벨·채점/지표·실행 명령·CI 경로 | Knowledge/조립 개발과 초기 골격 병행 가능, 실제 GT는 제품 경로에 주입 금지 |

메모리 Knowledge와 app 등록·평가 기반은 Host/Report 계약 리뷰와 **병렬**로 개발할 수 있다. PostgreSQL+AGE 어댑터, 실제 웹 UI/API·Compose 패키징은 S1의 검증 가능한 최소 경로 후속으로 나눈다.

이동찬의 다음 작업은 남은 Host·Report 공유 계약을 작게 확정하고 Knowledge 메모리 서비스, app의 신뢰된 등록 경계와 무전송 조립을 구현하는 것이다. 팀원은 이미 병합된 포트의 로컬 fake로 자기 서비스 개발을 병행하며, Host·Report 내부 구현은 각 담당자가 소유한다.

웹 UI/API·개발용 LLM 설정·`app`/`ollama`/`db` Docker 패키징은 [로컬 배포 설계](local-deployment.md)의 후속 구현 범위다. 실제 대상 전송에는 내구 의도/정책 감사와 D-0 확인이 필요하며, 메모리 대역 연결이나 계약 테스트 통과만으로 허용하지 않는다.
