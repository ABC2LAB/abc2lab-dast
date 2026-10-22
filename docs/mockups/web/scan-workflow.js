"use strict";

// Presentation-only state. No request in this flow contacts a target or service.
const coverageStates = {
  complete: { label: "확인 완료", color: "success" },
  limited: { label: "일부 확인", color: "warning" },
  unknown: { label: "전송 불명", color: "neutral" },
  blocked: { label: "정책 차단", color: "warning" },
  not_run: { label: "미실행", color: "neutral" },
  waiting: { label: "대기 중", color: "neutral" },
};
let preflightTimer = null;

function invalidatePreflight() {
  clearTimeout(preflightTimer);
  state.preflight = "idle";
}

function scopePreview() {
  return `<section class="scope-rules" aria-labelledby="scope-title">
    <div class="section-inline-heading"><h3 id="scope-title" class="subsection-title">범위와 보호 규칙</h3>${badge("등록 프로필 예시", "purple")}</div>
    <div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">경로</th><th scope="col">적용 규칙</th></tr></thead><tbody>
      <tr><td>GET /api/orders/{order_id}</td><td>${badge("읽기 검사", "purple")}</td></tr>
      <tr><td>/login · /api/auth/session</td><td>${badge("인증용 접근", "info")}</td></tr>
      <tr><td>/api/payments/* · /logout</td><td>${badge("접근 차단", "warning")}</td></tr>
    </tbody></table></div>
    <div class="scope-simulator">
      <div class="field"><label for="scope-method">메서드</label><select id="scope-method" aria-label="규칙 미리보기 메서드">${["GET", "POST"].map((method) => `<option ${state.scopeMethod === method ? "selected" : ""}>${method}</option>`).join("")}</select></div>
      <div class="field"><label for="scope-url">URL 규칙 미리보기</label><input id="scope-url" value="${escapeHtml(state.scopeInput)}" placeholder="/api/orders/example" maxlength="300"><small>예시: /login · /api/payments/example · 외부 URL</small></div>
      ${button("규칙 확인", "simulate-scope", "secondary", "search")}
    </div>
    <div id="scope-simulation-result" aria-live="polite">${state.scopeResult ? simulationResult() : '<p class="small-text muted">입력한 주소에 접속하지 않고, 목업의 고정 규칙과 비교합니다.</p>'}</div>
  </section>`;
}

function simulateScope() {
  let result;
  try {
    const target = targets.find((item) => item.id === state.form.target);
    const url = new URL(state.scopeInput, target.url);
    const authPath = ["/login", "/api/auth/session"].includes(url.pathname);
    const isReadPath = /^\/api\/(orders|customers|invoices|addresses|files|teams)\/[^/]+(?:\/(metadata|documents))?$/.test(url.pathname);
    if (url.origin !== target.url || url.username || url.password) result = ["danger", "등록 범위 밖 · 차단", "선택한 대상과 origin이 다른 주소는 이 진단에 포함되지 않습니다."];
    else if (url.search || url.hash) result = ["warning", "등록 대조 필요 · 미허용", "이 간단한 미리보기는 query·fragment를 해석하지 않습니다. 실행 허가를 의미하지 않습니다."];
    else if (authPath) result = ["warning", "인증용 접근", "등록된 로그인·세션 확인에만 사용하는 경로입니다. 취약점 검사 대상과 구분합니다."];
    else if (state.scopeMethod === "GET" && isReadPath) result = ["success", "읽기 검사 범위", "예시 등록 동작에 해당합니다. 실제 실행에는 계정·자원·정책의 요청별 검증이 필요합니다."];
    else result = ["danger", "보호 또는 미등록 동작 · 차단", "결제·로그아웃·쓰기 동작과 목록에 없는 경로는 이 예시 프로필에서 허용하지 않습니다."];
  } catch {
    result = ["danger", "주소 형식을 확인해 주세요", "올바른 경로나 http(s) URL을 입력하세요."];
  }
  state.scopeResult = result;
  document.querySelector("#scope-simulation-result").innerHTML = simulationResult();
}

function simulationResult() {
  const [color, title, description] = state.scopeResult;
  return `<div class="simulation-result ${color}">${icon(color === "success" ? "check" : "shield")}<div><strong>${title}</strong><p>${description}</p></div></div>`;
}

function preflightPanel() {
  const done = ["ready", "failed"].includes(state.preflight);
  const failed = state.preflight === "failed";
  const checks = [
    ["대상과 허용 범위", "선택한 등록 대상·읽기 동작 연결", false],
    ["계정과 주체", failed ? "평가 계정 B의 인증 프로필이 만료된 상황 예시" : `${accountLabel(state.form.owner)} / ${accountLabel(state.form.evaluated)} · 서로 다른 주체 예시`, failed],
    ["기대 접근 정책", "등록 정책·자원 연결과 유효기간 대조 예시", false],
    ["실행 한도", `최대 ${state.form.maxAttempts ?? 60}회 · ${state.form.maxDuration ?? 5}분 · 동시 요청 ${state.form.concurrency ?? 1}개인 예시 프로필`, false],
  ];
  return `<section class="preflight-card card" aria-label="시작 전 점검">
    <div class="preflight-header"><div><h3 class="subsection-title">시작 전 점검</h3><p>연결·인증·정책 확인 화면을 가상으로 재생합니다.</p></div>${badge(state.preflight === "ready" ? "준비됨 · 예시" : failed ? "확인 필요" : state.preflight === "checking" ? "점검 중" : "점검 전", state.preflight === "ready" ? "success" : failed ? "warning" : "neutral")}</div>
    <ul class="preflight-checks">${checks.map(([title, text, error]) => `<li class="preflight-check ${error ? "danger" : ""}">${icon(done ? error ? "alert" : "check" : "clock")}<div><strong>${title}</strong><small>${done ? escapeHtml(text) : "사전 점검 후 예시 결과가 표시됩니다."}</small></div><span class="check-status">${badge(done ? error ? "실패" : "확인" : "대기", done ? error ? "danger" : "success" : "neutral")}</span></li>`).join("")}</ul>
    <div class="preflight-controls"><label class="field" for="preflight-scenario">점검 상황 예시<select id="preflight-scenario"><option value="ready" ${state.preflightScenario === "ready" ? "selected" : ""}>정상 준비</option><option value="expired" ${state.preflightScenario === "expired" ? "selected" : ""}>평가 계정 인증 만료</option></select></label>${button(state.preflight === "checking" ? "점검 중…" : "사전 점검 (데모)", "check-preflight", "secondary", "check", state.preflight === "checking" ? "disabled" : "")}</div>
    <div id="preflight-message" class="scan-notice ${failed ? "warning" : ""}" role="${failed ? "alert" : "status"}">${icon(failed ? "alert" : "flask")}<div><strong>${failed ? "계정 프로필을 확인해야 시작할 수 있습니다" : "실제 연결 없이 점검 화면을 재생합니다"}</strong><p>${failed ? "정상 준비 예시로 바꿔 다시 점검하거나, 이전 단계에서 계정을 변경해 보세요." : "준비됨은 목업 상태입니다. 실제 로그인·인증·실행 허가를 증명하지 않습니다."}</p></div></div>
  </section>`;
}

function scanSetup() {
  const target = targets.find((item) => item.id === state.form.target);
  const retest = state.form.retestCaseId;
  let content;
  if (state.newStep === 1) {
    content = `<div class="form-section-title"><span class="step-number">01</span><div><h2>대상과 검사 범위를 선택하세요</h2><p>등록된 범위와 보호 규칙을 먼저 확인합니다.</p></div></div>
      <div class="field"><label for="scan-name">진단 이름 <span class="required">*</span></label><input id="scan-name" name="scanName" aria-label="진단 이름" required maxlength="60" value="${escapeHtml(state.form.name)}"></div>
      <fieldset class="field"><legend>등록된 대상</legend><div class="target-options">${targets.map((item) => `<label class="target-option ${state.form.target === item.id ? "selected" : ""}"><input type="radio" name="target" value="${item.id}" ${state.form.target === item.id ? "checked" : ""} ${retest && state.form.target !== item.id ? "disabled" : ""}><span class="target-avatar ${item.color}">${item.initials}</span><span><strong>${item.name}</strong><small>${item.url}</small></span>${badge("등록됨")}</label>`).join("")}</div></fieldset>
      <div class="scope-note">${icon("shield")}<div><strong>${retest ? `${escapeHtml(retest)} · 선택 사례만 다시 검사` : "수평 접근 권한 · 읽기 검사"}</strong><p>등록 계정과 기존 자원의 관찰을 비교하는 화면 예시입니다.</p></div></div>${scopePreview()}`;
  } else if (state.newStep === 2) {
    content = `<div class="form-section-title"><span class="step-number">02</span><div><h2>비교할 계정을 선택하세요</h2><p>소유자 A와 평가 계정 B의 신원을 구분합니다.</p></div></div>
      <div class="identity-diagram"><span class="identity-person">${icon("users")}<strong>소유자 A</strong><small>자기 자료 조회</small></span><span class="identity-line">같은 자원 비교 ${icon("arrow")}</span><span class="identity-person evaluated">${icon("users")}<strong>평가 계정 B</strong><small>다른 계정의 접근</small></span></div>
      <div class="field-row"><div class="field"><label for="owner-account">소유자 계정 A</label><select id="owner-account" name="owner">${accountOptions(state.form.owner)}</select></div><div class="field"><label for="evaluated-account">평가 계정 B</label><select id="evaluated-account" name="evaluated">${accountOptions(state.form.evaluated)}</select></div></div>
      <p id="account-error" class="form-error" role="alert" hidden>서로 다른 계정 프로필을 선택해 주세요.</p>
      <div class="info-note">${icon("info")}<p>등록된 인증 프로필 예시입니다. 비밀번호·토큰을 입력할 필요가 없습니다.</p></div>`;
  } else if (state.newStep === 3) {
    content = `<div class="form-section-title"><span class="step-number">03</span><div><h2>모델과 실행 한도를 정하세요</h2><p>이번 진단에만 적용되는 설정입니다. API 키는 저장하지 않습니다.</p></div></div>${scanSettingsPanel()}${scanLocalConfigSummary()}`;
  } else {
    content = `<div class="form-section-title"><span class="step-number">04</span><div><h2>사전 점검 후 진단을 시작하세요</h2><p>설정 변경 시 다시 점검합니다.</p></div></div><div class="review-target">${targetCell(target)}</div>
      <dl class="review-list"><div><dt>진단 이름</dt><dd>${escapeHtml(state.form.name)}</dd></div><div><dt>검사 범위</dt><dd>${retest ? `${escapeHtml(retest)} · 수정 확인` : "등록된 읽기 접근 권한 검사"}</dd></div><div><dt>계정 비교</dt><dd>${accountLabel(state.form.owner)} → ${accountLabel(state.form.evaluated)}</dd></div><div><dt>모델</dt><dd>${escapeHtml(scanSettingsConfig().model)} · ${state.form.provider === "external" ? "외부 / 내부 API" : "로컬 Ollama"}</dd></div><div><dt>실행 한도</dt><dd>${state.form.maxAttempts ?? 60}회 · ${state.form.maxDuration ?? 5}분 · 동시 ${state.form.concurrency ?? 1}개</dd></div></dl>
      ${retest ? `<div class="field mt-16"><label for="retest-scenario">수정 확인 결과 예시</label><select id="retest-scenario"><option value="present" ${state.form.retestScenario === "present" ? "selected" : ""}>같은 문제 다시 확인</option><option value="not-reproduced" ${state.form.retestScenario === "not-reproduced" ? "selected" : ""}>기존 경로에서 미재현</option><option value="unverified" ${state.form.retestScenario === "unverified" ? "selected" : ""}>신원 근거 확인 불가</option></select><small>실제 검사 결과를 고르는 기능이 아닌 목업 시연용 선택입니다.</small></div>` : ""}
      <div class="mt-24">${preflightPanel()}</div><label class="checkbox-row"><input type="checkbox" name="confirmed" required><span>위 대상·계정·모델·실행 범위를 확인했습니다.</span></label>`;
  }
  return `${heading(retest ? "수정 확인 진단" : "새 진단 시작", "범위와 계정을 확인하고 가상 진단 흐름을 둘러보세요.", button("닫기", "go-scans", "ghost", "close"))}
    ${retest ? `<div class="retest-banner">${icon("clock")}<div><strong>${escapeHtml(state.form.sourceRunId)} → 새 진단</strong><p>${escapeHtml(retest)}의 이전 결과를 유지하고 새 근거를 연결합니다. ${button("전체 진단으로 전환", "clear-retest", "ghost small")}</p></div></div>` : ""}
    <div class="stepper">${["대상과 범위", "계정 프로필", "모델·실행 설정", "사전 점검"].map((label, index) => `<div class="stepper-item ${index + 1 === state.newStep ? "active" : index + 1 < state.newStep ? "complete" : ""}"><span>${index + 1 < state.newStep ? icon("check") : index + 1}</span><strong>${label}</strong></div>`).join("")}</div>
    <div class="wizard-grid"><form id="new-scan-form" class="card form-card"><div class="card-body">${content}</div><div class="form-actions">${state.newStep > 1 ? button("이전", "previous-step", "ghost", "left") : '<span class="muted small-text">가상 데이터 · 대상 요청 없음</span>'}<button class="button primary" type="submit" ${state.newStep === 4 && state.preflight !== "ready" ? "disabled" : ""}>${state.newStep === 4 ? "진단 시작" : "다음 단계"}${icon(state.newStep === 4 ? "scan" : "arrow")}</button></div></form>
    <aside class="card summary-card"><div class="card-body"><span class="eyebrow">SCAN SUMMARY</span><h2>진단 요약</h2><div class="summary-target">${targetCell(target)}</div><div class="summary-line"><span>등록된 동작</span><strong>${target.endpoints}개</strong></div><div class="summary-line"><span>이번 검사</span><strong>${retest ? "선택 사례 1개" : "읽기 접근 권한"}</strong></div><div class="summary-line"><span>계정 프로필</span><strong>${target.profile}</strong></div><div class="summary-line"><span>선택 모델</span><strong>${escapeHtml(scanSettingsConfig().model)}</strong></div><div class="summary-line"><span>예상 데모 시간</span><strong>약 10초</strong></div><hr><div class="summary-tip">${icon("info")}<p>등록된 동작 수와 실제 검사한 항목 수를 구분합니다. 모든 결과는 화면 검토용 예시입니다.</p></div></div></aside></div>`;
}

function findingsForRun(run) {
  // This demo publishes verdicts only on completion. Stopping cannot create a
  // verdict from progress or turn an interrupted retest into identity failure.
  if (["running", "stopped"].includes(run.status)) return [];
  if (run.retestCaseId) {
    const original = { ...run.originalFinding, time: "11:00:10" };
    if (run.retestScenario === "unverified") return [{ ...original, value: "undecidable", severity: "미평가", title: "현재 계정의 신원 근거가 부족해 확인하지 못했습니다", retestOutcome: "unverified" }];
    if (run.retestScenario === "not-reproduced") return [{ ...original, value: "undecidable", severity: "미평가", title: "이번 조건에서 기존 문제가 재현되지 않았습니다", retestOutcome: "not-reproduced" }];
    return [{ ...original }];
  }
  const confirmed = findings.filter((item) => item.value === "confirmed").slice(0, run.count);
  const others = findings.filter((item) => item.value !== "confirmed" && (run.count > 0 || item.value === "allowed"));
  return findings.filter((item) => confirmed.includes(item) || others.includes(item));
}

function coverageRows(run) {
  const activeOrStopped = ["running", "stopped"].includes(run.status);
  const cases = activeOrStopped ? run.retestCaseId ? [run.originalFinding] : findings : findingsForRun(run);
  const rows = cases.map((item) => {
    const unverified = item.retestOutcome === "unverified";
    const status = unverified || item.value === "suspected" ? "limited" : item.retestOutcome === "not-reproduced" ? "complete" : item.value === "undecidable" ? "unknown" : "complete";
    return { id: item.id, method: "GET", path: item.path, title: item.resource, status, item,
      reason: item.retestOutcome === "not-reproduced" ? "기존 재현 경로에서 교차 자료가 관찰되지 않음. 전체 취약점 부재·수정 완료는 미확정." : unverified ? "현재 평가 계정의 신원 근거 확인 불가" : item.value === "suspected" ? "기대 정책 미등록 · 금지 여부 추가 확인 필요" : item.value === "undecidable" ? "교차 요청 전송 불명 · 응답 근거 미확보" : item.value === "allowed" ? "등록된 공유 정책 검증 · 비교 전송 성공을 주장하지 않음" : "등록 정책·서로 다른 주체·실데이터 비교 근거 확인",
      signals: unverified ? ["미확인", "미실행", "확인"] : item.value === "allowed" ? ["해당 없음", "해당 없음", "확인"] : ["확인", item.value === "undecidable" ? "불명" : "확인", item.value === "suspected" ? "미확인" : "확인"] };
  });
  if (!run.retestCaseId) rows.push(
    { id: "CHECK-007", method: "GET", path: "/api/payments/{payment_id}", title: "결제 동작", status: "blocked", reason: "보호 규칙으로 접근 차단 · 대상 요청을 보내지 않은 예시", signals: ["미실행", "미실행", "차단"] },
    { id: "CHECK-008", method: "GET", path: "/api/exports/{export_id}", title: "내보내기 자료", status: "not_run", reason: "이 예시 진단의 작업 예산으로 진행하지 못함 · 안전 여부 미평가", signals: ["미실행", "미실행", "미확인"] },
  );
  if (run.status === "running" || run.status === "stopped") {
    const completed = run.stage < 2 ? 0 : Math.floor((run.progress / 100) * rows.length);
    rows.forEach((row, index) => {
      if (row.status === "blocked") return;
      if (index >= completed) Object.assign(row, { status: run.status === "stopped" ? "not_run" : "waiting", reason: run.status === "stopped" ? "사용자 중단으로 확인하지 못한 항목 · 진단 완료로 집계하지 않음" : "가상 작업 대기 중 · 아직 확인된 근거 없음", signals: ["미확인", "미확인", "미확인"] });
    });
  }
  return rows;
}

function coverageSignal(label) {
  const ok = label === "확인";
  return `<span class="signal-cell ${ok ? "" : "neutral"}">${icon(ok ? "check" : label === "차단" ? "shield" : "help")}${label}</span>`;
}

function coverageDetail(row, run) {
  const canOpen = row.item && run.status !== "running" && findingsForRun(run).some((item) => item.id === row.id);
  const send = row.status === "waiting" || row.status === "not_run" ? "실행 근거 미확인" : row.status === "blocked" ? "미전송 예시" : row.status === "unknown" ? "교차 요청 불명" : row.item?.value === "allowed" || row.item?.retestOutcome === "unverified" ? "비교 전송 주장 없음" : "기준·교차 전송 예시";
  return `<aside class="card coverage-detail" aria-label="선택한 검사 상세"><span class="eyebrow">SELECTED CHECK</span><h3>${escapeHtml(row.title)}</h3>${badge(coverageStates[row.status].label, coverageStates[row.status].color)}<p class="small-text">${escapeHtml(row.reason)}</p><dl class="detail-meta"><dt>검사</dt><dd>읽기 접근 권한</dd><dt>계정</dt><dd>${accountLabel(run.owner || "buyer-a")} → ${accountLabel(run.evaluated || "buyer-b")}</dd><dt>전송 상태</dt><dd>${send}</dd><dt>판정</dt><dd>${canOpen ? verdictBadge(row.item.value) : "판정 없음"}</dd></dl><div class="coverage-reference">${escapeHtml(run.id)} / ${escapeHtml(row.id)}<br>가상 작업·근거 참조<br>실제 원문·인증 값 없음</div>${canOpen ? `<a class="button secondary" href="#finding/${row.id}/${run.id}">${icon("arrow")}판정 근거 보기</a>` : '<p class="small-text muted">확인된 사례가 생기면 근거 상세로 연결됩니다.</p>'}<div class="coverage-legend"><span class="small-text muted">행을 선택해 미완료 사유를 확인하세요.</span><span class="small-text muted">처리 상태와 취약점 판정은 별개입니다.</span></div></aside>`;
}

function coverageContent(run) {
  const rows = coverageRows(run);
  const filtered = rows.filter((row) => (state.coverageFilter === "all" || state.coverageFilter === "gaps" && row.status !== "complete" || row.status === state.coverageFilter) && `${row.path} ${row.title} ${row.id}`.toLowerCase().includes(state.coverageQuery.toLowerCase()));
  const selected = filtered.find((row) => row.id === state.coverageSelected) || filtered[0];
  return `<div class="coverage-layout"><section class="card"><div class="card-header"><h2 class="section-title">경로별 확인 범위<span class="section-count">${filtered.length}</span></h2><span class="small-text muted">GET · 읽기 검사</span></div>${filtered.length ? `<div class="table-wrap"><table class="data-table coverage-table"><thead><tr><th scope="col">검사 경로</th><th scope="col">기준 관찰 A</th><th scope="col">교차 관찰 B</th><th scope="col">정책 근거</th><th scope="col">처리 상태</th></tr></thead><tbody>${filtered.map((row) => `<tr class="${selected.id === row.id ? "coverage-row-selected" : ""}"><td class="coverage-path"><button type="button" class="coverage-select" data-action="select-coverage" data-value="${row.id}" aria-pressed="${selected.id === row.id}">${escapeHtml(row.path)}<small>${escapeHtml(row.id)} · ${escapeHtml(row.title)}</small></button></td>${row.signals.map((label) => `<td>${coverageSignal(label)}</td>`).join("")}<td>${badge(coverageStates[row.status].label, coverageStates[row.status].color)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty-state">${icon("search")}<h3>일치하는 검사 항목이 없습니다</h3><p>검색어나 처리 상태 필터를 바꿔 보세요.</p>${button("범위 필터 초기화", "reset-coverage", "secondary small")}</div>`}<div class="table-caption">${filtered.length} / ${rows.length}개 작업 · 실제 요청 수가 아닙니다.</div></section>${selected ? coverageDetail(selected, run) : ""}</div>`;
}

function coverage() {
  const requested = allRuns().find((run) => run.id === getRoute().id);
  if (requested) state.resultRun = requested;
  const run = state.resultRun;
  const rows = coverageRows(run);
  const count = (status) => rows.filter((row) => row.status === status).length;
  const gaps = rows.length - count("complete");
  return `${taskSectionHeading("검사 범위", "확인한 항목과 차단·미실행·전송 불명 사유를 함께 살펴보세요.")}
    <section class="coverage-summary"><div><span class="eyebrow">COVERAGE · DEMO</span><h2>선택한 ${rows.length}개 작업 중 ${count("complete")}개 확인 완료</h2><p>등록된 동작 ${run.target.endpoints}개와 구분한 이번 검사 계획입니다. 발견하지 못한 경로와 웹 전체의 검사율은 알 수 없습니다.</p></div><div class="coverage-stats"><div><span>확인 완료</span><strong>${count("complete")}개</strong></div><div><span>추가 확인·전송 불명</span><strong>${count("limited") + count("unknown")}개</strong></div><div><span>정책 차단</span><strong>${count("blocked")}개</strong></div><div><span>미실행·대기</span><strong>${count("not_run") + count("waiting")}개</strong></div></div><div class="coverage-bar" role="img" aria-label="전체 ${rows.length}개 중 확인 완료 ${count("complete")}개, 추가 확인 또는 미완료 ${gaps}개">${Object.keys(coverageStates).filter((status) => count(status)).map((status) => `<span class="${status === "limited" ? "blocked" : ["not_run", "waiting"].includes(status) ? "pending" : status}" style="flex:${count(status)}"></span>`).join("")}</div><p>완료는 해당 확인 절차의 처리를 뜻하며, 취약점 없음이나 전체 서비스의 안전을 뜻하지 않습니다.</p></section>
    <div class="coverage-toolbar"><div class="filter-tabs" role="group" aria-label="검사 범위 필터">${[["all", "전체"], ["gaps", "추가 확인"], ["blocked", "차단"], ["unknown", "전송 불명"]].map(([value, label]) => `<button type="button" class="filter-tab ${state.coverageFilter === value ? "active" : ""}" data-action="coverage-filter" data-value="${value}" aria-pressed="${state.coverageFilter === value}">${label}</button>`).join("")}</div><label class="search-field compact">${icon("search")}<input id="coverage-search" aria-label="검사 경로 검색" placeholder="경로 또는 자원 검색" value="${escapeHtml(state.coverageQuery)}"></label></div><div id="coverage-content">${coverageContent(run)}</div>`;
}

function evidenceChain(item) {
  const missing = item.value === "undecidable";
  return `<section class="mt-24" aria-label="근거 연결"><div class="section-inline-heading"><h2 class="section-title">근거가 판정으로 연결된 흐름</h2><span class="small-text muted">합성 기록</span></div><div class="evidence-chain">${[["등록 정책", item.value === "suspected" ? "추가 확인 필요" : "사례·자원 연결", item.value === "suspected"], ["신원 근거", item.retestOutcome === "unverified" ? "확인 불가" : "계정·주체 대조", item.retestOutcome === "unverified"], ["관찰 근거", item.value === "allowed" ? "허용 정책으로 판단" : item.retestOutcome === "not-reproduced" ? "기존 경로에서 미재현" : missing ? "부족한 근거 보존" : "기준·교차 비교", missing && item.retestOutcome !== "not-reproduced"], ["최종 판정", verdicts[item.value].label, missing]].map(([label, text, pending], index) => `<div class="chain-step ${pending ? "pending" : "complete"}"><span class="step-number">${index + 1}</span><strong>${label}</strong><small>${text}</small></div>`).join("")}</div></section>`;
}

function retestBanner(run) {
  if (!run.retestCaseId) return "";
  const labels = { present: "이전과 같은 판정 예시", "not-reproduced": "이번 조건에서 미재현", unverified: "확인 불가" };
  return `<div class="retest-banner mt-16">${icon("clock")}<div><strong>수정 확인 · ${run.status === "stopped" ? "중단됨" : labels[run.retestScenario]}</strong><p><a class="text-link" href="#results/${run.sourceRunId}">${run.sourceRunId} 이전 결과</a> → ${run.id} · ${escapeHtml(run.retestCaseId)}<br>과거 결과를 유지합니다. 미재현은 수정 완료나 전체 취약점 부재의 증명이 아닙니다.</p></div></div>`;
}

function retestCard(item) {
  const run = reportContext().run;
  const history = allRuns().filter((entry) => entry.sourceRunId === run.id && entry.retestCaseId === item.id);
  if (item.value !== "confirmed") return "";
  return `<section class="card retest-card mt-24"><div><span class="eyebrow">VERIFY AGAIN</span><h2 class="section-title">이 사례를 다시 확인하세요</h2><p class="small-text muted">같은 대상과 사례를 선택한 새 가상 진단으로 이동합니다. 계정·설정은 다시 점검합니다.</p></div>${button("수정 확인 진단", "start-retest", "secondary", "scan")}<div class="small-text">${history.length ? history.map((entry) => `<p><a class="text-link" href="#${entry.status === "running" ? "scan" : "results"}/${entry.id}">${entry.id} · ${entry.status === "running" ? "진행 중" : entry.status === "stopped" ? "중단됨" : entry.retestScenario === "not-reproduced" ? "미재현 예시" : entry.retestScenario === "unverified" ? "확인 불가 예시" : "이전과 같은 판정 예시"}</a></p>`).join("") : "아직 연결된 수정 확인 진단이 없습니다."}</div></section>`;
}

function beginRetest() {
  if (state.run?.status === "running") { toast("진행 중인 진단을 먼저 완료하거나 중지해 주세요."); navigate(`scan/${state.run.id}`); return; }
  const run = reportContext().run;
  const item = selectedFinding();
  state.form = { name: `${item.resource} · 수정 확인`, target: run.target.id, owner: run.owner || "buyer-a", evaluated: run.evaluated || "buyer-b", ai: Boolean(run.ai), retestCaseId: item.id, sourceRunId: run.id, originalFinding: { ...item, retestOutcome: undefined }, retestScenario: "present" };
  state.preflightScenario = "ready";
  state.scopeResult = null;
  state.newStep = 1;
  invalidatePreflight();
  navigate("new-scan");
}

document.addEventListener("click", (event) => {
  const element = event.target.closest("[data-action]");
  if (!element || element.disabled) return;
  const action = element.dataset.action;
  if (action === "simulate-scope") simulateScope();
  else if (action === "check-preflight") {
    invalidatePreflight();
    state.preflight = "checking";
    render(false);
    preflightTimer = setTimeout(() => {
      state.preflight = state.preflightScenario === "ready" ? "ready" : "failed";
      if (getRoute().name === "new-scan" && state.newStep === 4) render(false);
    }, 500);
  } else if (action === "coverage-filter") { state.coverageFilter = element.dataset.value; render(false); }
  else if (action === "select-coverage") {
    state.coverageSelected = element.dataset.value;
    document.querySelector("#coverage-content").innerHTML = coverageContent(state.resultRun);
    document.querySelector(`.coverage-select[data-value="${state.coverageSelected}"]`)?.focus({ preventScroll: true });
  } else if (action === "reset-coverage") { state.coverageFilter = "all"; state.coverageQuery = ""; render(false); }
  else if (action === "start-retest") beginRetest();
  else if (action === "clear-retest") { delete state.form.retestCaseId; delete state.form.sourceRunId; delete state.form.originalFinding; state.newStep = 1; invalidatePreflight(); render(); }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "coverage-search") {
    state.coverageQuery = event.target.value;
    document.querySelector("#coverage-content").innerHTML = coverageContent(state.resultRun);
  } else if (event.target.id === "scope-url") { state.scopeInput = event.target.value; state.scopeResult = null; document.querySelector("#scope-simulation-result").textContent = "입력이 바뀌었습니다. 규칙을 다시 확인하세요."; }
});

document.addEventListener("change", (event) => {
  if (event.target.id === "scope-method") { state.scopeMethod = event.target.value; state.scopeResult = null; document.querySelector("#scope-simulation-result").textContent = "메서드가 바뀌었습니다. 규칙을 다시 확인하세요."; }
  else if (event.target.id === "preflight-scenario") { state.preflightScenario = event.target.value; invalidatePreflight(); render(false); }
  else if (event.target.id === "retest-scenario") { state.form.retestScenario = event.target.value; invalidatePreflight(); render(false); }
});

document.addEventListener("keydown", (event) => {
  if (event.target.id === "scope-url" && event.key === "Enter") {
    event.preventDefault();
    simulateScope();
  }
});
