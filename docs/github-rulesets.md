# PR 승인 Bypass와 GitHub Ruleset 설정

이 문서는 `ABC2LAB/abc2lab-dast`의 **수동 설정 가이드**다. 정책의 정본은 [기여 안내](../CONTRIBUTING.md#리뷰-승인-bypass)다. 이 문서를 작성하면서 GitHub 설정·팀·멤버는 변경하지 않았다. 아래 설정과 동작 검증은 아직 완료되지 않았다.

## 현재 확인한 상태

2026-10-21 GitHub API GET 요청으로 확인했다.

- `main`의 기존 Branch Protection: 승인 1명, 오래된 승인 무효화, 필수 CI 14개와 최신 base 반영 요구, 리뷰 대화 해결, 관리자에게도 보호 적용. Force Push와 삭제는 금지되어 있다.
- 저장소 및 상위 조직의 적용 가능한 Ruleset 목록은 비어 있다. `pr-bypass` 팀의 존재·구성원·접근 권한과 관리자 UI의 실제 표시 항목은 확인하지 않았다.

이는 기존 설정을 읽은 결과이며 새 Bypass 정책의 적용 검증 결과가 아니다.

## 수동 설정 순서

1. 현재 Branch Protection과 저장소·조직·Enterprise의 적용 규칙, Bypass 목록을 기록한다. 새 보호를 활성화하고 검증하기 전에는 기존 Branch Protection을 삭제하지 않는다.
2. ABC2LAB 조직의 **Teams → New team**에서 `pr-bypass`를 준비한다. 이미 있으면 중복 생성하지 않고 아래 구성과 일치하는지 확인한다.
3. 저장소 **Settings → Rules → Rulesets → New branch ruleset**에서 아래 두 Ruleset을 각각 설정한다. 두 규칙 모두 `main`만 대상으로 선택하고 제외 패턴이 없는지 확인한다.
4. 두 규칙을 **Active**로 저장하고 실제 적용 대상·규칙·CI 목록을 다시 확인한다. UI 메뉴나 옵션 이름이 다르면 대응 항목을 확인하고 기록한다.
5. 별도 검증 저장소에서 같은 구성의 동작을 먼저 확인한 뒤 아래 전환 절차를 따른다. 검증표에는 검증 저장소와 실제 대상 저장소의 결과를 구분해 기록한다.

메뉴 경로는 GitHub UI에 따라 다를 수 있다. Ruleset 생성·Bypass 설정은 [GitHub 공식 가이드](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)를 따른다. 옵션이 보이지 않으면 플랜·저장소 공개 범위·관리 권한·팀 visibility를 확인할 항목으로 남기고 임의로 대체하지 않는다.

### A. Organization Team: pr-bypass

| 항목 | 설정 |
|---|---|
| 조직 / 팀 | `ABC2LAB` / `pr-bypass` |
| 구성원 | `sleepingman1222`, `mminjun`, `31-no3won` |
| 구성원 제외 | `jsang01` |
| Visibility | `Visible` 팀. `Secret` 팀은 Bypass 대상으로 사용할 수 없다. |
| 저장소 권한 | 기존 병합 권한을 확인한다. Bypass만으로 Write·Admin 권한이 부여되지는 않는다. |

상위·하위 팀, IdP 동기화 등으로 실제 유효 구성원이 늘어나지 않는지 확인한다. 계정의 조직 가입 상태, 팀 선택 가능 여부와 필요한 저장소 접근 권한도 확인한다. 조직 Owner 또는 허용된 팀 생성 권한자가 [팀 생성 절차](https://docs.github.com/en/organizations/organizing-members-into-teams/creating-a-team)에 따라 진행한다.

이 권한은 기술적으로 **PR 작성자가 본인인지 검사하지 않는다.** 팀 구성원은 다른 사람의 PR에서도 승인 조건을 우회할 수 있다. 정책상 자신의 PR에서만 사용하며, 권한이 없는 작성자의 PR은 승인 절차를 유지한다. 작성자 제한을 GitHub가 자동으로 강제한다고 설명하지 않는다.

### B. CI 보호 Ruleset: main-ci-safety

| 항목 | 설정 |
|---|---|
| 이름 / 대상 / Enforcement | `main-ci-safety` / `main` / `Active` |
| Bypass list | **비어 있음**. 팀·Repository Admin·Organization Owner·앱 등 어떤 actor도 추가하지 않는다. |
| Require a pull request before merging | 켬 |
| Required approvals | `0`명. UI가 토글 방식이면 승인 요구를 끄고 PR 필수는 유지한다. |
| Require review from Code Owners / 마지막 push 승인 | 끔. 이 Ruleset에 별도 승인 조건을 추가하지 않는다. |
| Require status checks to pass | 켬. 아래 14개를 모두 등록하고 가능하면 기대 제공자를 GitHub Actions로 지정한다. |
| Require branches to be up to date before merging | 켬. 기존 strict 조건을 유지한다. |
| Require conversation resolution before merging | 켬. PR 추가 옵션에 있으면 이 Ruleset의 PR 규칙 안에서 설정한다. |
| Block force pushes | 켬 |
| Restrict deletions | 켬 |

`Restrict updates`나 브랜치 잠금은 모든 정상 병합도 막을 수 있으므로 직접 push 금지의 대체 옵션으로 켜지 않는다. PR 필수 규칙으로 `main` 직접 push를 막는다. 삭제·Force Push 금지 대상은 `main`이며, 병합 후 작업 브랜치 정리 규칙은 유지한다.

CI 실패·미완료·누락이나 미해결 리뷰 대화가 있으면 Bypass 사용자도 병합할 수 없어야 한다. **`pr-bypass`를 이 Ruleset의 Bypass list에 추가하지 않는다.** 승인 Bypass와 CI 보호를 분리하기 위한 필수 조건이다.

#### 필수 CI 이름과 확인 근거

로컬 [.github/workflows/ci.yml](../.github/workflows/ci.yml)과 최근 [main push 실행](https://github.com/ABC2LAB/abc2lab-dast/actions/runs/39552099874), [PR 실행](https://github.com/ABC2LAB/abc2lab-dast/actions/runs/39551382747)을 대조했다. 두 실행 모두 아래 14개 job이 `success`였고 기존 Branch Protection의 필수 검사 이름도 일치했다.

```text
environment
module (abc2lab-app)
module (abc2lab-contracts)
module (abc2lab-evidence)
module (abc2lab-gateway)
module (abc2lab-host)
module (abc2lab-judge)
module (abc2lab-knowledge)
module (abc2lab-mcp-knowledge)
module (abc2lab-mcp-webdiag)
module (abc2lab-policy)
module (abc2lab-reasoner)
module (abc2lab-report)
module (abc2lab-webdiag)
```

`CI`는 workflow 이름이며 위 개별 job 이름 대신 등록하지 않는다. UI의 추가 버튼으로 실제 등록을 완료하고 저장 후 14개가 남아 있는지 확인한다. 기존 검사 제공자는 GitHub Actions(`app_id=15368`)였다. 제공자 선택이 UI에 없으면 확인 필요로 기록한다. Workflow 변경으로 검사 이름이 바뀌면 최근 PR 실행과 필수 목록을 함께 재확인한다. [규칙별 옵션 설명](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)을 참고한다.

### C. PR 승인 Ruleset: main-pr-approval

| 항목 | 설정 |
|---|---|
| 이름 / 대상 / Enforcement | `main-pr-approval` / `main` / `Active` |
| Require a pull request before merging | 켬 |
| Required approvals | `1`명 |
| Dismiss stale pull request approvals when new commits are pushed | 켬. 기존 조건을 유지한다. |
| Bypass list | Organization Team `ABC2LAB/pr-bypass`만 등록 |
| Bypass mode | **For pull requests only**. `Always allow`를 사용하지 않는다. |
| CI·대화 해결·Force Push·삭제 규칙 | `main-ci-safety`에서 강제하며 이 Ruleset에는 중복 추가하지 않는다. |

`.github/CODEOWNERS`의 네 계정과 리뷰 자동 요청을 유지한다. 리뷰 요청은 필수 승인 수와 별개이며 Bypass 사용 시에도 제거하지 않는다. 스키마·공통 규칙의 추가 담당자 승인과 Bypass 사유 기록은 [기여 안내](../CONTRIBUTING.md#스키마공통-규칙-변경의-승인)에 따라 병합자가 확인한다. 일반적인 승인 수 설정이나 CODEOWNERS만으로 모든 담당자별 추가 승인까지 자동 강제되지는 않는다.

### D. 기존 Branch Protection과 별도 우회 경로

Ruleset과 기존 Branch Protection은 함께 적용되고 더 엄격한 조건이 남는다. 따라서 기존 승인 1명 요구를 그대로 두면 새 `main-pr-approval`을 Bypass해도 기존 보호에 막힐 수 있다. 이는 [규칙 중첩 설명](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)에 따른 정상 동작이다.

1. 기존 보호를 그대로 유지한 채 두 Ruleset을 Active로 만들고, `main` 대상·빈 CI Bypass 목록·14개 CI·대화 해결·삭제/Force Push 금지가 모두 적용되는지 확인한다.
2. 별도 검증 저장소에서 같은 팀·유효 권한·workflow와 두 Ruleset을 구성하고, 기존 승인 요구가 중복되지 않는 상태로 아래 검증표의 허용·차단 동작을 먼저 확인한다. **승인 Bypass와 비권한자의 승인 요구까지 검증하기 전에는 기존 Branch Protection의 승인 조건도 완화하지 않는다.** 검증 저장소를 준비하거나 동일 구성을 확인할 수 없으면 전환을 보류하고 기존 보호를 유지한다.
3. 두 Ruleset의 동작 검증 증거와 대상 저장소의 설정 일치를 확인한 뒤, 기존 Branch Protection에서 **중복 승인 요구만** 제거할 수 있는지 확인한다. 기존 PR·CI·대화 해결·삭제/Force Push 보호는 유지한다. 분리해서 조정할 수 없다면 확인 필요로 남기고 기존 규칙을 유지한다.
4. 승인 중복을 해소한 실제 대상 저장소에서 계정별 병합 조건을 다시 확인한다. 검증 저장소에서의 성공을 실제 저장소의 검증 완료로 표시하지 않는다. 검증 실패 시 기존 승인 요구를 복구한다.
5. 전환 후 실제 보호가 모두 확인된 경우에만 기존 Branch Protection 전체 제거 또는 유지 여부를 결정한다. 모든 조건을 검증하기 전까지 기존 규칙 전체를 삭제하지 않는다. 새 정책에 불필요한 중복 승인 요구가 남지 않게 하되, 보호가 비는 구간을 만들지 않는다.

기존 승인 요구가 겹치는 동안 실제 대상 저장소에서 승인 없는 병합이 차단되는 것은 예상된 결과다. 이를 해결하려고 검증 전에 기존 보호를 지우거나 CI 보호에 Bypass를 추가하지 않는다.

Organization Owner, Repository Admin, custom role의 `bypass branch protections`·규칙 편집 권한, 조직/Enterprise 상위 규칙과 앱의 우회 경로를 별도로 점검한다. 기존 Branch Protection의 관리자 적용·Bypass 허용 목록도 확인한다. CI 보호를 우회하는 actor가 없어야 하며 `jsang01`이 다른 역할·팀·앱 경로로 승인 우회를 얻지 않는지 확인한다. 기존 보호의 관리자 기본 예외는 [보호 브랜치 설명](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)을 참고한다.

규칙을 편집할 수 있는 관리자가 보호 자체를 바꾸는 권한과, 현재 규칙을 유지한 채 PR에서 Bypass하는 권한은 별개다. 이 두 Ruleset이 관리자의 설정 변경까지 기술적으로 차단한다고 간주하지 않는다.

## 적용 후 GitHub 동작 검증 — 미완료

다음은 **예상 결과**이며 실제 확인 결과가 아니다. 검증 저장소와 실제 대상 저장소를 구분하고, 계정별 UI·적용 규칙·검사 결과와 확인 일시를 기록한다. 실제 대상의 차단 검증을 위해 `main` 직접 push·Force Push·삭제를 시도하거나 실패 CI를 우회 병합하지 않는다. 파괴적 검증은 별도 검증 저장소에서 수행한다.

| 조건 | 기대 결과 | 실제 검증 상태 |
|---|---|---|
| `sleepingman1222`의 본인 PR, 승인 0, CI 성공·대화 해결 | 승인 Bypass로 병합 가능 | 미실행 |
| `mminjun`의 본인 PR, 승인 0, CI 성공·대화 해결 | 승인 Bypass로 병합 가능 | 미실행 |
| `31-no3won`의 본인 PR, 승인 0, CI 성공·대화 해결 | 승인 Bypass로 병합 가능 | 미실행 |
| `jsang01`의 PR, 승인 0, CI 성공·대화 해결 | 본인은 병합 불가. 다른 권한자가 대신 Bypass하는 것도 정책상 허용하지 않음 | 미실행 |
| Bypass 미사용 일반 PR, 작성자 외 승인 1, CI 성공·대화 해결 | 병합 가능 | 미실행 |
| 모든 계정의 `main` 직접 push·Force Push·삭제 | 차단 | 미실행 |
| Bypass 사용자의 PR, 필수 CI 하나라도 실패·진행 중·누락 | 병합 차단 | 미실행 |
| Bypass 사용자의 PR, 미해결 리뷰 대화 존재 | 병합 차단 | 미실행 |
| 스키마·공통 규칙 변경 | 담당자별 추가 승인 또는 허용된 Bypass와 영향 범위·사유 기록 필요 | 미실행 |
| PR 생성 또는 Draft → Ready | CODEOWNERS 기반 작성자 외 팀원 리뷰 요청 유지 | 미실행 |

GitHub UI에서 0명 승인·PR 전용 Bypass·팀 선택·제공자 지정·관리자 적용 등이 예상과 다르면 확인한 화면과 미확인 항목을 남긴다. 문서 링크 확인이나 과거 CI 성공만으로 위 표를 완료 처리하지 않는다.
