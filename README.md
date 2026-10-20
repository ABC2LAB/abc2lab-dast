# abc2lab-dast

ABC2LAB DAST의 uv 멀티패키지 개발 워크스페이스입니다. 현재는 환경과 패키지 골격을 구성한 단계이며 진단 기능은 아직 구현되지 않았습니다.

## 개발 시작

Python 3.13.15와 uv 0.12.23을 사용합니다.

```bash
uv python install
uv sync --locked --all-packages
uv run --locked --all-packages pytest
```

설치, 선택 의존성, 브라우저 설치와 공통 검사는 [개발 환경 안내](docs/development.md)를 따릅니다.

## 팀원 온보딩

저장소를 내려받은 뒤 담당 모듈만 선택해 설치·검증합니다. 담당 모듈은 회의에서 정한 뒤 모듈명과 패키지명을 1:1로 기록하세요.

```bash
git clone https://github.com/ABC2LAB/abc2lab-dast.git
cd abc2lab-dast
uv python install
uv sync --locked --package abc2lab-knowledge --group dev
uv run --locked --package abc2lab-knowledge --group dev pytest packages/knowledge/tests
```

`knowledge`는 예시입니다. 모듈별 경로와 명령은 [모듈 개발 가이드](docs/module-development.md)를 사용합니다. 작업 범위, 의존성 변경, PR 작성 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 읽고 시작하세요. AI 도구를 사용할 때는 저장소 루트의 [AGENTS.md](AGENTS.md)를 적용합니다.

팀 공지 예시:

> ABC2LAB DAST 저장소에서 담당 모듈을 독립적으로 개발합니다. 먼저 `uv python install`과 `uv sync --locked --package <패키지명> --group dev`를 실행하고, 변경은 `packages/<모듈>/src`와 `packages/<모듈>/tests` 중심으로 올려 주세요. 전체 구조·계약 변경이나 다른 모듈 수정이 필요하면 먼저 해당 담당자와 협의하고 별도 PR로 분리합니다. 시작 전 [모듈 개발 가이드](docs/module-development.md)와 [기여 안내](CONTRIBUTING.md)를 확인해 주세요.

## 설계 기준

- [아키텍처](docs/planning/mcp-architecture.md)
- [도구 카탈로그](docs/planning/mcp-tool-catalog.md)
- [모듈 설계](docs/planning/module-design-confirmed.md)

`packages/`는 공개 계약과 서비스 패키지, `app/`은 조립 루트입니다. 모듈 담당자는 팀 회의 후 정합니다.
