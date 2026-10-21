# S1 착수 상태와 계약 PR 순서

확인 기준: 2026-10-21, [API 상세 규격 v0.5](s1-api-spec.md) 팀 리뷰 반영 시점. 이 문서는 구현 완료나 실제 전송 허가를 선언하지 않는다. 각 팀원의 개인 status.md/plan.md/CLAUDE.md는 이 저장소에 없으므로 여기서 수정하지 않는다. 개인 계획의 선행조건도 아래 기준으로 갱신한다.

## 0. 현재 선행조건

| 항목 | 확인한 상태 | 개발에 미치는 영향 |
|---|---|---|
| [PR #8](https://github.com/ABC2LAB/abc2lab-dast/pull/8) | CLOSED, 병합되지 않음 | 기존 실행 관문 타입은 제공되지 않는다. #8 병합을 대기하거나 해당 브랜치를 복원하지 않는다 |
| [PR #9](https://github.com/ABC2LAB/abc2lab-dast/pull/9) | MERGED, 문서 변경 | v0.3 설계가 main에 들어갔으며 타입·Protocol·fake 구현은 없음 |
| [PR #10](https://github.com/ABC2LAB/abc2lab-dast/pull/10) | MERGED, PoC·팀 리뷰 설계 보완 | v0.5 문서·미실행 예시·정적 벡터가 main에 반영됨. 자동 생성기·공유 codec 구현 완료가 아님 |
| contracts 패키지 | 구현 대기 scaffold | 새 계약 PR의 병합 전에는 공개 타입이 있다고 가정하지 않음 |

Policy/Gateway 공개 포트와 그 fake의 선행조건은 **새 C1·C2 계약 PR의 병합**이다. “PR #8 병합 선행”이라는 개인 계획은 이 조건으로 교체한다. 조건/정규화/예산 등 모듈 내부 순수 로직은 먼저 구현·시험할 수 있다. 공개 계약 대신 임의 Any·dict·서비스별 타입 사본을 만들지 않는다.

## 1. 작은 계약 PR로 다시 시작

| 단계 | 이동찬의 제안 범위 | 병합 후 가능한 작업 | 관련 리뷰 |
|---|---|---|---|
| C1 fingerprint codec | [정규 바이트·envelope·버전 규칙](fingerprint-contract.md), stdlib-only 순수 codec과 고정 벡터 테스트. 타입별 adapter는 해당 타입 PR에서 추가 | 모든 모듈이 같은 codec을 재사용. fake codec/모듈별 직렬화 제거 | 최민준·윤재상·이경준 |
| C2 실행 경계 | 공통 Ref/RunKey/SourceVersion/상태, PolicyInput/Decision 및 필요한 등록·세션 snapshot, prepare/evaluate/execute·세션 읽기·commit 검증의 최소 Protocol. 비밀 없는 identity/request_intent/attempt 감사 payload·adapter·고정 벡터 포함 | Policy/Gateway가 실제 contracts를 사용하는 무전송 fake로 개발·검증 | 최민준·이경준·윤재상 |
| C3 로컬 Evidence | capture/seal/compare·캡처 수명·민감값 제거 근거·ComparisonProjected와 저장 receipt, PoC 요청 레시피 | Gateway의 캡처 인계, WebDiag 비교, Evidence 독립 테스트 연결 | 윤재상·최민준·이경준 |
| C4 발견·투영·보고 | Host/WebDiag의 hints/Candidate 전달과 이벤트·조회, Judge/Report 경계. 실제 소비 경계마다 별도 PR로 분할 | Host/Knowledge와 Judge/Report fake 연결, app에서 한 경계씩 교체 | 각 제공자·소비자 |

C2를 위해 C3/C4의 전체 도메인을 먼저 정의하지 않는다. 아직 없는 capture 서비스 등은 실제 연동 전 해당 소계약을 병합한다. C2만으로 전체 Gateway/Evidence 연동이나 S1이 완료된 것으로 표시하지 않는다. 후속 단계의 내부 로직은 필요한 계약 준비와 병행할 수 있다.

RunRegistration은 **app 소유의 내부 등록 집계 타입**으로 `app/src/abc2lab_app/registration.py`에 둘 예정이다. 각 서비스에는 필요한 불변 snapshot·설정만 주입하며 서비스가 app 타입을 import하지 않는다. 서비스 간 실제 교환하는 snapshot/요청/반환/Protocol과 fingerprint adapter는 `packages/contracts/src/abc2lab_contracts/`에 경계별로 둔다. 경로는 구현 예정이며 현재 파일이 존재하거나 타입이 구현됐다는 뜻이 아니다.

## 2. 병렬 개발의 고정 책임

- Host: run/task/case ID, 작업·중복·취소, 후보 등록/조회/revision 검사와 모든 Projection 제출.
- WebDiag: 단서 반환, 인증·세션 상태, 모든 논리 HTTP request_ref 발급과 관찰/교차 실행 조정. Knowledge 포트를 받지 않음.
- Gateway/Policy: 실제 요청·현재 세션·등록 정책 독립 재검증, 같은 codec의 view fingerprint, 전송 직전 예산·상태 원자 검사.
- 각 원본 producer: 자기 journal과 불변 Projection 이벤트. Host는 다른 producer의 receipt·내용을 생성하거나 수정하지 않음.
- Evidence/Report: 근거·요청 레시피·PoC 절차와 누락 사유 보존. 보고서 생성이 추가 대상 요청을 보내지 않음.

27포트의 명시적 목록은 [상세 규격 §3.1](s1-api-spec.md#31-s1-포트-수-대조), 전송 직전 세션 재조회와 감사는 [§10](s1-api-spec.md#10-감사-커밋과-조회), 새로운 검증 사례 S1-37~42는 [§11](s1-api-spec.md#11-초기-한도-사유-코드와-개발-사례)을 따른다. 현재 사례는 후속 테스트 요구사항이다.
