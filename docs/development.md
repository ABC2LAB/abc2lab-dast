# 개발 환경과 의존성

## 공통 버전

- CPython 3.13.15: `.python-version`으로 고정한다. 각 패키지는 Python 3.13 계열을 대상으로 한다.
- uv 0.12.23: 루트 `tool.uv.required-version`으로 확인한다. 설치는 [공식 설치 문서](https://docs.astral.sh/uv/getting-started/installation/)의 버전 지정 방법을 따른다.
- 빌드 백엔드는 `uv_build>=0.12.23,<0.13`을 사용한다. uv의 같은 버전에 포함된 백엔드를 사용하며 다른 프런트엔드에서는 해당 범위의 백엔드를 설치한다.
- 정확한 런타임/개발 의존성은 루트 `uv.lock`에 기록한다.

## 최초 설치

저장소 루트에서 실행한다.

```bash
uv python install
uv sync --locked --all-packages
```

루트 개발 그룹에 pytest, pytest-asyncio, pytest-cov, Ruff, mypy, Import Linter를 둔다. 가상환경과 캐시는 커밋하지 않는다. 패키지는 editable로 설치되므로 소스 수정 뒤 재설치할 필요가 없다.

## 의존성 배치

| 영역 | 기본 의존성 | 선택 의존성 |
| --- | --- | --- |
| contracts | 표준 라이브러리만 | 없음 |
| host / knowledge / evidence / policy / judge / report | contracts | 각 패키지의 `postgres` extra |
| gateway | contracts, HTTPX, Playwright | `postgres` extra |
| webdiag | contracts | 없음 |
| reasoner | contracts | 모델 공급자/런타임은 후속 선정 |
| mcp-knowledge / mcp-webdiag | contracts | `server` extra의 MCP Python SDK |
| app | contracts와 초기 서비스 패키지 | `postgres`, `mcp`, `reasoner` |

`app`이 실제 서비스 구현을 조립한다. 서비스 간 호출 포트는 `contracts`에 두며 다른 서비스 구현 패키지에는 의존하지 않는다. `mcp-*`도 주입받은 포트를 감싸므로 서비스 구현에 의존하지 않는다.

PostgreSQL 드라이버는 Psycopg 3의 `binary,pool` extras를 사용한다. 개발 환경 설치 편의를 위한 선택이며 운영의 libpq 공급 방식은 배포 시 검증한다. 각 서비스는 자기 저장 어댑터에서 자기 역할/스키마로 접속한다. AGE는 PostgreSQL 확장이므로 별도 Python 그래프 DB SDK를 추가하지 않는다. AGE 접속/질의는 knowledge 어댑터가 소유한다. 서버 역할과 스키마 권한은 드라이버 설치로 설정되지 않는다.

## 선택 기능 설치

```bash
# PostgreSQL 어댑터 개발용 드라이버
uv sync --locked --all-packages --extra postgres

# Phase 2 MCP 어댑터 개발용 SDK
uv sync --locked --all-packages --extra mcp

# 모든 선언된 선택 의존성까지 설치
uv sync --locked --all-packages --all-extras
```

선택 의존성이 필요한 명령에는 동일한 `--extra` 또는 `--all-extras`를 전달한다. 예: `uv run --locked --all-packages --extra postgres python -c "import psycopg"`. 기본 명령을 다시 실행하면 선택 의존성이 제거될 수 있다.

PostgreSQL+AGE 서버/이미지 digest, ZAP/Nuclei 실행 파일과 검토 템플릿, 모델 공급자 SDK/가중치, UI 및 target-app 프레임워크는 이 의존성 설정에서 임의로 정하지 않는다. 설계의 해당 통합 단계에서 검증하고 고정한다. 설계 문서에 기록된 PG16/AGE1.6.0 PoC를 최종 배포 조합으로 취급하지 않는다.

## Playwright 브라우저

Python 패키지와 브라우저 바이너리는 별도 설치다. 기본 테스트는 브라우저 프로세스와 실제 대상 통신을 사용하지 않는다.

```bash
cp .env.example .env
uv run --locked --all-packages --env-file .env playwright install chromium
```

Linux에서 OS 라이브러리가 없으면 Playwright 공식 시스템 요구사항에 맞춰 설치한다. 시스템 패키지 설치는 이 저장소의 Python 의존성 설치에 포함되지 않는다. 브라우저 캐시는 `.cache/ms-playwright`에 두고 해당 명령/실행에서도 `--env-file .env`를 사용한다.

## 공통 검사

```bash
uv lock --check
uv run --locked --all-packages ruff check .
uv run --locked --all-packages ruff format --check .
uv run --locked --all-packages mypy
uv run --locked --all-packages lint-imports
uv run --locked --all-packages pytest
uv build --all-packages
```

기본 pytest는 `integration` marker 테스트를 제외한다. 실제 서비스를 준비한 통합 검증에서는 `pytest -m integration`을 사용한다.

단일 모듈은 `uv run --locked --package abc2lab-knowledge pytest packages/knowledge/tests`처럼 실행한다. 전체 워크스페이스 환경의 성공만으로 패키지 독립 설치를 증명할 수 없으므로, 패키지 배포/어댑터 구현 시 격리된 환경에서 해당 wheel과 선언된 의존성만 설치해 확인한다.

uv 워크스페이스는 하나의 가상환경을 공유한다. 선언되지 않은 import를 uv 자체가 차단하지 않으므로 Import Linter로 서비스 독립성, contracts 최하단, HTTP/브라우저의 gateway 한정, 코어 I/O 금지와 MCP 어댑터 경계를 검사한다. 이 정적 검사는 실제 프로세스/네트워크/DB 권한 격리를 대신하지 않는다.

## 의존성 변경

패키지 런타임 의존성은 해당 패키지에 추가한다. 공통 개발 도구는 루트에만 추가한다.

```bash
uv add --package abc2lab-gateway 'httpx>=0.28.1,<0.29'
uv add --dev pytest
```

변경한 `pyproject.toml`과 `uv.lock`을 같은 PR로 올린다. 의도적인 업그레이드에만 `uv lock --upgrade-package <이름>`을 사용한다. 팀원별 `pip install`로 환경을 따로 수정하지 않는다.

모듈별 작업 절차는 [모듈 개발 가이드](module-development.md)를 따른다. 모듈 담당자는 회의 후 정한다. 현재 설정에는 담당자와 CODEOWNERS를 넣지 않는다.

## 공식 근거

- [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)
- [uv build backend](https://docs.astral.sh/uv/concepts/build-backend/)
- [uv required-version](https://docs.astral.sh/uv/reference/settings/#required-version)
- [Playwright Python 설치](https://playwright.dev/python/docs/intro)
- [Psycopg 설치](https://www.psycopg.org/psycopg3/docs/basic/install.html)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Import Linter](https://import-linter.readthedocs.io/en/stable/)
