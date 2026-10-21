# 진단 보고서 예시 — 읽기 수평 IDOR

> **미실행 가상 예시입니다.** 아래 대상·계정·객체·근거 참조와 관찰 결과는 모두 출력 형식을 설명하기 위한 가정입니다. 실제 진단 결과나 재현 성공을 뜻하지 않습니다. 보고 생성기도 아직 구현되지 않았습니다.

| 항목 | 예시 값 |
|---|---|
| 검사 실행 | `example-run-001` |
| 대상/환경 별칭 | `example-target` / `example-test` |
| 사례 | `example-case-001` |
| 취약점 유형 | 다른 계정의 기존 객체에 대한 읽기 접근 권한 위반 |
| 예시 판정 | `CONFIRMED` — 가정값 |
| 예시 PoC 상태 | `documented` — 원 실행과 연결된 절차의 출력 형태 |
| 별도 재실행 | `not_run` — 수행하지 않음 |
| 심각도 | 미평가 |

## 1. 문제 설명

등록 기대 정책에서 A만 읽을 수 있도록 정한 기존 객체를 B 계정으로도 읽을 수 있었다고 가정한다. 정상 A 응답과 B 교차 응답이 같은 객체의 비자명 데이터를 포함하고, 주체 확인과 공유/위임 예외 확인까지 완료됐다고 가정한 예시다.

HTTP 200만으로 확정하지 않으며, 아래 조건별 근거를 함께 확인하는 형태다.

| 조건 | 예시 관찰/근거 |
|---|---|
| 기대 권한 | 등록 정책 `example-policy-001` revision 1에서 B 접근 금지, 공유/위임 예외 없음 |
| 실제 주체 | 서로 다른 A/B subject가 확인됐다고 가정. `example-identity-a`, `example-identity-b` |
| 기준 응답 | A가 자기 객체의 정상 실데이터를 읽었다고 가정. `example-evidence-owner` |
| 교차 응답 | B에게 같은 객체의 정상 실데이터가 반환됐다고 가정. `example-evidence-cross` |
| 비교·판정 | 반사/공통 템플릿을 배제했다고 가정. `example-comparison-001`, `example-verdict-001` |

## 2. 재현 전제

재현자는 허가된 로컬 등록 설정에서 다음 별칭의 실제 값을 확인한다. 보고서는 비밀번호·쿠키·토큰·실제 객체 값을 포함하지 않는다.

| 입력 | 의미 |
|---|---|
| `${REGISTERED_ORIGIN}` | 현재 허가된 대상 origin |
| `${RESOURCE_ID}` | 등록 자원 바인딩 `example-binding-owner-001` revision 1의 기존 A 객체 |
| `${SESSION_A}` / `${SESSION_B}` | 등록 인증 절차로 새로 생성하고 주체를 확인한 A/B 세션 |
| 동작 | `example-read-object` revision 1의 GET 동작 |

검사 허가·현재 기대 정책·객체 바인딩이 여전히 유효해야 한다. 과거 정책 결정·세션 generation·전송 준비 핸들을 재사용하지 않는다. B 자기 객체나 새 객체 생성은 요구하지 않는다.

## 3. PoC 재현 절차

1. 등록 인증/주체 확인 프로필로 A와 B가 서로 다른 실제 계정인지 확인한다.
2. A 세션으로 아래 등록 객체 GET을 수행한다. A의 정상 객체 데이터가 반환되는지 확인한다.
3. 목적지·객체를 그대로 유지하고 B 세션으로 같은 객체 GET을 비교한다. 교차 검사는 기존 access_compare 경로와 Policy/Gateway 통제를 사용한다.
4. 로그인 화면·오류 응답·입력 반사·공통 템플릿을 제외하고 같은 객체의 비자명 데이터가 B에게 반환되는지 확인한다.
5. 새 run의 정책·주체·요청·근거·비교·판정을 기록한다. 원 보고서의 판정이나 과거 응답을 새 실행 결과로 복사하지 않는다.

다음은 **실행 가능한 전체 HTTP 요청이 아닌 placeholder 템플릿**이다. 인증 설정은 등록된 실행 어댑터가 결합한다.

```text
기준 요청
GET ${REGISTERED_ORIGIN}/objects/${RESOURCE_ID}
인증 맥락: ${SESSION_A}
예시 원 실행 참조: example-attempt-owner → example-evidence-owner

교차 요청
GET ${REGISTERED_ORIGIN}/objects/${RESOURCE_ID}
인증 맥락: ${SESSION_B}
예시 원 실행 참조: example-attempt-cross → example-evidence-cross
```

실제 보고서에서는 Gateway의 원 실행에서 파생하고 Evidence에 저장한 등록 요청 레시피를 출력한다. 위 `/objects/` 경로도 이 문서의 허구 예시이며 실제 대상 경로로 추정해 사용하지 않는다.

## 4. 기대 결과와 예시 관찰

| 요청 | 등록 정책의 기대 | 예시에서 가정한 관찰 |
|---|---|---|
| A → A 객체 | 정상 객체 데이터 반환 | normal 응답·객체 데이터 확인 |
| B → 같은 A 객체 | 객체 데이터 접근 거부 | normal 응답·동일 객체 데이터 확인 |

예시 비교 신호는 `same_resource=yes`, `distinct_verified_subjects=yes`, `owner_normal_data=yes`, `cross_normal_data=yes`, `nontrivial_data_match=yes`, `reflection_excluded=yes`, `template_excluded=yes`로 가정한다. 응답 원문·개인정보·인증 값·캡처 핸들·HMAC 키를 보고서에 넣지 않는다.

## 5. 감사와 한계

- 정책 결정·전송 intent·원 실행 attempt·두 근거·완료 비교·판정이 연결되는 출력 형태를 예시로 든다. 이 가상 문서에는 검증 가능한 실제 journal이 없다.
- 실제 보고서는 sent/not_sent/unknown과 감사 누락을 구분한다. 레시피나 근거가 부족하면 PoC를 incomplete/unavailable로 남긴다.
- 이 문서는 재실행을 수행하지 않았고, 실제 취약점·성능·지원 범위를 입증하지 않는다.

## 6. 조치 검토 항목

인증된 요청 주체가 해당 객체를 읽을 수 있는지 서버의 객체별 접근 정책과 비교하는 지점을 점검한다. 대상 소스·구현 원인을 확인하지 않았으므로 특정 파일·SQL·코드 수정 위치는 제시하지 않는다.

이 출력 형식의 데이터 계약과 후속 검증은 [PoC 보고서 설계](../planning/poc-report-design.md)를 따른다.
