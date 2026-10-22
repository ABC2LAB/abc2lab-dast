# C4-A Knowledge 공유 계약

상태: **공유 계약 로컬 구현·검증 / 제공자·소비자 리뷰 전 (2026-10-21)**. 이동찬의 `contracts`와 관련 문서가 범위다. C3 [PR #27](https://github.com/ABC2LAB/abc2lab-dast/pull/27)의 Evidence 계약을 선행 의존성으로 사용하며, 해당 PR이 병합됐다고 표시하지 않는다. `knowledge`의 실제 메모리 저장소·AGE 어댑터, Host/WebDiag/Judge/Report 서비스, `app` 조립은 후속 구현이다.

기준은 [S1 API §8](s1-api-spec.md#8-knowledge의-후보와-투영), [모듈 설계](module-design-confirmed.md), [fingerprint 계약](fingerprint-contract.md)이다. 목표는 Host와 Knowledge 담당자가 상대 구현 없이 같은 요청·결과·실패 사례로 개발하는 것이다.

## 1. 공개 타입과 포트

`abc2lab_contracts.ports.KnowledgePort`는 다음 세 비동기 메서드를 제공한다. 입력·출력 필드는 기존 S1 표를 그대로 사용한다.

| 메서드 | 요청 | 결과 |
|---|---|---|
| `register_candidates` | `CandidateSubmission` | `CandidateAck` |
| `project` | `ProjectionSubmission` | `ProjectionAck` |
| `get_case_view` | `CaseReadRequest` | `CaseReadResult` |

후보·조회·ACK는 `abc2lab_contracts.knowledge`에서 import한다. `CandidateHint.discovery_kind`는 `DiscoveryKind` enum이고, `ProjectionAck.disposition`은 `ProjectionDisposition` enum이다. `Candidate`에는 명세에 없는 discovery_kind나 실제 URL·파라미터를 추가하지 않는다.

`abc2lab_contracts.projection.ProjectionEvent`는 `ObservationProjected | ComparisonProjected | VerdictProjected | PolicyRegistered`의 폐쇄 union이다. C3의 `ComparisonProjected`를 재사용하며, 다른 세 이벤트의 최소 payload인 `observation.Observation`, `verdict.Verdict`, 기존 `registration.ExpectedAccessPolicySnapshot`을 사용한다. 이 자료형 추가가 WebDiag/Judge의 서비스 구현이나 공개 호출 포트 구현을 뜻하지 않는다. `run`/`task`·Report 타입은 이번 범위에 없다.

## 2. 결과의 일관성

| 결과 | COMPLETE | PARTIAL | FAILED |
|---|---|---|---|
| 후보 등록 | 후보·Knowledge revision, 정상 0건도 허용 | 수락한 후보·revision·사유 | 후보 없음·revision None·사유 |
| 투영 | applied/duplicate·적용 revision | deferred·revision None·사유 | rejected·revision None·사유 |
| 조회 | 일관 snapshot revision·truncated=False | 허용된 자료·snapshot revision·사유 | 자료 없음·revision None·truncated=False·사유 |

생성자는 중첩 타입·동일 run·후보 ref 중복·생산자별 event ref 중복과 위 상태 조합을 검증한다. PARTIAL/FAILED는 비어 있지 않은 사유가 필요하다. 절단된 조회는 PARTIAL이며 `result_limit_exceeded` 사유를 사용한다. 조회 권한과 실제 누락 여부는 서비스가 확인하며, 권한 없는 자료의 존재를 사유로 누설하지 않는다.

## 3. 원본 payload와 감사 결합

각 이벤트는 kind/run/producer/event_ref/source_revision과 receipt의 대응 필드, record ref/revision 및 **실제 payload에서 재계산한 fingerprint**가 일치해야 한다. Observation/Verdict의 source_event도 같은 producer/event_ref여야 한다. Policy는 run의 target/environment와 일치해야 한다.

| 원본 | record ref | source/record revision | fingerprint |
|---|---|---|---|
| Observation | observation_ref | 불변 record `1` | `observation_fingerprint` / observation.v1 |
| Comparison | comparison_ref | 불변 record `1` | C3 `comparison_fingerprint` / comparison.v1 |
| Verdict | verdict_ref | verdict.revision | `verdict_fingerprint` / verdict.v1 |
| ExpectedPolicy | policy_ref | policy.source.revision | `expected_policy_fingerprint` / expected_policy.v1 |

세 새 wrapper는 정확한 타입·명시적 필드 집합·중첩 enum/tuple/UTC 시각을 hash 전에 검증한다. 모든 업무 필드와 미리 고정한 source_event를 포함하고 새 영수증을 payload에 넣지 않는다. 흐름은 **payload와 source event ID 고정 → fingerprint → 원본 producer commit → receipt → projection**이다. 기존 C1/C2/C3 bytes·벡터는 변경하지 않는다.

`AuditReceipt.sequence`는 생산자의 감사 순번, `source_revision`은 원본 record 버전, `knowledge_revision`은 graph snapshot 버전이다. 서로 같다고 가정하지 않는다. 타입 생성 성공은 실제 commit·저장·인가의 증명이 아니다. Knowledge는 `app`이 주입한 신뢰된 생산자별 `AuditVerifier`와 Evidence 읽기 포트로 원본·출처·의존 자료를 독립 확인한다. PolicyRegistered는 신뢰된 등록 생산자에게만 허용한다. Host가 receipt나 producer를 다시 작성하지 않는다.

Verdict 생성자는 CONFIRMED의 필요조건(3개 check 모두 YES, 정책 출처·비교·근거 ref 존재)만 검사한다. 다른 결론은 사유를 남긴다. 실제 정책·신원·데이터 검증과 SUSPECTED의 판정 기준은 Judge 소유이며 이 계약이 판정 알고리즘을 정의하지 않는다.

공유 `VerdictValue`의 wire 값은 명세대로 대문자다. 소문자 enum을 사용하는 Judge 내부 모델은 후속 제공자 어댑터에서 공유 VerdictValue·CheckState로 명시 변환한다. 내부 enum 객체를 공유 계약에 직접 넣지 않으며 이번 변경에서 Judge 구현을 수정하지 않는다.

## 4. revision·멱등성·조회 한도 명확화

- 빈 run graph의 최초 일관 snapshot revision은 **1**이다. 실제 graph 상태가 달라질 때만 증가한다. 한 후보 batch가 여러 후보를 바꿔도 그 적용 단위의 graph revision은 한 번 증가한다. Candidate.revision과는 별개다.
- 같은 `(run_key, submission_ref)`의 동일 후보 입력은 기존 ACK/후보를 재사용한다. 다른 입력은 idempotency_conflict이며 기존 등록을 덮어쓰지 않는다. 서로 다른 출처의 단서를 어떤 후보로 병합할지는 실제 Knowledge 정규화 정책에서 결정한다.
- 투영 식별자는 `(run_key, producer, event_ref)`다. 같은 이벤트/내용은 duplicate로 **최초 적용 revision**을 돌려주고 graph revision을 증가시키지 않는다. 같은 식별자의 다른 내용은 rejected/idempotency_conflict다. deferred/rejected는 graph에 0건 적용한다. deferred 재제출은 동일 원본 이벤트를 사용하고 대상 요청을 재전송하지 않는다.
- `CaseReadRequest.limit`은 **candidates와 events의 반환 개수 합계** 상한이며 1–100이다. 반환은 단일 snapshot에서 결정한다. 요청 revision을 제공할 수 없으면 failed/revision_unavailable이며 최신 snapshot으로 대체하지 않는다. 현재 revision만 지원하는 메모리 구현을 허용한다.
- `candidate_refs`와 Comparison/Verdict/Policy 이벤트를 연결하는 일반 조회 알고리즘·정렬·페이지 cursor는 이 최소 계약에서 새로 확정하지 않는다. 실제 Knowledge 구현 착수 시 그 연계·접근 범위 규칙을 별도로 정의해야 한다. 무전송 fake는 명시적으로 연결한 한 후보의 fixture만 읽으며 범용 graph 질의를 구현했다고 표시하지 않는다.

## 5. 무전송 연결 예제와 담당 검토

계약 테스트와 [무전송 fake](../../packages/contracts/tests/test_no_io_knowledge.py)는 Host의 **단서 등록 → 후보 snapshot 조회 → 원본 이벤트 투영 → 조회**를 재생한다. 중복·충돌·검증 unknown/deferred·누락 Evidence·권한 거부·stale revision·절단을 구분하고, 검증하지 못한 이벤트는 graph에 적용하지 않는다. 실제 HTTP·브라우저·DB·AGE·GT를 사용하지 않는다.

| 담당 | 검토할 경계 |
|---|---|
| 이동찬 (`contracts`, `knowledge`, `app`) | 공유 타입·codec·Knowledge 책임, 실제 저장·조립과의 구분 |
| 이경준 (`host`, `webdiag`, `evidence`) | CandidateHint/Observation, Host 호출 순서, Evidence 의존성과 원본 이벤트 보존 |
| 최민준 (`judge`, `policy`, `gateway`, `report`) | Verdict·ExpectedPolicy 소비, 감사 binding·불명 보존, 무전송 경계 |

팀원의 승인이나 실제 서비스 통합 완료는 이 문서의 타입 구현·로컬 검증과 별도로 확인한다.

## 6. 로컬 검증 기록

2026-10-21, Python 3.13.15에서 다음을 확인했다. GitHub CI나 팀원 승인 결과가 아니다.

| 검사 | 결과 |
|---|---|
| `scripts/dev.py check contracts` | Ruff lint/format, strict mypy 33개 파일, 계약 테스트 221개 통과 |
| 전체 기본 pytest / mypy | 303개 테스트 / 55개 소스 파일 통과 |
| Import Linter | 6개 경계 유지·위반 0개 |
| contracts wheel·sdist | 빌드 성공 |
| 고정 벡터 | 기존 8개 유지, 새 3개 typed bytes/digest 일치, 전체 11개 SHA-256 재계산 일치 |

상태 타입·위조 바인딩·조회 실패·부분 결과·취소 전파를 계약/fake 범위에서 검사한다. 실제 동시성·저장 트랜잭션·생산자 journal 내구성·snapshot 연계 알고리즘의 검증 완료를 뜻하지 않는다.
