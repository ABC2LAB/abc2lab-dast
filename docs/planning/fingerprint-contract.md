# 결정적 fingerprint 계약 v1

상태: **C1 codec 구현·병합 완료** ([PR #15](https://github.com/ABC2LAB/abc2lab-dast/pull/15)). `canonical_json_bytes()`·`CanonicalObject`·`freeze_object()`와 `primitive-v1` 저수준 벡터 검증이 구현됐다. C2 운영 record별 typed wrapper·adapter 및 실행 경계 계약은 아직 미구현이다.

## 1. 소유권과 경계

`contracts`가 `abc2lab_contracts.fingerprint`에 표준 라이브러리만 사용하는 무상태 codec을 소유한다. 이 codec은 순수 데이터 변환과 SHA-256 계산만 하며 I/O, 시계, 저장, 비밀 제거, 정책 판정, HMAC, 업무 규칙을 수행하지 않는다. 공통 `utils` 패키지가 아니며 `app` 주입용 인터페이스도 아니다. Policy, Gateway, 각 감사 생산자, Knowledge Projector, Evidence, Judge, Report는 같은 구현을 직접 사용한다. 모듈별 codec과 테스트용 대체 codec은 허용하지 않는다.

`contracts`의 범위를 순수 데이터 타입으로만 한정하던 문구는 이 작은 결정적 계약 함수까지 허용하도록 바꾼다. 이는 서비스 구현을 contracts로 옮기는 예외가 아니다. 계약 PR은 한 번에 모든 record를 구현하지 않는다. C1은 codec과 primitive vector만, C2는 typed `PolicyInput`/`PolicyDecision`/`IdentityResult`/`RequestIntentRecord`/`AttemptRecord` adapter와 전체 vector를 다룬다. 이후 record는 각 소비자와 필요한 시점에 별도 typed projection·vector를 추가한다.

C1에서 구현된 공개 순수 함수는 `canonical_json_bytes(value: CanonicalValue) -> bytes`다. C2 이후에는 `policy_input_fingerprint(value: PolicyInput) -> Fingerprint` 같은 **record별 typed wrapper**를 추가한다. 기존 `sha256_fingerprint(kind, version, payload)` 제안은 공개하지 않는다. 호출자가 운영 kind/version과 임의 payload를 따로 조합하는 경로를 만들지 않는다. 이 순수 함수들과 후속 wrapper는 27개 S1 서비스 포트에 포함되지 않는다. `CanonicalValue`는 폐쇄형 union이며 `Any`가 아니다.

fingerprint 입력은 호출자가 만든 임의 dict가 아니라 타입별로 허용된 불변 payload다. codec은 원문 HTTP, 쿠키, 토큰, 비밀번호, 캡처 핸들, HMAC 키를 받지 않는다. 원문을 받은 호출자는 먼저 민감값 제거와 typed allowlist를 적용하고, 그 결과를 frozen dataclass나 허용된 snapshot으로 만든다.

## 2. 바이트와 타입 규칙

codec 버전은 `canonical-json.v1`이다. fingerprint는 다음 envelope의 canonical UTF-8 bytes를 SHA-256한 **소문자 64자리 hex**다.

```json
{"codec_version":"canonical-json.v1","record_kind":"...","schema_version":"...","payload":{}}
```

envelope의 codec_version/record_kind/schema_version은 필수 문자열이다. 저수준 canonical_json_bytes는 구조·인코딩을 검사하고, 운영 typed wrapper/registry는 미등록 codec/kind/schema 조합을 거부한다. JSON은 `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`로 생성하고 UTF-8로 인코딩한다. BOM, 앞뒤 공백, 마지막 개행을 넣지 않는다.

### 2.1 정규 바이트와 운영 계약 검증의 분리

| 경로 | 검사·반환 | 허용 범위 |
|---|---|---|
| 저수준 canonical_json_bytes | 폐쇄형 값·문자열·시각·인코딩 규칙 검사 후 bytes 반환 | kind/version의 업무 의미를 판단하지 않음. demo envelope도 일반 불변 값으로 인코딩 가능하며 운영 계약 fingerprint 발행은 아님 |
| record별 typed wrapper | 정확한 frozen record 타입과 그 record의 지원 버전을 검사하고 내부 등록 검증기를 호출 | PolicyInput 등을 직접 받으며 dict·임의 envelope·다른 record/subclass를 받지 않음. kind/version은 등록된 상수에서 선택 |
| 내부 운영 등록 검증기 | 불변 registry의 codec_version/record_kind/schema_version/정확한 record 타입/명시적 payload adapter가 모두 일치할 때만 정규화·SHA-256 | 미등록·서로 다른 record의 재라벨·미지원 버전·필드 누락/추가를 거부. 입력이 만든 spec이나 단순 enum 캐스팅을 등록으로 인정하지 않음 |

운영 registry는 계약 코드에 고정된 immutable tuple 같은 상수다. 상수 조회는 가변 런타임 상태를 만들지 않으므로 무상태 순수 함수 원칙과 양립한다. 런타임 등록 API, 환경 변수, 주입 가능한 registry, 테스트용 override/허용 flag, 미등록 값의 기본 adapter fallback은 제공하지 않는다. 테스트도 운영 registry를 바꾸지 않는다.

C1에서 병합된 운영 registry는 **빈 tuple**이며, 미등록 record는 `_registered_record_fingerprint()`에서 거부한다. 따라서 C1은 운영 fingerprint를 발행하지 않고 Policy/Gateway fake도 제공하지 않는다. C2에서 실제 타입·typed wrapper·payload adapter·고정 벡터와 함께 해당 지원 항목만 추가한다. 아래 표에 이름이 있다는 이유로 구현 전 record를 허용 목록에 먼저 넣지 않는다. 이후 record도 각 계약 PR에서 같은 절차를 따른다.

C2에서는 빈 registry에 항목을 추가하는 것만으로 완료 처리하지 않는다. 현재 내부 골격은 정확한 record 타입과 codec 버전을 확인하고 adapter를 호출하므로, 업무 schema version·필드 집합·PolicyInput 안팎 버전 일치는 typed wrapper/adapter가 명시적으로 검사해야 한다. 누락/추가 필드·subclass·다른 record 재라벨을 거부하는 테스트와 운영 벡터 5개가 함께 통과한 뒤 등록한다. 저수준 bytes를 직접 SHA-256해서 만든 문자열만으로 운영 등록 경로를 통과했다고 판단하지 않는다. 소비자는 typed record에서 다시 계산하고 원본 producer의 receipt도 검증한다.

문서의 설명·절 번호만 바꾸면 schema version은 유지한다. 필드 구성·의미·타입별 payload 변환의 호환성을 깨는 변경은 해당 schema version을 올리고, 공통 정규 바이트 규칙을 바꾸면 codec_version도 올린다. 지원 버전은 계약 코드에서 명시하며 상대 버전을 추측하거나 다른 버전으로 조용히 재인코딩하지 않는다.

허용되는 재귀 값은 다음과 같다.

- record별 typed adapter가 허용한 frozen dataclass의 모든 payload 필드를 문자열 key object로 변환한다. 필드 선언 순서가 아니라 canonical JSON의 key 정렬을 사용한다.
- `Enum`은 record별 typed adapter가 허용한 문자열 `.value`만 사용한다. 별도 런타임 타입 등록소나 임의 객체의 문자열 변환을 만들지 않는다.
- `str`, `bool`, `None`, signed 64-bit 범위의 `int`를 허용한다. `bool`은 `int`보다 먼저 판정한다.
- tuple은 순서를 보존한 JSON array로 변환한다. tuple의 원소도 같은 폐쇄 규칙을 따른다.
- 도메인 계약에 명시된 immutable/snapshotted mapping만 허용한다. key는 문자열이어야 하며 재귀 값은 폐쇄 규칙을 따른다. 임의 mapping을 모든 도메인 타입의 빈칸으로 사용하지 않는다.
- C1의 `freeze_object()`는 정확한 `dict` 또는 `MappingProxyType`을 입력받아 중첩 매핑·tuple을 재귀적으로 복사하고, 외부 매핑에 대한 참조를 보관하지 않는 불변 `CanonicalObject`로 고정한다. 직접 생성하는 `CanonicalObject`의 `entries`도 tuple·문자열 키·중복 키 없음·폐쇄형 값 규칙을 검증한다. 저수준 `canonical_json_bytes()`는 원본 dict·mapping proxy를 직접 인코딩하지 않고 이미 고정된 `CanonicalValue`만 받는다.
- 스냅샷 생성 도중 생산자는 변경되지 않는 일관된 입력을 제공해야 한다. 스냅샷 생성 후의 원본 수정은 결과를 바꾸지 않지만, frozen 객체에 대한 의도적인 런타임 우회 조작까지 막는 보안 경계는 아니다. C2의 업무별 typed adapter가 필드 allowlist·민감값 제거·업무 버전을 검증한 뒤 필요한 스냅샷을 구성한다.
- `SourceVersion`은 특별한 순서 규칙을 갖지 않는 일반 nested object다. `issuer`, `source_ref`, `revision` 세 필드를 모두 직렬화하고, 다른 object와 동일하게 code point 기준 key 정렬을 적용한다.
- timezone-aware `datetime`은 UTC로 변환해 항상 `YYYY-MM-DDTHH:MM:SS.ffffffZ`로 쓴다. naive datetime은 거부한다.

float(유한값 포함), NaN, Infinity, list, set, bytes, Decimal, naive datetime, 비문자열 mapping key, 미등록 dataclass/enum, 임의 객체, `Any` catch-all은 거부한다. 문자열은 Unicode 정규화하지 않고 입력 code point를 보존하며 lone surrogate는 거부한다. 업무상 정규화가 필요하면 fingerprint 전에 별도 버전 규칙으로 처리한다.

### 2.2 C1 공개 API와 사용

구현은 [fingerprint.py](../../packages/contracts/src/abc2lab_contracts/fingerprint.py), 검증은 [test_fingerprint.py](../../packages/contracts/tests/test_fingerprint.py)에 있다. 현재 공개 심볼은 `abc2lab_contracts.fingerprint`에서 직접 import한다.

| 심볼 | 현재 동작 |
|---|---|
| `CODEC_VERSION` | `canonical-json.v1` 고정 상수 |
| `CanonicalValue` | `str`, `bool`, `None`, signed 64-bit `int`, aware `datetime`, 재귀 tuple, `CanonicalObject`의 폐쇄형 union |
| `CanonicalObject(entries)` | 정확한 tuple 쌍으로 object를 구성하고 문자열 키·중복 없음·불변 값을 검사. 키 순서도 정규화 |
| `freeze_object(source)` | 정확한 dict 또는 mapping proxy를 재귀 복사해 `CanonicalObject` 반환. 중첩 dict는 snapshot으로, tuple은 순서를 보존해 고정 |
| `canonical_json_bytes(value)` | 고정된 `CanonicalValue`를 검증하고 정규 UTF-8 bytes 반환. 원본 dict·list·임의 업무 dataclass/enum·지원 타입의 subclass는 거부 |

```python
from abc2lab_contracts.fingerprint import canonical_json_bytes, freeze_object

snapshot = freeze_object({"labels": ("가", "A"), "optional": None})
encoded = canonical_json_bytes(snapshot)
assert encoded == '{"labels":["가","A"],"optional":null}'.encode("utf-8")
```

`freeze_object()` 완료 후 원본 dict나 mapping proxy의 원본을 수정해도 snapshot은 바뀌지 않는다. 입력에 순환 참조가 있으면 `ValueError`로 거부한다. 허용 타입 밖의 값은 `TypeError`, 중복 키·정수 범위·naive datetime 오류는 `ValueError`, lone surrogate는 `UnicodeEncodeError`로 드러난다. 결과 bytes는 C1 저수준 직렬화 결과이며 운영 record fingerprint로 발행된 값이 아니다. `_registered_record_fingerprint()`는 내부 함수이며 서비스가 직접 호출할 공개 API가 아니다.

**시각 경계의 현재 한계:** aware datetime이라도 UTC로 변환한 시각이 Python의 1~9999년 범위를 벗어나면 `OverflowError`가 발생한다. 예를 들어 `datetime.min`에 양의 UTC offset을 붙인 값이 해당한다. 정상 업무 시각의 정규 바이트에는 영향이 없으며, C2의 시각 타입·adapter에서 허용 범위와 오류 처리를 검토한다. 현재 C1이 이 오류를 `ValueError`로 통일했다고 가정하지 않는다.

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
| `run`, `task` | 아직 wire schema가 확정되지 않았다. C4에서 각 record의 비밀 없는 frozen payload, typed adapter, schema/kind, golden vector를 확정하기 전에는 record별 wrapper와 운영 fingerprint 발행을 보류한다. |

업무 record에 새 필드가 생기면 해당 변환자와 golden vector를 같은 계약 PR에서 갱신한다. 알 수 없는 record kind/version이나 필드 누락은 성공 fingerprint로 바꾸지 않는다.

## 4. 고정 벡터와 후속 테스트

정적 벡터는 [fingerprint-v1-vectors.json](../examples/fingerprint-v1-vectors.json)에 있다. 각 항목은 `canonical_utf8`의 정확한 문자열과 SHA-256을 함께 보존한다. C1에서 `primitive-v1` 벡터의 바이트·digest 일치를 실제 테스트로 검증했다. 나머지 운영 벡터는 C2에서 검증할 대상으로 남으며, 벡터 자체는 실행 관문 통과나 보안 증명을 의미하지 않는다.

각 벡터의 validation_path는 다음 경로를 구분하며 fingerprint envelope/payload에 포함하지 않는 시험 metadata다.

- canonical_bytes_only: C1의 demo.record/demo.v1. 구현된 테스트는 tuple·허용된 불변 mapping으로 fixture를 구성하고 `canonical_json_bytes()`의 정확한 bytes와 **테스트 안의 stdlib hashlib.sha256** digest를 검증한다. 같은 demo는 운영 등록 검증기에서 거부되며 테스트용 운영 등록은 하지 않는다.
- production_adapter: C2 이후 해당 record의 typed wrapper로 검증한다. C1에서 저수준 serializer가 이 JSON을 인코딩할 수 있어도 운영 타입/adapter 검증 통과로 집계하지 않는다.

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

C1의 저수준 codec과 `primitive-v1` 벡터·거부 경계 검증은 PR #15에 구현됐다. 이 사실만으로 C2 운영 adapter, 서비스 실행 경계, 실제 대상 전송 안전성이나 취약점 검증이 완료됐다고 보지 않는다.
