# 기여 안내

## 작업 단위

이 저장소는 uv 멀티패키지 워크스페이스입니다. 팀원은 회의에서 지정된 모듈을 맡고, 기본적으로 해당 모듈의 `src/`, `tests/`, `pyproject.toml`만 수정합니다. `contracts`의 공개 포트와 `app` 조립은 여러 모듈에 영향을 주므로 공동 리뷰 대상으로 다룹니다.

모듈 경계와 책임은 [모듈 개발 가이드](docs/module-development.md), 설계 근거는 [확정 모듈 설계](docs/planning/module-design-confirmed.md)를 따릅니다. 담당자 이름과 CODEOWNERS는 담당자 회의 뒤 추가합니다.

이름·구조·예외·로그 등 코딩 기준은 사람과 AI 모두 [AGENTS.md](AGENTS.md)를 참조합니다.

## 시작

```bash
git clone https://github.com/ABC2LAB/abc2lab-dast.git
cd abc2lab-dast
git switch -c feat/knowledge-projector
uv run --no-project --python 3.13.15 scripts/dev.py setup knowledge
```

`setup`은 선택한 모듈의 잠금 의존성·개발 도구·extra, pre-commit 훅과 기본 테스트를 준비합니다. 작업 중에는 담당 모듈만 격리 검사합니다.

```bash
uv run --no-project --python 3.13.15 scripts/dev.py check knowledge
```

`check all`은 PM 또는 CI와 같은 전체 검사가 필요할 때만 사용합니다. 팀원이 루트 설정이나 전체 의존성을 따로 구성할 필요는 없습니다.

## 변경 규칙

- 브랜치 이름은 `feat/<module>-<short-name>` 또는 `fix/<module>-<short-name>`처럼 모듈을 포함합니다.
- 공개 계약이 필요하면 먼저 `contracts` 변경을 별도 PR로 제안하고 의존 모듈 담당자의 리뷰를 받습니다.
- 다른 모듈의 내부 구현, 스키마, 유틸리티를 import하지 않습니다. 공개 포트만 사용하고 테스트에서는 모듈 로컬 fake를 둡니다.
- `gateway`만 대상 HTTP/브라우저 통신을 소유합니다. 코어와 기본 단위 테스트는 실제 네트워크·DB를 사용하지 않습니다.
- 비밀값, 원문 응답, 캡처 핸들, GT를 로그·공개 포트·PR에 넣지 않습니다.
- 의존성 변경은 해당 패키지의 `pyproject.toml`과 루트 `uv.lock`을 같은 PR에 포함합니다. `contracts`, `app`, 루트 설정 변경은 영향받는 모듈을 PR에 기록합니다.

## PR

작은 단위로 PR을 만들고 템플릿의 범위·검증·계약 변경 여부를 채웁니다. CI가 전체 워크스페이스와 모듈별 격리 검사를 실행합니다. 리뷰에서 합의되지 않은 모듈 경계 변경, 빈 `Any` placeholder API, 구현되지 않은 scaffold를 기능 완료로 표시하지 않습니다.

```bash
git fetch origin
git rebase origin/main
uv run --no-project --python 3.13.15 scripts/dev.py check knowledge
git push -u origin feat/knowledge-projector
```

main에 직접 push하지 말고 PR로 병합합니다. 병합 후에는 브랜치를 삭제하고 다음 작업에서 최신 main을 다시 받습니다.

커밋 훅이 Ruff로 파일을 고칠 수 있습니다. 훅 실행 뒤 변경된 파일을 다시 `git add`하고 커밋을 재시도합니다. 훅을 우회하지 말고, CI가 최종 검증합니다.
