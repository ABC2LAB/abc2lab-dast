# 모듈별 개발 가이드

팀원은 아래 배정에 따라 여러 패키지를 맡되 각 패키지의 책임·의존 경계를 유지한다. 개발 담당과 PR 리뷰 요청 대상은 별개이며, 리뷰는 계속 팀원 전체에게 요청한다.

## 담당 배정

| 담당자 | 담당 범위 | 작업 묶음 | 계획 비중 |
|---|---|---|---|
| 이동찬 (관리자·PM) | `contracts`·`app`·`knowledge` | 공유 계약·조립·KG·관리 | 약 27% |
| 최민준 | `gateway`·`judge`·`policy` | verifier·실행 관문·통제 결정 | 약 26% |
| 이경준 | `webdiag`·`host`, P2의 `reasoner` | 관찰·생성·오케스트레이션 | 약 24% |
| 윤재상 | `evidence`·`report`·루트 `eval/` | 근거·보고·평가 | 약 23% |

비중은 팀의 작업 계획 추정치이며 측정된 구현량이 아니다. `reasoner`는 이경준의 P2 범위로 두며 P1 기본 경로에 필수로 넣지 않는다. `mcp-knowledge`·`mcp-webdiag`는 이번 배정에 포함되지 않았으므로 P2 착수 시 담당자를 별도 확정한다.

`eval/`은 윤재상이 소유하는 루트의 평가 전용 작업 영역이다. uv 패키지가 아니며 현재는 [담당 범위 안내](../eval/README.md)만 있다. 평가 하네스·데이터·테스트는 후속 구현 대상이다.

## 모듈과 패키지

| 모듈 | uv 패키지 | 책임 |
|---|---|---|
| contracts | `abc2lab-contracts` | 공유 타입과 공개 Port Protocol; 의존성 leaf |
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
```

이경준의 P1 검사:

```bash
uv run --no-project --python 3.13.15 scripts/dev.py check webdiag
uv run --no-project --python 3.13.15 scripts/dev.py check host
```

P2의 `reasoner` 작업에는 같은 명령의 `check reasoner`를 추가한다.

윤재상의 검사:

```bash
uv run --no-project --python 3.13.15 scripts/dev.py check evidence
uv run --no-project --python 3.13.15 scripts/dev.py check report
```

`eval/`의 실행·검증 명령은 평가 하네스 구현 PR에서 의존성·CI 경로와 함께 정의한다. 현재 `scripts/dev.py check eval`이나 기본 pytest가 평가 테스트까지 검증한다고 보지 않는다.

CI의 모듈별 격리 검사는 선택된 패키지의 모든 extra를 설치해 해당 어댑터 SDK도 검사한다. 서버나 브라우저 프로세스를 기동하는 설정은 아니다. `app`은 조립 루트이므로 선택한 서비스 구현에 의존하지만, 서비스 모듈은 다른 서비스 구현 없이 `contracts`와 자기 외부 라이브러리만 사용한다.

전체 검사는 루트에서 실행한다.

```bash
uv run --no-project --python 3.13.15 scripts/dev.py check all
```

## 계약과 경계

초기 환경 구성 시점의 `contracts`에는 공개 타입/Protocol이 아직 구현되지 않았다. 의존 모듈 구현을 먼저 시작하면서 임의 schema나 `Any` placeholder를 만들지 말고, 필요한 최소 계약을 `contracts` PR로 제안한다. 구현 모듈의 독립 테스트는 그 공개 포트를 구현하는 로컬 fake를 사용한다.

`gateway`만 대상에 통신하고, 각 서비스의 저장 어댑터만 자기 정본 DB에 접근한다. `mcp-*`는 포트를 감싸는 얇은 어댑터다. `app`이 조립하며, 서비스가 다른 서비스의 구체 구현을 직접 생성하지 않는다. 실제 PostgreSQL+AGE, 브라우저 바이너리, MCP 서버는 해당 어댑터의 통합 테스트를 시작하기 전에 준비한다.

코어 테스트는 외부 네트워크·브라우저·DB 없이 실행한다. 기본 pytest는 `integration` marker가 붙은 테스트를 제외한다. 실제 환경을 준비한 뒤 `pytest -m integration`으로 실행한다. 통합 테스트는 별도 환경을 사용하며 비밀값·원문 응답·캡처 핸들·GT를 출력하지 않는다. 자세한 설계 의미는 [확정 모듈 설계](planning/module-design-confirmed.md), 공통 환경은 [개발 환경 안내](development.md)를 참조한다.

[공통 작업 규칙](../CONTRIBUTING.md)과 CI는 작업 범위·의존 방향을 안내하고 검사한다. 개인 AI 하네스는 각자 로컬에서 유지하며 저장소에는 포함하지 않는다. GitHub에서 사용자별로 특정 디렉터리의 파일 수정 자체를 차단하는 설정은 아니다. 모듈 담당 배정과 별개로 `.github/CODEOWNERS`가 모든 변경의 리뷰를 팀원 전체에 요청한다. 작성자를 제외한 팀원 1명의 승인과 필수 CI 통과가 병합 기준이다.
