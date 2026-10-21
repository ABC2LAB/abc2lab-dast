# 모듈별 개발 가이드

팀원은 아래 배정에 따라 여러 패키지를 맡되 각 패키지의 책임·의존 경계를 유지한다. 리뷰 요청은 계속 팀원 전체에게 보내며, 스키마 변경의 필수 승인은 [계약·영향 담당자별 승인 기준](../CONTRIBUTING.md#스키마공통-규칙-변경의-승인)을 따른다.

## 담당 배정

| 담당자 | 담당 범위 | 작업 묶음 | 계획 비중 |
|---|---|---|---|
| 이동찬 (관리자·PM) | `contracts`·`app`·`knowledge`·루트 `eval/` | 공유 계약·조립·KG·평가·관리 | 약 34% |
| 최민준 | `gateway`·`judge`·`policy`·`report` | verifier·실행 관문·통제 결정·보고 | 약 33% |
| 이경준 | `webdiag`·`host`·`evidence`, P2의 `reasoner` | 관찰·생성·오케스트레이션·근거 | 약 33% |

비중은 팀의 작업 계획 추정치이며 측정된 구현량이 아니다. `reasoner`는 이경준의 P2 범위로 두며 P1 기본 경로에 필수로 넣지 않는다. `mcp-knowledge`·`mcp-webdiag`는 이번 배정에 포함되지 않았으므로 P2 착수 시 담당자를 별도 확정한다.

`eval/`은 이동찬이 소유하는 루트의 평가 전용 작업 영역이다. uv 패키지가 아니며 현재는 [담당 범위 안내](../eval/README.md)만 있다. 평가 하네스·데이터·테스트는 후속 구현 대상이다. 평가 격리를 위해 판정(`judge`) 담당과 분리해 둔다.

## 담당 재배정 (2026-10-21)

윤재상 이탈로 `evidence`·`report`·루트 `eval/`을 남은 세 명이 나눠 맡는다.

| 모듈 | 이전 | 이후 | 기준 |
|---|---|---|---|
| `evidence` | 윤재상 | **이경준** | `judge` 담당(최민준)과 다른 소유자에 둬서 Judge가 Evidence를 독립 재검증하는 신뢰 경계를 유지한다. 이경준의 `webdiag`(비교)·`host`(투영)가 이미 Evidence와 맞닿아 있다 |
| `report` | 윤재상 | **최민준** | Report는 Verdict의 다운스트림 표현이라 판정 담당이 맡아도 탐지·평가 독립성에 영향이 없다. Report는 전송·판정을 하지 않는다 |
| 루트 `eval/` | 윤재상 | **이동찬** | GT 격리상 판정(`judge`) 담당과 분리한다. 탐지 경로 밖이며 조립자(`app`)·계약(`contracts`) 담당이 주입 경계를 집행하기 좋다 |

- 유지할 경계: 이동찬이 `knowledge`(판정 추론 입력)와 `eval/`(GT)을 함께 맡으므로, 제품의 발견·추론·판정 경로가 GT·`eval/`을 입력·정답 단서로 읽지 않도록 코드 격리를 유지한다. `judge` 테스트의 평가 fixture 사용은 테스트 전용으로 허용한다.
- 승인 절차: 팀이 3명이 되어 스키마·공통 규칙 변경의 담당자별 승인은 남은 담당 전원(작성자 제외)을 기준으로 한다. [리뷰 승인 Bypass](../CONTRIBUTING.md#리뷰-승인-bypass) 허용 계정에서 `jsang01`은 이미 제외돼 있다. `.github/CODEOWNERS`에서 `@jsang01`을 뺀다.
- 인계: 기존 계약·설계 문서(`s1-api-draft.md`·`poc-report-design.md`·`s1-development-status.md`·`c3-c4-contract-draft.md`)에 남은 윤재상 리뷰·경계 참여는 새 소유자로 승계하며(evidence→이경준, report→최민준, eval→이동찬), 각 문서는 해당 계약 PR에서 갱신한다.
- 각자 개인 하네스(status/plan/CLAUDE)는 이 배정으로 갱신한다.

## 모듈과 패키지

| 모듈 | uv 패키지 | 책임 |
|---|---|---|
| contracts | `abc2lab-contracts` | 공유 타입·Port Protocol·명시적 fingerprint 순수 codec; stdlib-only 의존성 leaf |
| host | `abc2lab-host` | Controller, Scheduler, Planner, Broker와 Task 상태 |
| knowledge | `abc2lab-knowledge` | 후보·관찰 그래프, Projector, Knowledge 저장/조회 |
| evidence | `abc2lab-evidence` | 실행영역 캡처·비교와 민감값 제거 Evidence 저장/조회 |
| webdiag | `abc2lab-webdiag` | Discovery, Observe, Access Compare, Auth 흐름 |
| policy | `abc2lab-policy` | 구체 실행 계획에 대한 Safety Policy 판정 |
| gateway | `abc2lab-gateway` | 유일한 대상 HTTP/브라우저 실행 관문과 Vault |
| judge | `abc2lab-judge` | 유형별 oracle과 독립 판정 |
| reasoner | `abc2lab-reasoner` | Context, Model Adapter, 제안형 추론(P2·이경준) |
| report | `abc2lab-report` | 결과와 감사 타임라인 보고 |
| mcp-knowledge | `abc2lab-mcp-knowledge` | KnowledgePort의 얇은 MCP 어댑터(P2·담당 미정) |
| mcp-webdiag | `abc2lab-mcp-webdiag` | WebDiagPort의 얇은 MCP 어댑터(P2·담당 미정) |
| app | `abc2lab-app` | 조립 루트와 의존성 주입; 구체 구현 선택 |

## 패키지별 작업

```bash
uv run --no-project --python 3.13.15 scripts/dev.py setup all
uv run --no-project --python 3.13.15 scripts/dev.py check knowledge
```

모든 팀원은 `setup all`로 공통 환경을 한 번 설치한다. 여러 모듈의 `setup`을 차례로 실행하면 공유 `.venv`에서 앞서 설치한 패키지가 제거될 수 있으므로 묶음 설치를 사용한다. `check`는 담당 모듈 디렉터리 이름을 받아 공유 환경을 바꾸지 않는 격리 환경에서 Ruff, mypy와 pytest를 실행한다. 팀원이 uv 옵션을 조합하거나 전체 워크스페이스를 직접 설정할 필요는 없다.

이동찬의 검사:

```bash
uv run --no-project --python 3.13.15 scripts/dev.py check contracts
uv run --no-project --python 3.13.15 scripts/dev.py check app
uv run --no-project --python 3.13.15 scripts/dev.py check knowledge
```

최민준의 검사:

```bash
uv run --no-project --python 3.13.15 scripts/dev.py check gateway
uv run --no-project --python 3.13.15 scripts/dev.py check judge
uv run --no-project --python 3.13.15 scripts/dev.py check policy
uv run --no-project --python 3.13.15 scripts/dev.py check report
```

이경준의 P1 검사:

```bash
uv run --no-project --python 3.13.15 scripts/dev.py check webdiag
uv run --no-project --python 3.13.15 scripts/dev.py check host
uv run --no-project --python 3.13.15 scripts/dev.py check evidence
```

P2의 `reasoner` 작업에는 같은 명령의 `check reasoner`를 추가한다.

`eval/`의 실행·검증 명령은 평가 하네스 구현 PR에서 의존성·CI 경로와 함께 정의한다. 현재 `scripts/dev.py check eval`이나 기본 pytest가 평가 테스트까지 검증한다고 보지 않는다.

CI의 모듈별 격리 검사는 선택된 패키지의 모든 extra를 설치해 해당 어댑터 SDK도 검사한다. 서버나 브라우저 프로세스를 기동하는 설정은 아니다. `app`은 조립 루트이므로 선택한 서비스 구현에 의존하지만, 서비스 모듈은 다른 서비스 구현 없이 `contracts`와 자기 외부 라이브러리만 사용한다.

전체 검사는 루트에서 실행한다.

```bash
uv run --no-project --python 3.13.15 scripts/dev.py check all
```

## 계약과 경계

S1 병렬 개발은 [API 흐름·담당·로컬 fake 사례](planning/s1-api-draft.md)와 [API 상세 규격 v0.5](planning/s1-api-spec.md)를 팀 리뷰 자료로 사용한다. I/O 서비스 포트는 async def로 정의하고 소비자는 await한다. 정책 조건·오라클·정규화의 순수 로직, 세션 메모리 snapshot 조회·캡처 인계/해제는 동기다. Host는 유한 큐·worker 1개로 시작하며 순서·취소·동시성 상한은 [비동기 실행 계약](planning/s1-api-spec.md#22-비동기-호출과-작업-실행)을 따른다.

로컬 fake도 포트의 async/def를 일치시키고, pytest-asyncio strict 설정에서 `@pytest.mark.asyncio`로 검사한다. Event·fake clock으로 지연·취소·경합을 재현하며 Task/캡처/lease가 남지 않는지 확인한다. 상세 규격의 필수 필드·반환 상태·수명·감사 확인 포트와 S1-01~28 수용 사례는 후속 구현 대상이다. 제공자와 소비자는 자기 입력이 충분한지, 출력을 독립적으로 만들 수 있는지, 실패를 fake로 재현할 수 있는지 더블 체크한다. 실제 소비 경계부터 작은 계약 PR로 확정한다.

[PoC 보고서 계약](planning/poc-report-design.md)은 Gateway의 실제 요청 최소 view → 로컬 Evidence의 등록 레시피/근거 저장 → Report의 재현 절차로 연결한다. S1-29~36에서 민감값 치환·요청 바인딩·무전송 보고·부분/취소 상태를 검증한다. [예시 보고서](examples/s1-poc-report.example.md)는 미실행 가상 문서이며 제품 입력이나 실제 진단 근거가 아니다. Report는 다른 모듈 DB나 Gateway 실행 포트를 직접 사용하지 않는다.

`contracts`에는 [PR #15](https://github.com/ABC2LAB/abc2lab-dast/pull/15)로 C1의 `canonical-json.v1` codec과 불변 스냅샷·저수준 벡터 테스트가 구현됐다. 공통 실행 타입·Protocol과 업무별 fingerprint adapter는 아직 C2 구현 대상이다. 의존 모듈에서 임의 schema나 `Any` placeholder, 서비스별 codec 사본을 만들지 말고 필요한 최소 공개 계약을 PR로 제안한다. 구현 모듈의 독립 테스트는 확정된 공개 포트를 구현하는 로컬 fake를 사용한다.

C1의 import 경로와 snapshot 생성 예시는 [공개 API와 사용](planning/fingerprint-contract.md#22-c1-공개-api와-사용), 구현과 테스트의 확인 범위는 [C1 재검증](planning/s1-development-status.md#3-c1-구현-확인과-재검증)을 따른다. C1 통과를 업무 record의 운영 fingerprint 검증이나 S1 실행 수용 사례 통과로 집계하지 않는다.

[착수 상태·선행조건](planning/s1-development-status.md)에 따라 CLOSED/unmerged PR #8 대신 **C1 병합 완료 → C2 실행 경계 계약 구현·병합 대기** 상태로 진행한다. Policy/Gateway 공개 fake는 C2 병합 뒤 연결하며 내부 순수 로직은 먼저 시험할 수 있다. [공유 codec](planning/fingerprint-contract.md)은 모든 모듈이 같은 C1 구현을 재사용한다. 문서 판번호와 policy_input.v1은 별개다. RunRegistration은 app 내부 집계이며 각 서비스에는 필요한 snapshot만 주입한다.

Host는 Knowledge 등록/조회/투영과 run/task/case ID를, WebDiag는 인증·whoami·복구·기준/교차 request_ref 발급을 맡는다. WebDiag에는 Knowledge 포트를 주입하지 않고 Host가 조회한 Candidate 값을 전달한다. 추가 수용 사례 S1-37~42는 codec·identity 매핑·투영 호출자·ID·등록 재검증·전송 직전 세션/예산 검사를 다룬다. 팀원의 개인 status.md/plan.md에도 새 계약 PR 선행조건을 적용한다.

`gateway`만 대상에 통신하고, 각 서비스의 저장 어댑터만 자기 정본 DB에 접근한다. `mcp-*`는 포트를 감싸는 얇은 어댑터다. `app`이 조립하며, 서비스가 다른 서비스의 구체 구현을 직접 생성하지 않는다. 실제 PostgreSQL+AGE, 브라우저 바이너리, MCP 서버는 해당 어댑터의 통합 테스트를 시작하기 전에 준비한다.

코어 테스트는 외부 네트워크·브라우저·DB 없이 실행한다. 기본 pytest는 `integration` marker가 붙은 테스트를 제외한다. 실제 환경을 준비한 뒤 `pytest -m integration`으로 실행한다. 통합 테스트는 별도 환경을 사용하며 비밀값·원문 응답·캡처 핸들·GT를 출력하지 않는다. 자세한 설계 의미는 [확정 모듈 설계](planning/module-design-confirmed.md), 공통 환경은 [개발 환경 안내](development.md)를 참조한다.

[공통 작업 규칙](../CONTRIBUTING.md)과 CI는 작업 범위·의존 방향을 안내하고 검사한다. 개인 AI 하네스는 각자 로컬에서 유지하며 저장소에는 포함하지 않는다. GitHub에서 사용자별로 특정 디렉터리의 파일 수정 자체를 차단하는 설정은 아니다. 모듈 담당 배정과 별개로 `.github/CODEOWNERS`가 모든 변경의 리뷰를 팀원 전체에 요청한다. 일반 PR은 작성자 외 1명 승인·필수 CI 통과, 스키마·공통 규칙 변경은 CONTRIBUTING.md의 추가 승인 기준을 적용한다.
