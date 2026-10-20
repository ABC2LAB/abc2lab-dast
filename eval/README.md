# 평가 작업 영역

담당자는 **윤재상**이다. `evidence`·`report`와 함께 근거·보고·평가 범위를 맡는다.

이 디렉터리는 [모듈 설계](../docs/planning/module-design-confirmed.md)의 평가 하네스·코퍼스 작업 영역이다. `packages/` 아래의 uv 패키지가 아니므로 `scripts/dev.py setup eval`이나 `check eval` 대상에는 포함되지 않는다. 현재는 담당 범위 안내만 있으며 평가 실행 코드·데이터·테스트는 아직 없다.

- 평가 하네스, 평가 코퍼스·라벨, 평가 지표와 재현 절차를 이곳에서 관리한다.
- Ground Truth는 평가기만 읽는다. 제품의 발견·추론·판정 경로는 `eval/`이나 GT를 입력·정답 단서로 사용하지 않는다.
- `report`는 제품의 진단 결과·감사 보고를, `eval/`은 그 결과에 대한 평가를 맡는다.
- 평가 실행 코드와 테스트를 추가할 때 실행 명령·의존성·CI 수집 경로를 함께 정의한다. 현재 기본 pytest 경로에 `eval/`이 자동 포함된 것으로 취급하지 않는다.

공통 환경은 `uv run --no-project --python 3.13.15 scripts/dev.py setup all`로 설치한다. 기존 담당 패키지는 `check evidence`와 `check report`로 검사한다. 자세한 배정과 경계는 [모듈 개발 가이드](../docs/module-development.md)를 따른다.
