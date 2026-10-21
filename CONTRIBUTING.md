# 기여 안내

## 작업 단위

이 저장소는 uv 멀티패키지 워크스페이스입니다. 팀원은 [담당 배정표](docs/module-development.md#담당-배정)에 따라 해당 패키지의 `src/`, `tests/`, `pyproject.toml`과 배정된 평가 영역을 수정합니다. `contracts`의 공개 포트와 `app` 조립은 여러 모듈에 영향을 주므로 공동 리뷰 대상으로 다룹니다.

모듈 경계와 책임은 [모듈 개발 가이드](docs/module-development.md), 설계 근거는 [확정 모듈 설계](docs/planning/module-design-confirmed.md)를 따릅니다. 관리자·PM은 이동찬이며, 리뷰 요청은 모듈 배정과 별개로 [.github/CODEOWNERS](.github/CODEOWNERS)에 등록한 팀원 전체에게 보냅니다.

이름·구조·예외·로그 등 공통 기준은 이 문서의 [공통 코딩 규칙](#공통-코딩-규칙)을 따릅니다. 개인 AI 하네스는 각자의 로컬에서 관리합니다.

## 시작

```bash
git clone https://github.com/ABC2LAB/abc2lab-dast.git
cd abc2lab-dast
git switch -c feat/knowledge-projector
uv run --no-project --python 3.13.15 scripts/dev.py setup all
```

`setup all`은 여러 담당 패키지를 같은 `.venv`에 설치하고 개발 도구·extra, pre-commit 훅과 기본 테스트를 준비합니다. 작업 중에는 담당 패키지마다 격리 검사를 실행합니다.

```bash
uv run --no-project --python 3.13.15 scripts/dev.py check knowledge
```

`check all`은 PM 또는 CI와 같은 전체 검사가 필요할 때만 사용합니다. 팀원이 루트 설정이나 전체 의존성을 따로 구성할 필요는 없습니다.

## 브랜치와 PR

- 팀원별 상시 브랜치를 만들지 않는다. 기능·수정 등 작업 단위로 짧게 브랜치를 사용하고 PR 하나에 한 가지 변경 목적을 담는다.
- 새 작업은 `git fetch origin`으로 갱신한 최신 `origin/main`에서 시작한다. 이미 병합한 작업 브랜치를 다음 작업에 재사용하지 않는다.
- 팀원 개발 브랜치는 `feat/<module>-<short-name>` 또는 `fix/<module>-<short-name>`으로 짓는다. 예: `feat/knowledge-store-memory`, `fix/gateway-timeout`.
- 문서·설정 작업은 `docs/<scope>-<short-name>`, `chore/<scope>-<short-name>`을 사용한다. Codex가 만드는 브랜치는 `codex/<short-name>`을 사용하며 같은 작업·PR 수명 규칙을 따른다.
- 브랜치 이름과 작업명은 영어 소문자·숫자·하이픈으로 쓴다. 한 사람이 여러 모듈을 맡아도 작업 목적과 대표 모듈을 드러내고, 무관한 변경은 별도 PR로 분리한다.
- `main`에 직접 push하지 않고 작업 브랜치를 원격에 올려 `main` 대상으로 PR을 만든다. 필수 CI 통과·미해결 대화 처리·작성자 외 팀원 1명 이상의 승인 후 병합한다.
- 병합이 끝난 작업 브랜치는 정리한다. 다음 작업은 다시 최신 `origin/main`에서 새 브랜치로 시작한다.

```bash
git fetch origin
git switch -c feat/knowledge-store-memory origin/main
```

## 변경 규칙

- 작업 브랜치의 생성·명명·병합 후 정리는 [브랜치와 PR](#브랜치와-pr)의 기준을 따릅니다.
- 공개 계약이 필요하면 먼저 `contracts` 변경을 별도 PR로 제안하고 의존 모듈 담당자의 리뷰를 받습니다.
- 다른 모듈의 내부 구현, 스키마, 유틸리티를 import하지 않습니다. 공개 포트만 사용하고 테스트에서는 모듈 로컬 fake를 둡니다.
- `gateway`만 대상 HTTP/브라우저 통신을 소유합니다. 코어와 기본 단위 테스트는 실제 네트워크·DB를 사용하지 않습니다.
- 비밀값, 원문 응답, 캡처 핸들, GT를 로그·공개 포트·PR에 넣지 않습니다.
- 의존성 변경은 해당 패키지의 `pyproject.toml`과 루트 `uv.lock`을 같은 PR에 포함합니다. `contracts`, `app`, 루트 설정 변경은 영향받는 모듈을 PR에 기록합니다.

## PR 작성과 검증

일반 PR을 열거나 draft를 리뷰 준비 상태로 바꾸면 작성자를 제외한 팀원 모두에게 리뷰가 자동 요청됩니다. 필수 CI 통과와 미해결 대화 처리 후 팀원 1명이 승인하면 병합할 수 있습니다. 모든 리뷰어의 승인을 기다릴 필요는 없습니다. 팀원이 바뀌면 `.github/CODEOWNERS`의 목록도 갱신합니다.

작은 단위로 PR을 만들고 템플릿의 범위·검증·계약 변경 여부를 채웁니다. CI가 전체 워크스페이스와 모듈별 격리 검사를 실행합니다. 리뷰에서 합의되지 않은 모듈 경계 변경, 빈 `Any` placeholder API, 구현되지 않은 scaffold를 기능 완료로 표시하지 않습니다.

```bash
git fetch origin
git rebase origin/main
uv run --no-project --python 3.13.15 scripts/dev.py check knowledge
git push -u origin feat/knowledge-projector
```

main에 직접 push하지 말고 PR로 병합합니다. 병합 후에는 브랜치를 삭제하고 다음 작업에서 최신 main을 다시 받습니다.

커밋 훅이 Ruff로 파일을 고칠 수 있습니다. 훅 실행 뒤 변경된 파일을 다시 `git add`하고 커밋을 재시도합니다. 훅을 우회하지 말고, CI가 최종 검증합니다.

## 공통 코딩 규칙

포맷은 도구에 맡기고 이름·책임 경계·계약·오류·로그의 의미를 리뷰합니다. 작은 변경과 기존 패턴·유틸리티 재사용을 우선하며 중복 추상화나 공통 `utils` 패키지를 임의로 추가하지 않습니다.

### 도구가 처리하는 형식

- Python 포맷·import 정렬·린트는 루트 `pyproject.toml`의 Ruff 설정을 따른다. 현재 줄 길이는 **100**이다. 도구가 정리한 형식을 수동으로 다시 맞추지 않는다.
- UTF-8, LF, 공백 들여쓰기를 사용하고 파일 끝에 개행을 둔다. `.editorconfig`와 `.gitattributes`를 따른다. Python은 4칸이다.
- EditorConfig는 지원하는 에디터의 설정이며 커밋 차단 장치가 아니다. 커밋 훅은 로컬 Ruff 포맷·수정을 실행하고, 최종 검증은 CI의 Ruff·mypy·Import Linter·pytest가 담당한다.
- Python 저장소에는 pre-commit과 Ruff가 설정되어 있다. JS/React 프로젝트가 추가되기 전까지 Prettier·ESLint는 설치하거나 설정하지 않는다.

### 이름과 구조

- 식별자는 영어를 사용한다. 주석·커밋·문서는 한글을 허용한다.
- 변수·함수·메서드·Python 모듈은 `snake_case`, 클래스는 `PascalCase`, 상수는 `UPPER_SNAKE_CASE`로 쓴다. 함수 이름은 동작을 드러낸다.
- 내부용 이름은 `_`로 시작한다. bool은 `is_`·`has_`·`can_`, 컬렉션은 복수형, 매핑은 `endpoints_by_role`처럼 관계를 드러낸다.
- `req`, `ep` 같은 임의 축약을 피한다. `url`, `id`, `db`, `kg`, `llm`, `http`와 외부 프로토콜·SDK가 정한 이름은 유지할 수 있다.
- `abc2lab-*` 배포 패키지명과 `mcp-*` 워크스페이스 디렉터리는 기존 구성을 유지한다. Python import 이름은 `abc2lab_mcp_knowledge`처럼 underscore를 사용한다.
- 함수 시그니처의 인자·반환 타입을 명시한다. 내부 변수의 추가 타입 표기는 필요한 경우에만 한다.
- 함수는 한 가지 책임을 갖는다. 약 40줄을 넘으면 분리를 검토하고, 인자가 4개를 넘으면 함께 움직이는 값들을 설정·요청 dataclass로 묶을지 검토한다. 줄 수를 맞추기 위한 쪼개기나 무관한 인자 묶기는 하지 않는다.
- 의미 있는 수치·단위·기본값은 `DEFAULT_TIMEOUT_S` 같은 상수나 설정으로 표현한다. URL·계정·timeout·모델명은 설정·등록 프로필에서 받아 `app`이 주입한다. 테스트 fixture의 명시적 예시는 허용한다.
- 경로는 `pathlib.Path`, 일반 문자열 조합은 f-string을 우선한다. 외부 입력을 SQL/Cypher에 문자열 삽입하지 않고 파라미터 바인딩·등록 질의를 사용한다.
- import는 절대 경로를 사용하고 `from x import *`는 금지한다. 정렬은 Ruff에 맡긴다.
- 주석은 이유·제약·주의할 의미를 설명한다. 주석 처리한 코드는 제거하고 TODO는 `# TODO(github_id): 내용`처럼 작성자를 식별할 수 있게 남긴다.
- 공개 함수·클래스에는 Google 스타일의 한 줄 요약 docstring을 쓴다. 필요한 오류·부분 결과 의미도 설명한다.

### 모듈 경계와 데이터 계약

- 다른 모듈의 내부 구현·스키마·유틸리티를 import하지 않는다. 공유 타입과 호출 포트는 `contracts`에 두고, `app`만 구체 구현을 조립·주입한다.
- `contracts`는 표준 라이브러리만 사용하는 의존성 최하단이다. 공유 데이터는 의미가 명확한 `dataclass`·enum·Protocol 등으로 정의한다. 스키마를 피하려고 임의 dict나 빈 `Any` API를 사용하지 않는다. 본래 매핑인 자료에 dict를 사용하는 것은 허용한다.
- fingerprint의 바이트 동일성은 [공유 계약 codec](docs/planning/fingerprint-contract.md)의 단일 구현으로 보장한다. contracts에 예외적으로 두는 무상태 순수 함수이며 I/O·업무 판정·비밀 제거·범용 utils를 추가하는 허용은 아니다. 각 모듈과 fake는 이 codec을 재사용한다.
- Pydantic이 필요한 외부 입력·MCP 와이어 검증은 해당 어댑터에서 처리한다. Pydantic 모델이나 별도 JSON 파일을 전체 도메인의 정본으로 지정하지 않는다.
- 공개 타입·포트가 아직 비어 있으면 최소 의미 계약부터 제안한다. 필요한 로컬 fake는 그 공개 포트를 구현한다. scaffold를 기능 구현이나 준비된 test double로 표시하지 않는다.
- 공개 스키마가 바뀌면 PR 제목에 `스키마 변경`을 표시하고 영향받는 모듈·호환성·검증 결과를 적는다. 계약 담당 이동찬과 영향받는 모듈 담당자 중 작성자를 제외한 관련자를 리뷰에 포함한다.
- 외부 JSON을 정의할 때는 프로젝트 소유 키에 `snake_case`, 날짜에 ISO 8601, 시각에 타임존이 있는 ISO 8601을 사용한다. 기존 외부 프로토콜의 필드명은 유지한다. 필수·생략·`null`·부분 결과의 의미와 스키마 버전은 기능별 계약에서 명시한다. 파일 교환이 필요하면 기본 파일명은 `module_subject_YYYYMMDD.json`으로 한다.
- 대상 HTTP/브라우저 통신은 `gateway` 어댑터만 수행한다. 각 서비스는 자기 저장 어댑터에서 자기 DB 역할·스키마만 사용하며 AGE 질의는 `knowledge`가 소유한다.
- 코어 단위 테스트는 네트워크·브라우저·DB 없이 실행한다. 실제 실행 환경이 필요한 테스트에는 `integration` marker와 준비 방법을 명시한다. 기본 pytest는 이 marker를 제외하며 통합 테스트는 별도 환경에서 실행한다.
- 평가 GT는 `eval`의 평가 전용 자료다. 제품의 발견·추론·판정 경로가 GT를 읽거나 이를 정답 단서로 사용하지 않는다.

### 예외와 로그

- `except:`와 `except Exception: pass`는 금지한다. 복구할 수 있는 구체적 예외를 처리하고, 경계에서 넓게 잡을 때는 실패 상태·사유를 보존하거나 다시 발생시킨다.
- timeout·인증 실패·조회 실패를 성공한 빈 목록이나 확정 가능한 부재로 바꾸지 않는다. 계약에 맞는 실패·부분 결과·판단불가를 남긴다. 전송 여부가 불명인 요청을 자동 재전송하지 않는다.
- 라이브러리·서비스의 진단 출력은 `logging.getLogger(__name__)`을 사용한다. CLI의 명시적 결과 출력과 프로토콜 출력은 해당 출력 계약을 따른다. 디버깅용 `print()`는 커밋하지 않는다.
- 정상 진행은 INFO, 복구 가능한 재시도·스킵은 WARNING, 처리 실패는 ERROR를 기준으로 한다. 로그 문자열은 `%s`와 인자를 전달하는 지연 포맷을 사용한다.
- 로그는 허용된 run/task/request/evidence 참조와 이벤트·사유 코드로 연결한다. 쿠키·토큰·비밀번호·원문 응답·캡처 핸들·run HMAC 키·GT를 로그·PR·공개 포트에 넣지 않는다.
- URL 쿼리, 응답 본문, 예외 메시지·traceback에도 비밀이 포함될 수 있으므로 그대로 기록하지 않는다. 진단에 필요한 정보만 민감값을 제거한 뒤 남긴다.

### 별도 기능 단계

- UI·target-app의 JS/React 채택과 Prettier·ESLint는 해당 코드가 추가될 때 정한다. 현재 Python 모듈 개발의 환경 설정에는 포함하지 않는다.
- 브라우저 바이너리, PostgreSQL+AGE 서버, MCP 서버와 외부 실행 파일은 각 어댑터의 통합 테스트 단계에서 준비한다. 기본 모듈 검사에는 필요하지 않다.

이 지침은 [모듈 설계](docs/planning/module-design-confirmed.md)의 책임 경계를 따른다. 설계 문서가 충돌하면 [아키텍처](docs/planning/mcp-architecture.md)를 우선한다.

## 개인 하네스

저장소 루트의 `AGENTS.md`는 각자 로컬에서 유지하는 개인 하네스이며 Git 추적에서 제외합니다. 팀 공통 기준은 이 문서, 모듈 배정은 [모듈 개발 가이드](docs/module-development.md)를 참조합니다.

기존 `AGENTS.md`를 개인화했다면 main 업데이트 전에 개인 사본을 별도 경로에 보관합니다. 공유 파일 제거가 반영된 뒤 루트의 `AGENTS.md`로 복원하면 이후 커밋에 포함되지 않습니다.
