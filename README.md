# abc2lab-dast

ABC2LAB DAST의 uv 멀티패키지 개발 워크스페이스입니다. C1 결정적 fingerprint codec([PR #15](https://github.com/ABC2LAB/abc2lab-dast/pull/15)), C2 실행 경계([PR #20](https://github.com/ABC2LAB/abc2lab-dast/pull/20)), C3 Evidence([PR #27](https://github.com/ABC2LAB/abc2lab-dast/pull/27)), C4-A Knowledge([PR #30](https://github.com/ABC2LAB/abc2lab-dast/pull/30)), C4-B Judge([PR #39](https://github.com/ABC2LAB/abc2lab-dast/pull/39))와 Host↔WebDiag([PR #38](https://github.com/ABC2LAB/abc2lab-dast/pull/38))의 공유 계약이 main에 병합됐습니다.

2026-10-22, `8f6fdd2` 기준으로 서비스는 일부 로컬 구현 단계입니다. WebDiag 세션 기반([PR #40](https://github.com/ABC2LAB/abc2lab-dast/pull/40))과 Judge 사유 코드 매핑([PR #41](https://github.com/ABC2LAB/abc2lab-dast/pull/41))도 반영됐지만, Host·Report 공개 계약과 실제 서비스 연결·HTTP/DB 통합은 남아 있습니다. 담당 배정은 [모듈 개발 가이드](docs/module-development.md#담당-배정), 구현 범위와 다음 작업은 [S1 착수 상태](docs/planning/s1-development-status.md#8-현재-서비스-구현과-남은-작업)를 따릅니다.

## 최종 제품 형태

최종 배포는 **`app`(웹 화면·API·진단 worker), `ollama`(로컬 모델), `db`(PostgreSQL+AGE)** 세 컨테이너를 Docker Compose로 기동하고 localhost에서 사용하는 로컬 웹을 목표로 합니다. 서비스별 패키지·책임 경계는 유지합니다. 상세 구성과 완료 기준은 [로컬 배포 설계](docs/planning/local-deployment.md)를 따릅니다.

현재는 서비스·계약 개발 단계이며 웹 UI/API·전체 조립·Dockerfile·Compose 설정은 구현 전입니다. 모듈 개발과 기본 테스트는 아래 uv 환경으로 진행합니다.

## 개발 시작

Python 3.13.15와 uv 0.12.23을 사용합니다.

최초 설치는 모든 팀원이 같은 명령을 사용합니다. 잠금된 의존성, 공통 개발 도구, 선택 extra, 커밋 훅과 기본 테스트를 한 번에 준비합니다. 작업 중에는 담당 모듈만 검사합니다.

```bash
uv run --no-project --python 3.13.15 scripts/dev.py setup all
uv run --no-project --python 3.13.15 scripts/dev.py check knowledge
```

여러 담당 패키지가 공유 `.venv`에 함께 설치되도록 `setup all`을 사용합니다. 최소 설치가 필요하면 `setup <모듈>`도 지원하지만, 다른 모듈의 설치 상태를 유지하지 않을 수 있습니다. `check all`은 PM 또는 CI와 같은 전체 검사가 필요할 때 사용합니다.

전체 환경과 통합 단계 의존성은 [개발 환경 안내](docs/development.md)를 따릅니다.

## 팀원 온보딩

저장소를 내려받은 뒤 공통 환경을 설치하고 [담당 배정표](docs/module-development.md#담당-배정)에 맞춰 모듈을 검사합니다.

```bash
git clone https://github.com/ABC2LAB/abc2lab-dast.git
cd abc2lab-dast
uv run --no-project --python 3.13.15 scripts/dev.py setup all
uv run --no-project --python 3.13.15 scripts/dev.py check knowledge
```

`knowledge`는 예시입니다. 모듈별 경로와 명령은 [모듈 개발 가이드](docs/module-development.md)를 사용합니다. 작업 범위, 브랜치·PR, 공통 코딩 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 읽고 시작하세요. 개인 AI 하네스인 루트 `AGENTS.md`는 각자 로컬에서 관리하며 Git 추적에서 제외합니다.

팀 공유 결정과 지침은 docs/ 또는 루트 Markdown 문서에 기록합니다. 내용별 기록 위치는 [공유 문서 작성 기준](CONTRIBUTING.md#공유-문서-작성)을 따릅니다.

팀 공지 예시:

> ABC2LAB DAST 저장소에서 배정된 모듈을 개발합니다. Git과 uv 0.12.23을 준비하고 `uv run --no-project --python 3.13.15 scripts/dev.py setup all`을 한 번 실행하세요. 작업 중에는 같은 명령의 `check <모듈>`로 본인 패키지만 검사합니다. 담당자별 범위와 검사 명령은 [모듈 개발 가이드](docs/module-development.md), PR 절차는 [기여 안내](CONTRIBUTING.md)를 따릅니다. 리뷰는 작성자를 제외한 팀원 모두에게 요청합니다. 일반 PR은 1명 승인과 필수 CI 통과, 스키마·공통 규칙 변경은 기여 안내의 추가 승인 기준을 적용합니다.

## 설계 기준

- [아키텍처](docs/planning/mcp-architecture.md)
- [도구 카탈로그](docs/planning/mcp-tool-catalog.md)
- [모듈 설계](docs/planning/module-design-confirmed.md)
- [S1 API 흐름·담당·개발 사례](docs/planning/s1-api-draft.md)
- [S1 API 상세 규격](docs/planning/s1-api-spec.md) — 비동기 I/O·공유 fingerprint·Host 투영 조정·PoC 보고서, 팀 리뷰 반영 중 설계안
- [S1 착수 상태·계약 PR 순서](docs/planning/s1-development-status.md) — C4-B까지의 계약 병합 이력, 현재 서비스 구현 범위와 남은 작업
- [fingerprint 계약·사용법](docs/planning/fingerprint-contract.md) — C1 정규 바이트와 C2 운영 record별 fingerprint, 저장 전·후 결과의 생성 순서
- [PoC 포함 보고서 설계](docs/planning/poc-report-design.md) · [미실행 가상 보고서 예시](docs/examples/s1-poc-report.example.md)

`packages/`는 공개 계약과 서비스 패키지, `app/`은 조립 루트, `eval/`은 평가 전용 작업 영역입니다. 담당 배정은 [모듈 개발 가이드](docs/module-development.md#담당-배정)에 기록합니다.
