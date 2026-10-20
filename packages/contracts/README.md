# contracts: 실행 관문 계약 1차

표준 라이브러리만 사용하는 불변 dataclass·enum·Protocol이다. [모듈 설계 §5–6](../../docs/planning/module-design-confirmed.md)의 의미 계약 중 **Policy → Gateway 실행 경계**를 먼저 구현한다. 실제 정책 평가·통신·저장·감사 기능은 각 구현 모듈의 책임이다.

## 사용 범위

- `abc2lab_contracts`: 실행 맥락·요청 바인딩·정책 결정·`PolicyPort`와 불투명 참조.
- `abc2lab_contracts.execution`: `GatewayPort`, `CapturedObservation`, `CaptureRef`, 전송·캡처 상태. 실행 영역 내부에서만 import한다. 패키지 루트에서 재노출하지 않는다.
- 포트는 설계 예시와 같은 동기 `def`이다. 테스트의 로컬 fake는 상속 없이 Protocol에 구조적으로 맞춘다. 비동기 포트가 필요하면 별도 계약 변경으로 합의한다.

`RunContext`에는 run·scope·실행 승인·profile·budget 참조가 들어간다. `RequestBinding`은 이 맥락과 요청 ID·요청 명세 revision·method·목적·계정·세션 세대를 묶는다. 관찰은 익명 계정을 허용하고 인증 목적은 계정 참조가 필요하다. 이 세션 바인딩은 인증 성공이나 실제 subject를 증명하지 않는다.

참조 값은 공백·제어문자가 없는 비밀이 아닌 식별자다. scope·authorization·request spec·profile·budget의 `(value, revision)` 대상 내용은 변경하지 않는다. 새 내용은 새 revision을 사용한다. 요청 명세는 실제 목적지·헤더·본문·인증 준비 전체를 고정하며, 같은 참조 아래 내용을 바꾸면 바인딩 검사가 무효해진다. 원문 자료는 실행 영역의 등록소·Vault가 해결한다. 참조 대상의 존재·불변성·유효성은 이 패키지가 검증하지 않는다.

## 반드시 유지할 의미

1. Policy는 context 불일치나 확인 불가를 block으로 처리하고, 반환 결정에 **입력 plan의 binding**을 보존한다. 실행 승인과 Judge의 기대 접근 정책은 서로 다른 개념이다.
2. Gateway는 I/O 전에 `decision.validate_binding(plan)`으로 전체 바인딩 일치를 확인한다. 불일치는 `RequestBindingError`로 거부하며 전송하지 않는다. 이 사전 거부는 `CapturedObservation`이 아니다. 구현은 별도 거부 감사 기록을 남긴다.
3. 바인딩 일치와 `ALLOW`만으로 전송할 수 없다. 구현은 현재 scope·목적지·인증 바인딩·세션 세대·승인 취소·profile·원자적 예산 차감 등을 재검사하고, 실제 전송 전에 intent와 정책 감사 기록을 내구성 있게 저장한다. 리다이렉트·재시도·브라우저 하위 요청도 매번 검사한다.
4. `CapturedObservation`은 동일 바인딩의 결정에만 연결한다. 아래 조합 외에는 생성할 수 없다. `BLOCK` 결정은 `not_sent`만 허용한다.

| `send_status` | `capture_availability` | `capture_ref` | 의미 |
| --- | --- | --- | --- |
| `sent` | `captured` | 있음 | 전송 사실과 실행 영역의 캡처가 있음. HTTP 성공·증거 봉인·취약점 확정은 별개 |
| `sent` | `unavailable` | `None` | 전송은 확실하지만 응답 대기·캡처 저장 등에서 실패. 사유 코드로 구분 |
| `not_sent` | `not_applicable` | `None` | 전송하지 않은 것이 확실 |
| `unknown` | `indeterminate` | `None` | 전송 여부 불명. 미전송·안전·성공으로 바꾸거나 자동 재전송하지 않음 |

`observed_at`은 호출자가 명시하는 timezone-aware UTC 감사 시각이다. timeout·경과 시간·인과 순서 판정에는 사용하지 않고 구현의 monotonic clock을 사용한다. 캡처 등록소는 핸들을 이 관찰의 run·요청·계정·세션 세대·시각에 결합해야 한다.

## 노출과 검증 한계

`CaptureRef`는 `EvidenceRef`가 아니다. 캡처 값은 repr에서 숨기지만, dataclass 직렬화(`asdict` 등)는 값을 읽을 수 있다. 실행 레코드를 Host·LLM·UI·MCP 결과나 로그에 직렬화하지 않는다. namespace와 타입은 프로세스 접근 제어·비밀 제거·감사 저장을 대신하지 않는다. 외부 입력 검증과 버전이 있는 JSON 와이어는 어댑터에서 별도로 정의한다.

테스트의 fake는 계약 사용 예시이며 실제 인증·인가·예산·전송 통제를 구현하지 않는다. 외부 네트워크·브라우저·DB가 필요하지 않다.

```bash
uv run --no-project --python 3.13.15 scripts/dev.py check contracts
```

후속 계약: 세션 생명주기와 실제 subject 검증, `access_compare` 교차 접근, Evidence 캡처·봉인·부분 저장, Judge/Knowledge/WebDiag 포트, AuditEvent. 전체 S1 계약과 서비스 구현은 아직 완료되지 않았다.
