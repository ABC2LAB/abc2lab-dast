# 결정적 fingerprint 계약 v1

상태: 팀 검토용 제안. 이번 문서는 구현을 추가하지 않는다. `contracts`의 첫 실행 경계 PR에서 이 규칙과 테스트 벡터를 함께 구현한다.

## 1. 소유권과 경계

`contracts`가 `abc2lab_contracts.fingerprint`에 표준 라이브러리만 사용하는 무상태 codec을 소유한다. 이 codec은 순수 데이터 변환과 SHA-256 계산만 하며 I/O, 시계, 저장, 비밀 제거, 정책 판정, HMAC, 업무 규칙을 수행하지 않는다. 공통 `utils` 패키지가 아니며 `app` 주입용 인터페이스도 아니다. Policy, Gateway, 각 감사 생산자, Knowledge Projector, Evidence, Judge, Report는 같은 구현을 직접 사용한다. 모듈별 codec과 테스트용 대체 codec은 허용하지 않는다.

`contracts`의 범위를 순수 데이터 타입으로만 한정하던 문구는 이 작은 결정적 계약 함수까지 허용하도록 바꾼다. 이는 서비스 구현을 contracts로 옮기는 예외가 아니다. 계약 PR은 한 번에 모든 record를 구현하지 않는다. C1은 codec과 primitive vector만, C2는 typed `PolicyInput`/`PolicyDecision`/`IdentityResult`/`RequestIntentRecord`/`AttemptRecord` adapter와 전체 vector를 다룬다. 이후 record는 각 소비자와 필요한 시점에 별도 typed projection·vector를 추가한다.

제안하는 공개 순수 함수는 C1의 `canonical_json_bytes(value: CanonicalValue) -> bytes`와 C2 이후의 `policy_input_fingerprint(value: PolicyInput) -> Fingerprint` 같은 **record별 typed wrapper**다. 기존 `sha256_fingerprint(kind, version, payload)` 제안은 공개하지 않는다. 호출자가 운영 kind/version과 임의 payload를 따로 조합하는 경로를 만들지 않는다. 이 함수들은 27개 S1 서비스 포트에 포함되지 않으며 아직 구현되지 않았다. CanonicalValue는 아래 폐쇄형 union이며 Any가 아니다.

fingerprint 입력은 호출자가 만든 임의 dict가 아니라 타입별로 허용된 불변 payload다. codec은 원문 HTTP, 쿠키, 토큰, 비밀번호, 캡처 핸들, HMAC 키를 받지 않는다. 원문을 받은 호출자는 먼저 민감값 제거와 typed allowlist를 적용하고, 그 결과를 frozen dataclass나 허용된 snapshot으로 만든다.

## 2. 바이트와 타입 규칙

codec 버전은 `canonical-json.v1`이다. fingerprint는 다음 envelope의 canonical UTF-8 bytes를 SHA-256한 **소문자 64자리 hex**다.

```json
{"codec_version":"canonical-json.v1","record_kind":"...","schema_version":"...","payload":{}}
```

`record_kind`와 `schema_version`은 필수 문자열이다. 등록되지 않은 kind/version은 거부한다. JSON은 `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`로 생성하고 UTF-8로 인코딩한다. BOM, 앞뒤 공백, 마지막 개행을 넣지 않는다.

### 2.1 정규 바이트와 운영 계약 검증의 분리

| 경로 | 검사·반환 | 허용 범위 |
|---|---|---|
| 저수준 canonical_json_bytes | 폐쇄형 값·문자열·시각·인코딩 규칙 검사 후 bytes 반환 | kind/version의 업무 의미를 판단하지 않음. demo envelope도 일반 불변 값으로 인코딩 가능하며 운영 계약 fingerprint 발행은 아님 |
| record별 typed wrapper | 정확한 frozen record 타입과 그 record의 지원 버전을 검사하고 내부 등록 검증기를 호출 | PolicyInput 등을 직접 받으며 dict·임의 envelope·다른 record/subclass를 받지 않음. kind/version은 등록된 상수에서 선택 |
| 내부 운영 등록 검증기 | 불변 registry의 codec_version/record_kind/schema_version/정확한 record 타입/명시적 payload adapter가 모두 일치할 때만 정규화·SHA-256 | 미등록·서로 다른 record의 재라벨·미지원 버전·필드 누락/추가를 거부. 입력이 만든 spec이나 단순 enum 캐스팅을 등록으로 인정하지 않음 |

운영 registry는 계약 코드에 고정된 immutable tuple 같은 상수다. 상수 조회는 가변 런타임 상태를 만들지 않으므로 무상태 순수 함수 원칙과 양립한다. 런타임 등록 API, 환경 변수, 주입 가능한 registry, 테스트용 override/허용 flag, 미등록 값의 기본 adapter fallback은 제공하지 않는다. 테스트도 운영 registry를 바꾸지 않는다.

C1에는 운영 record 등록 항목이 없다. 공통 canonical codec과 등록 거부 검사를 준비하며, 운영 fingerprint를 발행하거나 Policy/Gateway fake가 완성됐다고 표시하지 않는다. C2에서 실제 타입·typed wrapper·payload adapter·고정 벡터와 함께 해당 지원 항목만 추가한다. 아래 표에 이름이 있다는 이유로 구현 전 record를 허용 목록에 먼저 넣지 않는다. 이후 record도 각 계약 PR에서 같은 절차를 따른다.

문서의 설명·절 번호만 바꾸면 schema version은 유지한다. 필드 구성·의미·타입별 payload 변환의 호환성을 깨는 변경은 해당 schema version을 올리고, 공통 정규 바이트 규칙을 바꾸면 codec_version도 올린다. 지원 버전은 계약 코드에서 명시하며 상대 버전을 추측하거나 다른 버전으로 조용히 재인코딩하지 않는다.

허용되는 재귀 값은 다음과 같다.

- 등록된 frozen dataclass의 모든 선언 필드를 문자열 key object로 변환한다. 필드 선언 순서가 아니라 canonical JSON의 key 정렬을 사용한다.
- `Enum`은 등록된 문자열 `.value`만 사용한다. 임의 객체를 문자열로 바꾸지 않는다.
- `str`, `bool`, `None`, signed 64-bit 범위의 `int`를 허용한다. `bool`은 `int`보다 먼저 판정한다.
- tuple은 순서를 보존한 JSON array로 변환한다. tuple의 원소도 같은 폐쇄 규칙을 따른다.
- 도메인 계약에 명시된 immutable/snapshotted mapping만 허용한다. key는 문자열이어야 하며 재귀 값은 폐쇄 규칙을 따른다. 임의 mapping을 모든 도메인 타입의 빈칸으로 사용하지 않는다.
- `SourceVersion`은 특별한 순서 규칙을 갖지 않는 일반 nested object다. `issuer`, `source_ref`, `revision` 세 필드를 모두 직렬화하고, 다른 object와 동일하게 code point 기준 key 정렬을 적용한다.
- timezone-aware `datetime`은 UTC로 변환해 항상 `YYYY-MM-DDTHH:MM:SS.ffffffZ`로 쓴다. naive datetime은 거부한다.

float(유한값 포함), NaN, Infinity, list, set, bytes, Decimal, naive datetime, 비문자열 mapping key, 미등록 dataclass/enum, 임의 객체, `Any` catch-all은 거부한다. 문자열은 Unicode 정규화하지 않고 입력 code point를 보존하며 lone surrogate는 거부한다. 업무상 정규화가 필요하면 fingerprint 전에 별도 버전 규칙으로 처리한다.

## 3. record별 payload

receipt·자체 fingerprint를 제외하는 규칙을 필드명으로 재귀 검색하지 않는다. 각 공개 record는 별도 frozen payload 변환자를 가져야 하며, 그 변환자가 제외 필드와 포함 필드를 명시한다.

모든 record는 envelope에 schema_version을 갖는다. **payload의 schema_version은 해당 업무 타입이 실제 필드로 선언한 경우에만 포함**하며 이때 envelope 값과 일치해야 한다. 현재 PolicyInput은 양쪽에 policy_input.v1이 있고, PolicyDecision·IdentityResult·RequestIntentRecord·AttemptRecord 등은 envelope에만 있다. adapter가 다른 record에도 편의상 필드를 넣거나 PolicyInput의 필드를 빼지 않는다. 정확한 타입·필드 집합·버전 불일치는 hash 전에 거부한다. 이 비대칭은 의도된 계약이며 record별 벡터와 같아야 한다.

| record | payload 규칙 |
|---|---|
| `PolicyInput` | `record_kind=policy_input`, `schema_version=policy_input.v1`. payload에 있는 `schema_version`도 반드시 `policy_input.v1`이며 전체 필드를 포함한다. 자체 digest 필드는 없다. |
| `PolicyDecision` | `record_kind=policy_decision`, `schema_version=policy_decision.v1`. `decision_ref`, `binding_id`, `evaluated_view_fingerprint`, `outcome`, `policy_version`, `issued_at`, `expires_at`, `reason_codes`, `run_key` **9개 업무 필드 전체**를 포함하고 최상위 `audit_receipt` 하나만 제외한다. |
| `IdentityResult` | `record_kind=identity`, `schema_version=identity.v1`. `run_key`, `identity_ref`, `status`, `session_ref`, `account_ref`, `generation`, `subject_ref`, `evidence_ref`, `verified_at`, `valid_until`, `attempt_summaries`, `reason_codes`를 모두 포함하고 최상위 `audit_receipt` 하나만 제외한다. |
| `Observation` | `record_kind=observation`, `schema_version=observation.v1`. 모든 business field를 포함한다. |
| `Verdict` | `record_kind=verdict`, `schema_version=verdict.v1`. 모든 business field를 포함한다. |
| `ExpectedAccessPolicySnapshot` | `record_kind=expected_policy`, `schema_version=expected_policy.v1`. 모든 business field를 포함한다. |
| `EvidenceSummary` | `record_kind=evidence`, `schema_version=evidence.v1`. 모든 business field를 포함한다. |
| `ComparisonPayload` | `record_kind=comparison`, `schema_version=comparison.v1`. 모든 business field를 포함한다. |
| `StoredComparison` | `ComparisonPayload` fingerprint를 계산하고, Evidence 두 건과 Comparison 한 건의 완료 receipt를 별도로 검증한다. receipt를 payload에 임의로 넣거나 재귀 이름 필터로 제거하지 않는다. |
| `RequestIntentRecord` | `record_kind=request_intent`, `schema_version=request_intent.v1`, `record_ref=attempt_ref`, `revision=1` 불변. `run_key`, `request_ref`, `attempt_ref`, `binding_id`, `operation_ref`, `operation_revision`, `purpose`, `account_ref`, `session_generation`, `decision_ref`, `evaluated_view_fingerprint`, `created_at` 전부 포함한다. 실제 private bound request의 raw value/header/body/auth는 포함하지 않으며, binding은 실제 view digest와 Gateway 내부 bound request를 가리키는 검증 metadata다. |
| `AttemptRecord` | `record_kind=attempt`, `schema_version=attempt.v1`, `record_ref=attempt_ref`. `run_key`, `request_ref`, `attempt_ref`, `revision`, `decision_ref`, `binding_id`, `operation_ref`, `account_ref`, `session_generation`, `send_status`, `capture_status`, `occurred_at`, `reason_codes` 전부 포함한다. revision은 상태 revision이며 capture handle, AuthSignal, raw snapshot, headers/body/auth는 포함하지 않는다. 이후 known state는 새 revision으로 append하며 unknown을 추측해 not_sent로 바꾸지 않는다. |
| `run`, `task` | 아직 wire schema가 확정되지 않았다. C4에서 각 record의 비밀 없는 frozen payload, typed projection, schema/kind, golden vector를 확정하기 전에는 generic codec 사용을 보류한다. |

업무 record에 새 필드가 생기면 해당 변환자와 golden vector를 같은 계약 PR에서 갱신한다. 알 수 없는 record kind/version이나 필드 누락은 성공 fingerprint로 바꾸지 않는다.

## 4. 고정 벡터와 후속 테스트

정적 벡터는 [fingerprint-v1-vectors.json](../examples/fingerprint-v1-vectors.json)에 있다. 각 항목은 `canonical_utf8`의 정확한 문자열과 SHA-256을 함께 보존한다. 벡터는 synthetic type encoding만 고정하며, contracts 구현·commit·실행 관문 통과·보안 증명을 의미하지 않는다.

각 벡터의 validation_path는 다음 경로를 구분하며 fingerprint envelope/payload에 포함하지 않는 시험 metadata다.

- canonical_bytes_only: C1의 demo.record/demo.v1. 시험 fixture를 tuple·허용된 불변 mapping으로 구성하고 canonical_json_bytes로 정확한 bytes를 확인한 뒤, **테스트 안의 stdlib hashlib.sha256**으로 기대 digest를 확인한다. 운영 등록 검증기에는 같은 demo를 넣어 거부를 확인한다. 테스트용 운영 등록은 하지 않는다.
- production_adapter: C2 이후 해당 record의 typed wrapper로 확인한다. C1에서 저수준 serializer가 이 JSON을 인코딩할 수 있어도 운영 타입/adapter 검증 통과로 집계하지 않는다.

파일의 JSON array와 시간 문자열은 정규화 후 형태를 보여 준다. 실제 Python adapter는 선언된 필드에 따라 tuple·aware datetime 등으로 검증·변환한 뒤 codec에 넘기며 원본 JSON의 list나 임의 문자열을 타입 검증 없이 통과시키지 않는다. json.loads의 결과를 그대로 운영 typed wrapper에 넘기는 시험은 성공 사례가 아니다. 기존 canonical_utf8/SHA-256 값은 유지한다.

계약 PR은 다음을 검증해야 한다.

- 중첩 object 삽입 순서와 dataclass 선언 순서가 달라도 같은 bytes/digest
- tuple 순서, SourceVersion 한 필드, enum 값, `None`과 필드 생략의 차이는 다른 digest
- 서로 다른 UTC offset의 같은 시각은 같은 digest이며 0 microsecond도 `.000000Z`
- float/NaN/Infinity/naive datetime/list/set/bytes/비문자 key/미지원 version은 거부
- demo의 저수준 bytes/digest는 일치하지만 운영 경로에서는 거부. C1 빈 registry는 모든 운영 record를 거부하고 C2는 실제 등록된 정확한 조합만 허용
- 미등록 codec/kind/schema·record 재라벨·PolicyInput 안팎 버전 불일치·다른 record payload의 불필요한 schema_version 필드·필드 누락/추가·subclass는 hash 전에 거부
- Policy의 전체 PolicyInput과 Gateway의 같은 snapshot이 같은 golden digest를 사용
- receipt의 outcome·binding·record fingerprint 변조는 producer 조회/verify에서 거부

이 문서와 벡터는 런타임 codec 구현이나 보안 검증 완료를 의미하지 않는다.
