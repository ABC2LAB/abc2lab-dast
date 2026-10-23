# Design

## Source of truth
- Status: Draft — ARTEX의 화면 구성·스타일을 ABC2LAB 목업에 재구현하는 사용자 리뷰용 시안. 실제 프런트엔드 프레임워크 확정이 아니다.
- Last refreshed: 2026-10-23
- Primary product surfaces: localhost 웹의 진단 설정·사전 점검·진행·검사 범위·자산 그래프·지식 그래프(KG)·진단 흐름·결과·근거/PoC·수정 확인.
- Evidence reviewed: [배포 설계](docs/planning/local-deployment.md), [API 규격](docs/planning/s1-api-spec.md), [PoC 예시](docs/examples/s1-poc-report.example.md), [현재 구현 상태](docs/planning/s1-development-status.md).
- Visual reference: [jiwoochris/artex-global](https://github.com/jiwoochris/artex-global), commit `fdfb7a17b7da5e2de716c0e98475ec77a41c64c6`의 dashboard/tasks/sessions 화면. 사용자가 원본 React 이식 대신 현재 목업의 화면·스타일 재구현을 선택했다.
- 기존 목업의 화면·가상 Atlas Shop 데이터를 유지하며 시각 방향만 재구성한다. 원본 코드·브랜드 로고·이미지 파일을 저장소에 복사하지 않는다.
- 참고 출처·적용 대응·유지한 제품 경계는 [ARTEX UI 적용 기록](docs/mockups/web/artex-ui-adaptation.md)에 기록한다.
- 추가 참고: 사용자가 첨부한 '주요 화면 예시'의 대시보드·Knowledge Graph·취약점 목록·상세 정보 4개 구성. 화면 요소를 현재 작업 중심 흐름에 통합하며 원본의 전역 메뉴·브랜드를 복사하지 않는다.

## Brand
- Personality: 차분하고 명료한 보안 분석 작업 공간.
- Trust signals: 근거·판정 이유·불확실성을 같은 화면에서 확인한다.
- Avoid: 과장된 안전 점수, 해커 터미널 장식, 보안 완료로 오인시키는 녹색 표현.

## Product goals
- Goals: 첫 사용자가 대상 선택부터 진단·결과·재현 절차까지 스스로 이동한다.
- Non-goals: 실제 진단·LLM/DB 연결·성능 증명·최종 프런트엔드 구현.
- Success signals: 주요 동작이 클릭되고, 중지·실패·판단불가 상태와 예시 데이터를 구분한다.

## Personas and jobs
- Primary personas: 웹 서비스 보안 담당자와 진단 결과를 검토하는 개발자.
- User jobs: 등록 대상 진단, 진행 확인/중지, 근거 검토, 보고서 공유, 모델 설정.
- Key contexts of use: 데스크톱 localhost 웹, 팀 회의의 화면 시연.

## Information architecture
- Primary navigation: 개요, 진단 작업. 결과·그래프를 전역 메뉴로 나누지 않는다.
- 개요에는 새 진단 버튼을 두지 않는다. 새 작업은 진단 작업 목록에서 시작한다.
- 전역 검색은 작업 ID·이름·대상을 찾고 해당 작업 상세로 이동한다. 작업 목록은 검색·상태 필터·작업 ID·명시적인 열기 동작을 제공한다.
- Core routes/screens: overview, scans, new-scan, scan, coverage, results, finding, assets, knowledge, flow, reproduction, report.
- 중심 흐름: 작업 생성 → 해당 작업 상세. 상세 상단에 작업명·대상·상태·진행률을 유지하고 요약 / 그래프 / 취약점·판정 / 재현 현황 / 검사 범위 / 보고서·설정을 전환한다. 그래프 안에서는 자산·KG·진단 흐름을 전환한다.
- 상세의 모든 자료와 링크는 URL의 작업 ID에 귀속된다. 다른 작업으로 전환하려면 작업 목록으로 돌아간다. 완료·중단 뒤에도 같은 상세 페이지에서 검토한다.
- 새 진단: 대상·범위 → 계정 → 모델·실행 설정 → 사전 점검. 별도 설정 메뉴와 모델 연결의 사용 안 함 선택지는 제거한다.
- Content hierarchy: 현재 상태 → 필요한 행동 → 판정 이유/근거 → 세부 기록.

## Design principles
- 상태와 다음 행동을 한눈에 보이게 한다.
- 판정과 심각도를 구분하며, 판단불가를 취약점 없음으로 바꾸지 않는다.
- 정책상 접근 허용은 전체 시스템 안전 또는 실제 HTTP 성공을 의미하지 않는다.
- 검사 범위는 선택한 작업을 분모로 표시하고, 등록된 동작 수·웹 전체 검사율과 구분한다. 미실행·차단·전송 불명 사유를 보존한다.
- 사전 점검·URL 규칙 미리보기는 로컬 가상 결과다. 점검 실패는 시작을 막고 대상·계정 변경 시 점검을 다시 수행한다.
- 수정 확인은 과거 결과와 연결된 별도 가상 진단이다. 과거 근거를 유지하고 미재현을 수정 완료로 단정하지 않는다.
- 재현 현황은 현재 작업의 기준·교차 비교 처리와 사유를 보여준다. 취약점 확정 전 후보를 확정 결과로 표시하지 않는다. PoC 문서화·저장 기록 재생·새 수정 확인 진단을 구분하고, 문서화된 PoC가 별도로 실행 중인 것처럼 표시하지 않는다.
- 자산 그래프는 웹 표면 구조, KG는 계정·자원·정책·근거 관계, 진단 흐름은 스캐너의 작업·실행·판정 순서를 표시한다. 실제 업무 흐름과 구분한다.
- 그래프의 등록·관찰·추론·미확인과 취약점 판정을 구분한다. 노드·관계 선택, 부분 펼치기, 필터, 확대·이동, 흐름 재생은 저장된 합성 자료만 표시한다.
- 자동 진행 갱신은 선택 노드·관계·탭의 키보드 초점과 스크롤을 보존한다. 보조기기에는 단계가 바뀔 때 상태를 안내하고 같은 단계를 반복 공지하지 않는다.
- 이 목업의 판정은 완료 시에만 발행한다. 중단으로 판정이나 신원 실패·PoC를 만들지 않는다. 진행률로 확정 결과를 추정하지 않으며, 부분 완료의 제한 사유를 결과 본문에도 표시한다.
- 그래프 검색·필터·주변 연결 보기의 표시 경로 수를 실제 필터 결과와 함께 갱신한다. 작업 전체의 차단·미실행 수와 현재 표시 수를 구분한다.
- 그래프는 전체 화면 폭과 100% 배율을 기본으로 사용한다. 유형 아이콘·충분한 제목 폭·상태 문구를 함께 표시하고, 상세 정보는 캔버스 아래에 둔다. 의미별 영역 제목과 단계 번호로 읽는 순서를 안내한다.
- KG는 계정·대상/정책·근거·판정의 핵심 관계를 먼저 표시하며 역할·미검증 가설은 세부 관계로 펼친다. 자산은 ARTEX의 계층·묶음 노드를 참고해 도메인 → 웹 서비스 → 경로 그룹 → 엔드포인트로 표시한다. 근거 없는 페이지·자원 관계를 만들지 않는다.
- 자산의 엔드포인트는 메서드·경로 템플릿으로 구분하고 첫 경로 구간으로 묶는다. 기본 4개에 대표·미확인·차단·미실행 항목을 포함하며 나머지는 묶음 노드로 펼친다. 검색·검사 상태 필터는 접힌 항목도 찾고 상위 계층을 유지한다. 숨긴 수·필터 결과·작업 전체 수를 구분한다.
- 자산 상세에는 origin·메서드·경로 변수 이름·가상 출처·처리 사유·연결된 판정을 표시한다. 발견/등록된 경로라는 사실이 HTTP 전송·비교 완료·실제 페이지 관계를 증명하지 않는다. IP·프레임워크·응답 코드도 근거 없이 생성하지 않는다.
- 대시보드는 탐색 페이지·수집 API·경로 변수 이름·진단 후보 지표, 작은 웹 구조 그래프와 최근 활동을 제공한다. 지표는 명시적 합성 탐색 자료와 표시한 작업에서 계산한다. 등록만 된 차단·미실행 경로를 발견 페이지로 추정하지 않는다.
- KG는 사용자·역할→페이지→엔드포인트→자원의 '웹 구조'와 계정·정책·Evidence·Verdict의 '판정 근거'를 전환한다. 페이지 관계는 명시한 합성 탐색 fixture에서만 가져온다. 발견 관계로 신원·전송·접근 권한을 확정하지 않는다.
- 작업의 웹 구조 KG는 개요와 같은 유형별 색상의 원형 노드·곡선 연결을 사용한다. 원 옆에 유형·이름·관계 상태를 표시하고 전체 경로와 출처는 선택 상세에서 확인한다. 검색·펼치기·키보드·확대 조작은 유지한다.
- 취약점 목록에는 ID·검사 유형·심각도·판정·설명/경로·기록일을 표시한다. 후보·판정 발행·확인된 취약점·오탐 검토 기록을 구분하며, 오탐 데이터가 없는 현재 목업에서 ALLOWED/UNDECIDABLE을 오탐으로 집계하지 않는다.
- 상세는 유형·설명·관련 엔드포인트·재현/검토 단계와 합성 요청/응답 형식을 같은 화면에 제공한다. 실제 발견 시각이 없어 기록일을 사용한다. 요청 형식은 실행하지 않으며 전송 불명·신원 미확인·정책 허용 사례에 성공 응답을 만들지 않는다.
- 선택한 연결을 강조하고 반복 관계 라벨은 필요할 때 표시한다. 자산의 경로 그룹은 접기/펼치기, 전체 펼치기, 기본 보기 복원을 제공하며 상세 정보는 기존처럼 그래프 아래에 둔다.
- Tradeoffs: 첫 목업은 가상 데이터·단순 라우팅으로 사용자 흐름 검토를 우선한다.

## Visual language
- Color: 밝은 회색 사이드바, 흰색 작업 영역, 검정색 주요 버튼·중성색 선택 상태. 확인된 취약점·의심·판단불가·접근 허용은 별도 의미 색과 문구를 유지한다.
- Typography: OS 기본 sans-serif와 한국어 폰트 fallback. 외부 폰트 다운로드 없음.
- Spacing/layout rhythm: 4/8px 간격, 24–32px 화면 여백, 넓은 데이터 표.
- Shape/radius/elevation: 8–12px 곡률, 얇은 중성색 구분선, 최소한의 그림자. 작업 영역은 외곽 배경과 구분하는 하나의 컨테이너로 표시한다.
- Motion: 진행률과 짧은 전환에만 사용. reduced-motion 지원.
- Overview: 홍보 배너 대신 활성 작업·최근 판정·검사 범위 지표, 최근 작업 표, 활동 기록을 우선한다. 상세의 모델 설정은 새 진단에 통합한다.
- Imagery/iconography: 로컬 inline SVG 아이콘. 장식용 이미지·외부 CDN 없음.

## Components
- Existing components to reuse: 현재 목업의 내비게이션, 카드, 상태 배지, 데이터 표, 필터, 진행 단계, 대화상자, 토스트.
- New/changed components: 수집 지표·웹 구조 미니 그래프·최근 활동, 작업 표·상태 필터·빠른 검색, 작업 상세 헤더·분할 탭·요약·재현 현황, KG 웹 구조/판정 근거 전환, 판정 요약 지표·확장 표·검토 단계·합성 요청/응답, URL 규칙 미리보기, 통합 모델·실행 설정, 사전 점검 목록, 검사 범위 표·선택 상세, 그래프 캔버스·상세·필터·재생, 근거 연결, 수정 확인 이력.
- Variants and states: complete/running/stopped, confirmed/suspected/undecidable/allowed.
- Token/component ownership: 검토용 CSS 변수와 순수 JS render 함수. 실제 서비스 모듈과 분리.

## Accessibility
- Target standard: WCAG 2.2 AA를 목표로 한 기본 키보드·가독성 검토. 인증된 적합성 평가는 아님.
- Keyboard/focus behavior: skip link, 명시적 label, focus-visible, native dialog와 Escape, route 변경 후 제목 초점.
- Contrast/readability: 색만으로 의미를 전달하지 않고 텍스트 배지와 아이콘을 함께 사용.
- Screen-reader semantics: landmark, 표 header, aria-live 토스트·진행 상태.
- Reduced motion and sensory considerations: prefers-reduced-motion에서 전환/애니메이션 억제.

## Responsive behavior
- Supported breakpoints/devices: 1440px 데스크톱 중심, 1024px·390px에서도 동작 확인.
- Layout adaptations: 좁은 화면은 메뉴 접기, 카드/근거 세로 배치, 표 영역 안에서 가로 스크롤.
- Touch/hover differences: hover 없이 모든 행동에 접근 가능.

## Interaction states
- Loading: 가상 진단 단계와 진행률; 실제 요청은 발생하지 않는다.
- Empty: 검색/필터 결과 없음과 새 진단 시작 행동.
- Error: 진단 중단·일부 확인 불가를 보존한다.
- Success: 가상 완료 후 결과 화면으로 이동.
- Disabled: 필요한 입력 전 다음 단계, 수행 중 중복 시작 제한.
- Offline/slow network: 로컬 정적 파일만 필요하며 모델·대상 통신 없음.

## Content voice
- Tone: 간결하고 설명적인 한국어. 내부 모듈명·wire 타입을 사용자 흐름에 노출하지 않는다.
- Terminology: 확인된 취약점, 의심, 판단불가, 정책상 접근 허용.
- Microcopy rules: 모든 화면에 데모 표시. 키·원문 응답·실계정은 사용하지 않는다.

## Implementation constraints
- Framework/styling system: docs/mockups/web의 HTML/CSS/JS, 외부 의존성 없음.
- Design-token constraints: CSS custom properties 한 곳에서 색·간격 정의.
- Performance constraints: 외부 자원·API fetch·추적기 없음. 가상 타이머만 사용.
- Compatibility constraints: 최신 Chromium 계열에서 우선 검토. UI 스택은 별도 결정.
- Test/screenshot expectations: 통합 설정→점검→진단·중지→그래프/범위/결과→근거→수정 확인을 검증한다. 그래프의 노드·관계·필터·이동·확대·흐름 재생, 키 비보관, 이력·다운로드·모바일과 외부 통신 0건을 확인한다.
- 이번 보강은 화면·가상 데이터만 포함한다. 실행 중 이상 감시는 고도화 과제로 남기며 서비스·공유 계약·실행 권한을 추가하지 않는다.

## Open questions
- [ ] 사용자 피드백 — 밝은 테마/시각 밀도/주 내비게이션 최종 확정.
- [ ] 팀 합의 — 실제 UI 프레임워크와 최종 브랜드·아이콘 확정.
- [ ] 담당자 협의 — 목업 화면을 실제 API에 연결할 때의 데이터·권한·오류 상태 매핑.
