# S1 착수 상태와 계약 PR 순서

확인 기준: 2026-10-21, [PR #15](https://github.com/ABC2LAB/abc2lab-dast/pull/15)의 C1 병합과 [API 상세 규격 v0.5](s1-api-spec.md) 팀 리뷰 반영 시점. C1 codec 외의 실행 경계·서비스 구현이나 실제 전송 허가를 선언하지 않는다. 각 팀원의 개인 status.md/plan.md/CLAUDE.md는 이 저장소에 없으므로 여기서 수정하지 않는다. 개인 계획의 선행조건도 아래 기준으로 갱신한다.

## 0. 현재 선행조건

| 항목 | 확인한 상태 | 개발에 미치는 영향 |
|---|---|---|
| [PR #8](https://github.com/ABC2LAB/abc2lab-dast/pull/8) | CLOSED, 병합되지 않음 | 기존 실행 관문 타입은 제공되지 않는다. #8 병합을 대기하거나 해당 브랜치를 복원하지 않는다 |
| [PR #9](https://github.com/ABC2LAB/abc2lab-dast/pull/9) | MERGED, 문서 변경 | v0.3 설계가 main에 들어갔으며 타입·Protocol·fake 구현은 없음 |
| [PR #10](https://github.com/ABC2LAB/abc2lab-dast/pull/10) | MERGED, PoC·팀 리뷰 설계 보완 | v0.5 문서·미실행 예시·정적 벡터가 main에 반영됨. 자동 생성기·공유 codec 구현 완료가 아님 |
| contracts 패키지 | C1 codec 구현 완료, C2 타입·Protocol 미구현 | `abc2lab_contracts.fingerprint`의 `canonical_json_bytes()`·`CanonicalObject`·`freeze_object()` 사용 가능. 업무 record별 fingerprint 발행과 Policy/Gateway 실행 포트는 C2 병합 전까지 제공되지 않음 |
| [PR #15](https://github.com/ABC2LAB/abc2lab-dast/pull/15) | MERGED, C1 코드·테스트·계약 문서 | `primitive-v1` bytes/SHA-256 검증, 불변 snapshot 및 미등록 운영 record 거부 구현. C2는 미구현 |
| [PR #14](https://github.com/ABC2LAB/abc2lab-dast/pull/14)·[PR #16](https://github.com/ABC2LAB/abc2lab-dast/pull/16) | MERGED, C3·C4 최소 계약 초안과 리뷰 반영 | capture·Judge 소유 경계의 문서 제안. C2나 C3·C4 구현·벡터·fake가 제공된 것은 아님 |

Policy/Gateway 공개 포트와 그 fake의 선행조건은 **C2 실행 경계 계약 PR의 병합**이다. C1은 공통 정규화 codec만 제공하며 운영 record별 fingerprint·실행 타입·Protocol은 아직 제공하지 않는다. 폐기된 PR #8을 선행조건으로 삼지 않는다. 조건/정규화/예산 등 모듈 내부 순수 로직은 먼저 구현·시험할 수 있다. 공개 계약 대신 임의 Any·dict·서비스별 타입 사본을 만들지 않는다.

## 1. 작은 계약 PR로 다시 시작

| 단계 | 이동찬의 제안 범위 | 병합 후 가능한 작업 | 관련 리뷰 |
|---|---|---|---|
| C1 fingerprint codec (**MERGED, PR #15**) | [정규 바이트·검증 경로](fingerprint-contract.md#21-정규-바이트와-운영-계약-검증의-분리), stdlib-only canonical codec·demo 저수준 벡터·빈 운영 registry의 거부 검사 구현 완료 | 공통 canonical codec 사용 가능. 운영 record fingerprint 발행은 C2의 정확한 타입/adapter 등록 전까지 거부 | 최민준·윤재상·이경준 |
| C2 실행 경계 | 공통 Ref/RunKey/SourceVersion/상태, PolicyInput/Decision 및 필요한 등록·세션 snapshot, prepare/evaluate/execute·세션 읽기·commit 검증의 최소 Protocol. 비밀 없는 identity/request_intent/attempt payload·typed wrapper·adapter·정적 registry 항목·운영 벡터 포함 | Policy/Gateway가 등록된 타입별 fingerprint와 실제 contracts를 사용하는 무전송 fake로 개발·검증 | 최민준·이경준·윤재상 |
| C3 로컬 Evidence | capture/seal/compare·캡처 수명·민감값 제거 근거·ComparisonProjected와 저장 receipt, PoC 요청 레시피 | Gateway의 캡처 인계, WebDiag 비교, Evidence 독립 테스트 연결 | 윤재상·최민준·이경준 |
| C4 발견·투영·보고 | Host/WebDiag의 hints/Candidate 전달과 이벤트·조회, Judge/Report 경계. 실제 소비 경계마다 별도 PR로 분할 | Host/Knowledge와 Judge/Report fake 연결, app에서 한 경계씩 교체 | 각 제공자·소비자 |

C2를 위해 C3/C4의 전체 도메인을 먼저 정의하지 않는다. 아직 없는 capture 서비스 등은 실제 연동 전 해당 소계약을 병합한다. C2만으로 전체 Gateway/Evidence 연동이나 S1이 완료된 것으로 표시하지 않는다. 후속 단계의 내부 로직은 필요한 계약 준비와 병행할 수 있다. C3·C4의 gateway/judge 소유 경계(capture·Judge)는 [C3·C4 최소 계약 초안](c3-c4-contract-draft.md)에서 병렬로 제안한다.

RunRegistration은 **app 소유의 내부 등록 집계 타입**으로 `app/src/abc2lab_app/registration.py`에 둘 예정이다. 각 서비스에는 필요한 불변 snapshot·설정만 주입하며 서비스가 app 타입을 import하지 않는다. C1의 `packages/contracts/src/abc2lab_contracts/fingerprint.py`는 이미 구현됐다. 서비스 간 실제 교환하는 C2 snapshot/요청/반환/Protocol과 업무별 fingerprint adapter는 `packages/contracts/src/abc2lab_contracts/`에 경계별로 추가할 예정이며, 아직 존재하는 것으로 가정하지 않는다.

## 2. 병렬 개발의 고정 책임

- Host: run/task/case ID, 작업·중복·취소, 후보 등록/조회/revision 검사와 모든 Projection 제출.
- WebDiag: 단서 반환, 인증·세션 상태, 모든 논리 HTTP request_ref 발급과 관찰/교차 실행 조정. Knowledge 포트를 받지 않음.
- Gateway/Policy: 실제 요청·현재 세션·등록 정책 독립 재검증, 같은 codec의 view fingerprint, 전송 직전 예산·상태 원자 검사.
- 각 원본 producer: 자기 journal과 불변 Projection 이벤트. Host는 다른 producer의 receipt·내용을 생성하거나 수정하지 않음.
- Evidence/Report: 근거·요청 레시피·PoC 절차와 누락 사유 보존. 보고서 생성이 추가 대상 요청을 보내지 않음.

27포트의 명시적 목록은 [상세 규격 §3.1](s1-api-spec.md#31-s1-포트-수-대조), 전송 직전 세션 재조회와 감사는 [§10](s1-api-spec.md#10-감사-커밋과-조회), 새로운 검증 사례 S1-37~42는 [§11](s1-api-spec.md#11-초기-한도-사유-코드와-개발-사례)을 따른다. 현재 사례는 후속 테스트 요구사항이다.

## 3. C1 구현 확인과 재검증

C1 코드는 PR #15로 이미 병합됐다. 이번 확인에서는 [codec 구현](../../packages/contracts/src/abc2lab_contracts/fingerprint.py)과 [테스트](../../packages/contracts/tests/test_fingerprint.py)를 [공유 codec 계약](fingerprint-contract.md)·정적 벡터와 대조했다. API 사용 방법과 시각 경계의 현재 한계는 [공개 API 절](fingerprint-contract.md#22-c1-공개-api와-사용)에 기록한다.

| 확인 범위 | C1에서 확인하는 것 | 남아 있는 범위 |
|---|---|---|
| 정규 바이트 | `primitive-v1` 정확한 UTF-8 bytes·테스트 내 SHA-256, 중첩 키 정렬·tuple 순서·null/생략 구분·UTC 정규화 | 업무 record별 typed wrapper·payload adapter와 운영 벡터 5개는 C2 |
| 불변 snapshot | 원본 dict·mapping proxy와 참조 분리, 중복 키·순환 입력·가변 값 거부 | 호출자가 snapshot 생성 중 일관된 입력을 제공해야 함 |
| 입력 거부 | float·NaN·Infinity·list·set·bytes·Decimal·naive datetime·비문자 key·미등록 dataclass/enum·lone surrogate 거부 | 업무별 필드 allowlist·지원 schema/type 검사와 시각 허용 범위는 C2 |
| 운영 경계 | 빈 고정 registry가 demo·미등록 운영 record를 거부 | 실행 타입·Protocol·운영 fingerprint 발행·Policy/Gateway fake·S1-01~42 행동 검증은 미구현 |

재검증 명령은 다음과 같다. 실제 대상·브라우저·DB 없이 Ruff lint/format, mypy와 contracts 테스트를 격리 실행한다.

```bash
uv run --no-project --python 3.13.15 scripts/dev.py check contracts
```

2026-10-21 재검증 결과: Ruff lint/format 통과, mypy 4개 파일 통과, contracts 테스트 **36개 통과**(fingerprint 35개·패키지 smoke 1개). Import Linter도 **6개 경계 유지·위반 0개**였다. 사용 예시를 실제 실행했고, 정적 문서 검사에서 로컬 링크/anchor·JSON 예시·27개 포트 목록·42개 예정 case ID와 고정 벡터 6개의 bytes/SHA-256 일치를 확인했다. 운영 벡터 5개의 정적 일치는 C2 typed adapter 테스트 통과로 집계하지 않는다.

독립 코드 검토와 아키텍처 검토에서 C1의 필수 수정 사항은 없었다. 시각 극단값의 `OverflowError`는 현재 한계로 기록했으며, C2 등록 전에 필요한 타입·버전·필드 검사는 [운영 계약 경계](fingerprint-contract.md#21-정규-바이트와-운영-계약-검증의-분리)에 명시했다. 이 구현 검토 기록은 팀원별 PR 승인 기록과 구분한다.

문서·고정 벡터의 정적 일치 확인은 위 codec 테스트와 구분한다. 현재 테스트의 성공이 S1 서비스 실행·인가·감사 내구성·실제 취약점 진단 완료를 의미하지 않는다.
