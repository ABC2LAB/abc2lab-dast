# Repository agent guidance

- 저장소 루트는 Python 3.13.15와 uv 0.12.23을 사용한다.
- 작업 지침은 저장소 루트에서 시작하며, 더 좁은 디렉터리 지침이 생기면 그 범위를 따른다.
- 담당 모듈의 `src/`, `tests/`, `pyproject.toml` 안에서만 구현을 시작한다.
- 공유 `uv.lock`, 루트 설정, `contracts`, `app` 변경은 의존성·계약 PR로 분리하고 관련 담당자와 조율한다.
- 다른 모듈의 내부 구현·스키마·유틸리티를 import하지 않는다. `contracts`의 공개 포트만 사용한다.
- `contracts`는 순수 표준 라이브러리 기반의 의존성 leaf이며, 공개 타입·Protocol을 먼저 합의한다.
- 현재 공개 타입/Protocol이 비어 있다면 빈 `Any` API를 만들지 말고 최소 의미 계약을 먼저 제안한다.
- 모듈 테스트는 공개 계약을 구현하는 로컬 fake를 사용한다. scaffold는 구현 완료나 준비된 test double이 아니다.
- `app`만 구체 구현을 조립하고 주입한다. 서비스 코어가 다른 서비스 구현을 생성하지 않는다.
- 대상 HTTP/브라우저 통신은 `gateway` 어댑터만 소유한다. PostgreSQL은 각 서비스의 저장 어댑터만 사용한다.
- 코어 단위 테스트는 실제 네트워크·브라우저·DB를 기본으로 사용하지 않는다. 통합 테스트에는 명시적 marker를 둔다.
- raw secret, 원문 응답, 캡처 핸들, run key, GT를 로그·PR·공개 포트에 노출하지 않는다.
- 변경은 작게 유지하고 기존 패턴·유틸리티를 우선 재사용한다.
- 담당 모듈 명령은 `docs/module-development.md`를 따르고, 전체 구조 검사는 루트 CI 결과를 확인한다.
