"use strict";

const iconPaths = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  scan: '<path d="M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m8 0h3a2 2 0 0 0 2-2v-3M7 12h10m-5-5v10"/>',
  shield: '<path d="m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6l8-3Z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
  settings: '<path d="m9 3-1 3-3 1v4l2 1v3l-2 2 3 3 2-1h3l2 1 3-3-1-2v-3l2-1V7l-3-1-1-3Z"/><circle cx="12" cy="11" r="3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  left: '<path d="M19 12H5m6-6-6 6 6 6"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
  download: '<path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M15 8V3H3v13h5"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a18 18 0 0 1 0 18 18 18 0 0 1 0-18Z"/>',
  users: '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 4v2"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  activity: '<path d="M2 12h5l3-8 4 16 3-8h5"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 4 2c-1 .7-1.5 1-1.5 2M12 16h.01"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  flask: '<path d="M9 3h6m-5 0v6l-6 9a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3l-6-9V3M7 15h10"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
  server: '<rect x="3" y="3" width="18" height="8" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 7h.01M7 17.5h.01M11 7h6m-6 10.5h6"/>',
  file: '<path d="M14 2H5v20h14V7l-5-5Z"/><path d="M14 2v6h5M8 12h8m-8 4h5"/>',
  sparkle: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>',
  alert: '<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5m0 3h.01"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18"/>',
};
const icon = (name, extra = "") => `<svg class="icon ${extra}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[name] || iconPaths.file}</svg>`;
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
const verdicts = {
  confirmed: { label: "확인된 취약점", short: "확인됨", color: "danger" },
  suspected: { label: "의심", short: "의심", color: "warning" },
  undecidable: { label: "판단불가", short: "판단불가", color: "neutral" },
  allowed: { label: "정책상 접근 허용", short: "접근 허용", color: "info" },
};
const findings = [
  { id: "CASE-001", value: "confirmed", severity: "높음", title: "다른 사용자의 주문 정보를 조회할 수 있습니다", path: "/api/orders/{order_id}", resource: "주문 정보", policy: "주문 소유자만 조회 가능", time: "10:42:18" },
  { id: "CASE-002", value: "confirmed", severity: "높음", title: "계정 식별자를 바꾸면 다른 사용자의 프로필이 노출됩니다", path: "/api/customers/{customer_id}", resource: "구매자 프로필", policy: "본인 프로필만 조회 가능", time: "10:42:26" },
  { id: "CASE-003", value: "suspected", severity: "검토 필요", title: "다른 사용자의 청구서 데이터가 포함된 것으로 보입니다", path: "/api/invoices/{invoice_id}", resource: "청구서", policy: "등록된 접근 정책이 없어 추가 확인 필요", time: "10:42:37" },
  { id: "CASE-004", value: "undecidable", severity: "미평가", title: "교차 요청의 전송 상태를 확인할 수 없습니다", path: "/api/addresses/{address_id}", resource: "배송지 정보", policy: "배송지 소유자만 조회 가능", time: "10:42:41" },
  { id: "CASE-005", value: "allowed", severity: "참고", title: "공유된 팀 자료에 대한 접근이 정책상 허용됩니다", path: "/api/teams/{team_id}/documents", resource: "팀 공유 자료", policy: "등록된 팀 구성원의 조회를 허용", time: "10:42:48" },
  { id: "CASE-006", value: "confirmed", severity: "중간", title: "비공개 첨부파일의 메타데이터에 접근할 수 있습니다", path: "/api/files/{file_id}/metadata", resource: "첨부파일 메타데이터", policy: "파일 소유자만 조회 가능", time: "10:42:52" },
];
const targets = [
  { id: "atlas", name: "Atlas Shop", url: "https://shop.atlas.test", initials: "AS", color: "purple", profile: "구매자 계정 2개", endpoints: 24 },
  { id: "staging", name: "Atlas Shop · Staging", url: "https://staging.atlas.test", initials: "ST", color: "info", profile: "구매자 계정 2개", endpoints: 18 },
  { id: "partner", name: "Partner Portal", url: "https://partners.atlas.test", initials: "PP", color: "success", profile: "파트너 계정 2개", endpoints: 16 },
];
const historicalRuns = [
  { id: "RUN-004", name: "주문·계정 접근 권한 진단", target: targets[0], status: "complete", date: "2026.10.22 10:40", duration: "2분 34초", count: 3 },
  { id: "RUN-003", name: "스테이징 정기 진단", target: targets[1], status: "complete", date: "2026.10.21 16:20", duration: "1분 48초", count: 0 },
  { id: "RUN-002", name: "파트너 문서 권한 점검", target: targets[2], status: "partial", date: "2026.10.21 14:05", duration: "1분 12초", count: 1 },
  { id: "RUN-001", name: "구매자 시나리오 진단", target: targets[0], status: "complete", date: "2026.10.20 11:30", duration: "2분 16초", count: 2 },
];
const stageNames = ["대상과 계정 준비", "웹 기능 탐색", "접근 권한 비교", "근거 검증과 판정", "보고서 생성"];
const routeNames = { overview: "개요", scans: "진단 작업", "new-scan": "새 진단", scan: "작업 요약", results: "취약점·판정", finding: "결과 상세", coverage: "검사 범위", assets: "자산 그래프", knowledge: "지식 그래프 · KG", flow: "진단 흐름", reproduction: "재현 현황", report: "보고서·설정" };
const providerDefaults = {
  ollama: { name: "로컬 개발 모델", endpoint: "http://ollama:11434", model: "qwen3:8b", timeout: "30", tokens: "4096" },
  external: { name: "외부 API 프로필", endpoint: "https://model.example/v1", model: "demo-model", timeout: "30", tokens: "4096" },
};
const state = {
  runs: [], coverageFilter: "all", coverageQuery: "", coverageSelected: null,
  preflight: "idle", preflightScenario: "ready", scopeMethod: "GET", scopeInput: "/api/orders/example", scopeResult: null,
  filter: "all", query: "", runQuery: "", runFilter: "all", detailTab: "evidence", provider: "ollama",
  configs: structuredClone(providerDefaults), connection: "idle", run: null, resultRun: historicalRuns[0], nextRun: 5, newStep: 1,
  form: { name: "주문·계정 접근 권한 진단", target: "atlas", owner: "buyer-a", evaluated: "buyer-b", ai: true, maxAttempts: 60, maxDuration: 5, concurrency: 1 },
};
let runTimer = null;
let toastTimer = null;
let connectionTimer = null;
const view = document.querySelector("#view");
const getRoute = () => {
  const [name, id, runId] = location.hash.slice(1).split("/");
  return { name: routeNames[name] ? name : "overview", id: id || "CASE-001", runId };
};
const badge = (text, color = "neutral") => `<span class="badge ${color}"><span class="dot"></span>${escapeHtml(text)}</span>`;
const verdictBadge = (value) => badge(verdicts[value].label, verdicts[value].color);
const button = (label, action, variant = "secondary", iconName = "", attributes = "") => `<button type="button" class="button ${variant}" data-action="${action}" ${attributes}>${iconName ? icon(iconName) : ""}${label}</button>`;
const heading = (title, subtitle, actions = "", eyebrow = "") => `<div class="page-heading"><div>${eyebrow ? `<p class="eyebrow">${eyebrow}</p>` : ""}<h1 class="page-title" tabindex="-1">${title}</h1><p class="page-subtitle">${subtitle}</p></div><div class="heading-actions">${actions}</div></div>`;
const targetCell = (target) => `<span class="target-avatar ${target.color}">${target.initials}</span><span><strong>${escapeHtml(target.name)}</strong><small>${escapeHtml(target.url.replace("https://", ""))}</small></span>`;
const runBadge = (status) => ({ complete: badge("완료", "success"), partial: badge("일부 확인 불가", "warning"), stopped: badge("중단됨", "neutral"), running: badge("진행 중", "purple") })[status];
const allRuns = () => [...state.runs, ...historicalRuns];
function reportContext() {
  const run = taskRun() || state.resultRun;
  return { run, target: run.target, owner: accountLabel(run.owner || "buyer-a"), evaluated: accountLabel(run.evaluated || "buyer-b") };
}
function reportFindings() {
  return findingsForRun(reportContext().run);
}
function selectedFinding() {
  const cases = reportFindings();
  return location.hash.slice(1).split("/")[1] ? cases.find((item) => item.id === getRoute().id) : cases[0];
}

function navigate(route) {
  if (location.hash === `#${route}`) render();
  else location.hash = route;
}
function toast(message) {
  const element = document.querySelector("#toast");
  clearTimeout(toastTimer);
  element.textContent = message;
  element.hidden = false;
  toastTimer = setTimeout(() => { element.hidden = true; }, 4200);
}
function paintIcons(parent = document) {
  parent.querySelectorAll("[data-icon]").forEach((element) => { element.innerHTML = icon(element.dataset.icon); });
}
function renderNavigation() {
  const route = getRoute().name;
  const selected = taskRoutes.includes(route) || route === "new-scan" ? "scans" : route;
  document.querySelector("#navigation").innerHTML = [
    ["overview", "grid", "개요"], ["scans", "scan", "진단 작업"],
  ].map(([key, glyph, label]) => `<a class="nav-item ${selected === key ? "active" : ""}" href="#${key}" ${selected === key ? 'aria-current="page"' : ""}>${icon(glyph)}<span>${label}</span>${key === "scans" && state.run?.status === "running" ? '<span class="nav-running"></span>' : ""}</a>`).join("");
}
function runTable(runs) {
  if (!runs.length) return `<div class="empty-state">${icon("search")}<h3>일치하는 진단이 없습니다</h3><p>작업 이름·대상 검색어나 상태 필터를 바꿔 보세요.</p>${button("검색·필터 초기화", "reset-run-filters", "secondary small")}</div>`;
  return `<div class="table-wrap"><table class="data-table task-list-table"><thead><tr><th scope="col">작업 ID</th><th scope="col">작업 / 대상</th><th scope="col">상태</th><th scope="col">확인된 취약점</th><th scope="col">시작 일시</th><th scope="col"><span class="sr-only">열기</span></th></tr></thead><tbody>${runs.map((run) => `<tr><td><code class="task-id">${run.id}</code></td><td><a href="#scan/${run.id}" class="task-name-link"><strong>${escapeHtml(run.name)}</strong></a><p class="table-subtext">${escapeHtml(run.target.name)} · ${escapeHtml(run.target.url.replace("https://", ""))}</p></td><td>${runBadge(run.status)}</td><td><span class="finding-count ${run.count > 0 ? "text-danger" : "muted"}">${run.status === "running" ? "집계 중" : run.status === "stopped" ? "미발행" : `${run.count}건`}</span></td><td class="muted nowrap">${run.date}</td><td><a class="button secondary small row-link" href="#scan/${run.id}" aria-label="${escapeHtml(run.name)} 작업 상세 보기">열기 ${icon("arrow")}</a></td></tr>`).join("")}</tbody></table></div>`;
}

function overview() {
  const runs = allRuns();
  const latest = runs.find((run) => ["complete", "partial"].includes(run.status)) || historicalRuns[0];
  const cases = findingsForRun(latest);
  const counts = Object.fromEntries(Object.keys(verdicts).map((key) => [key, cases.filter((item) => item.value === key).length]));
  const running = runs.filter((run) => run.status === "running").length;
  const activityRun = state.run || latest;
  const logs = activityRun.logs || [{ time:"10:42", text:"최근 작업의 판정과 보고서 예시가 준비되었습니다.", kind:"success" }, { time:"10:41", text:"차단·전송 불명·미실행 범위를 기록했습니다.", kind:"warning" }, { time:"10:40", text:"등록 대상과 계정 프로필로 가상 작업을 시작했습니다.", kind:"info" }];
  return `${heading("워크스페이스 개요", "웹 탐색 구조와 진단 진행, 근거에 기반한 판정을 함께 확인하세요.")}
    <div class="workspace-summary"><span>탐색 요약 <a href="#scan/${latest.id}">${latest.id}</a> 기준</span><span>진행 중 작업 <strong>${running} / ${runs.length}</strong></span><span>확인된 취약점 <strong>${counts.confirmed}건</strong></span><span>추가 검토 <strong>${counts.suspected + counts.undecidable}건</strong></span></div>
    ${surfaceKpis(latest)}
    ${state.run?.status === "running" ? `<section class="card active-run-card"><div class="card-body"><div class="progress-header"><div>${runBadge("running")}<h2 class="section-title">${escapeHtml(state.run.name)}</h2><p class="small-text muted">${stageNames[state.run.stage]} · ${state.run.progress}%</p></div>${button("작업 상세 열기", "open-run", "primary small", "arrow")}</div><div class="progress-track"><div class="progress-bar" style="width:${state.run.progress}%"></div></div></div></section>` : ""}
    <div class="overview-discovery-grid">${surfaceSummary(latest)}<section class="card"><div class="card-header"><div><h2 class="section-title">최근 활동</h2><span class="small-text muted">${activityRun.id} · 가상 실행 기록</span></div><a class="text-link" href="#flow/${activityRun.id}">흐름 보기 ${icon("arrow")}</a></div><div class="overview-activity-list">${logs.slice(-5).reverse().map((entry) => `<div class="overview-activity-item">${badge(entry.kind === "success" ? "기록" : entry.kind === "warning" ? "확인 필요" : "진행", entry.kind === "warning" ? "warning" : "neutral")}<div><strong>${escapeHtml(entry.text)}</strong><small>${escapeHtml(entry.time)} · 대상 통신 없음</small></div></div>`).join("")}</div></section></div>
    <section class="card overview-tasks mt-24"><div class="card-header"><h2 class="section-title">최근 진단 작업<span class="section-count">${runs.length}</span></h2><a class="text-link" href="#scans">전체 작업 ${icon("arrow")}</a></div>${runTable(runs.slice(0,4))}<div class="table-caption">모든 대상·판정은 합성 예시입니다. 작업을 열면 그래프·재현 현황·근거를 함께 살펴볼 수 있습니다.</div></section>
    <section class="card mt-24"><div class="card-header"><h2 class="section-title">최근 판정</h2><a class="text-link" href="#results/${latest.id}">${latest.id} ${icon("arrow")}</a></div><div class="overview-recent-findings">${cases.slice(0,4).map((item) => `<a class="overview-finding-item" href="#finding/${item.id}/${latest.id}">${verdictBadge(item.value)}<div><strong>${escapeHtml(item.resource)}</strong><small>${escapeHtml(item.title)}</small></div>${icon("chevron")}</a>`).join("")}</div><div class="table-caption">확인 ${counts.confirmed} · 의심 ${counts.suspected} · 판단불가 ${counts.undecidable} · 접근 허용 ${counts.allowed}</div></section>`;
}

function filteredRuns() {
  const query = state.runQuery.toLowerCase().trim();
  return allRuns().filter((run) => (state.runFilter === "all" || run.status === state.runFilter) && `${run.id} ${run.name} ${run.target.name} ${run.target.url}`.toLowerCase().includes(query));
}

function scans() {
  const runs = filteredRuns();
  return `${heading("진단 작업", "작업별 진행·그래프·취약점·재현 기록을 한곳에서 확인하세요.", button("새 진단", "new", "primary", "plus"))}<section class="card task-list-card"><div class="toolbar"><label class="search-field">${icon("search")}<input id="run-search" placeholder="작업 이름 / 대상 / ID 검색" aria-label="진단 검색" value="${escapeHtml(state.runQuery)}"></label><label class="sr-only" for="run-status">작업 상태</label><select id="run-status" class="task-list-filter" aria-label="작업 상태">${[["all","모든 상태"],["running","진행 중"],["complete","완료"],["partial","일부 확인 불가"],["stopped","중단됨"]].map(([value,label]) => `<option value="${value}" ${state.runFilter === value ? "selected" : ""}>${label}</option>`).join("")}</select><span class="muted small-text" id="task-list-count" role="status">${runs.length} / ${allRuns().length}개 작업</span></div><div id="task-list-content">${runTable(runs)}</div></section>`;
}

function newScan() {
  return scanSetup();
}
function accountLabel(value) { return ({ "buyer-a": "구매자 A", "buyer-b": "구매자 B", "buyer-c": "구매자 C" })[value]; }
function accountOptions(value) { return ["buyer-a", "buyer-b", "buyer-c"].map((id) => `<option value="${id}" ${value === id ? "selected" : ""}>${accountLabel(id)} · ${id}</option>`).join(""); }
function startRun() {
  if (state.run?.status === "running") { navigate(`scan/${state.run.id}`); toast("진행 중인 가상 진단을 먼저 확인해 주세요."); return; }
  if (state.preflight !== "ready") { toast("사전 점검을 완료해 주세요."); return; }
  clearInterval(runTimer);
  state.run = { id: `RUN-${String(state.nextRun++).padStart(3, "0")}`, name: state.form.name, target: targets.find((target) => target.id === state.form.target), owner: state.form.owner, evaluated: state.form.evaluated, ai: true, modelProfile: { provider: state.provider, ...state.configs[state.provider] }, executionLimits: { maxAttempts: state.form.maxAttempts, maxDuration: state.form.maxDuration, concurrency: state.form.concurrency }, status: "running", progress: 8, stage: 0, count: 0, duration: "진행 중", date: "2026.10.22 11:00", logs: [{ time: "11:00:00", text: "가상 진단을 시작했습니다.", kind: "info" }, { time: "11:00:01", text: "등록된 대상과 두 계정 프로필을 준비했습니다.", kind: "success" }] };
  if (state.form.retestCaseId) Object.assign(state.run, { retestCaseId: state.form.retestCaseId, sourceRunId: state.form.sourceRunId, originalFinding: { ...state.form.originalFinding }, retestScenario: state.form.retestScenario });
  state.runs.unshift(state.run);
  runTimer = setInterval(() => {
    if (state.run?.status !== "running") return;
    state.run.progress = Math.min(100, state.run.progress + 7);
    const nextStage = Math.min(4, Math.floor(state.run.progress / 21));
    if (nextStage !== state.run.stage) {
      state.run.stage = nextStage;
      state.run.logs.push({ time: `11:00:${String(state.run.logs.length + 1).padStart(2, "0")}`, text: `${stageNames[nextStage]} 단계를 진행하고 있습니다.`, kind: "info" });
    }
    if (state.run.progress === 100) finishRun();
    else if (["assets", "knowledge", "flow"].includes(getRoute().name) && taskRun()?.id === state.run.id) { repaintGraph(); refreshTaskProgress(); }
    else if (["overview", "scans"].includes(getRoute().name) || taskRun()?.id === state.run.id) render(false);
  }, 700);
  navigate(`scan/${state.run.id}`);
}
function finishRun() {
  clearInterval(runTimer);
  if (!state.run || state.run.status !== "running") return;
  Object.assign(state.run, { status: "complete", progress: 100, stage: 4, count: state.run.retestCaseId ? state.run.retestScenario === "present" && state.run.originalFinding.value === "confirmed" ? 1 : 0 : 3, duration: "10초 (데모)" });
  state.resultRun = state.run;
  state.run.logs.push({ time: "11:00:10", text: `예시 결과와 보고서가 준비되었습니다. 확인된 취약점 ${state.run.count}건입니다.`, kind: "success" });
  render(false);
  toast("가상 진단이 완료되었습니다. 결과를 확인해 보세요.");
}
function scan() {
  return taskOverview(taskRun());
}

function resultRows() {
  const query = state.query.toLowerCase();
  return reportFindings().filter((finding) => (state.filter === "all" || finding.value === state.filter) && `${finding.title} ${finding.path} ${finding.id} ${findingCategory(finding)}`.toLowerCase().includes(query));
}
function resultsTable() {
  const rows = resultRows();
  if (!reportFindings().length && reportContext().run.status === "running") return `<div class="empty-state">${icon("activity")}<h3>근거 검증과 판정이 진행 중입니다</h3><p>아직 발행된 판정이 없습니다. 후보를 확정된 취약점이나 안전한 결과로 표시하지 않습니다.</p><a class="button secondary" href="#reproduction/${reportContext().run.id}">재현·비교 현황 보기</a></div>`;
  if (!reportFindings().length && reportContext().run.status === "stopped") return `<div class="empty-state">${icon("stop")}<h3>최종 판정 없이 작업이 중단되었습니다</h3><p>중단 전에 확보한 관찰 기록과 미확인 범위를 보존합니다. 취약점 없음이나 신원 검증 실패로 바꾸지 않습니다.</p><a class="button secondary" href="#coverage/${reportContext().run.id}">검사 범위와 중단 사유 보기</a></div>`;
  if (!rows.length) return `<div class="empty-state">${icon("search")}<h3>검색 조건에 맞는 결과가 없습니다</h3><p>다른 검색어나 판정 필터를 선택해 보세요.</p>${button("필터 초기화", "reset-filters", "secondary small")}</div>`;
  return `<div class="table-wrap"><table class="data-table findings-table"><thead><tr><th scope="col">ID</th><th scope="col">검사 유형</th><th scope="col">심각도</th><th scope="col">판정</th><th scope="col">결과 / 엔드포인트</th><th scope="col">기록일</th><th scope="col"><span class="sr-only">상세</span></th></tr></thead><tbody>${rows.map((finding) => `<tr><td><code class="task-id">${escapeHtml(finding.id)}</code></td><td class="finding-category">${escapeHtml(findingCategory(finding))}</td><td><span class="severity ${finding.severity === "높음" ? "high" : finding.severity === "중간" ? "medium" : ""}">${finding.severity === "높음" || finding.severity === "중간" ? '<i></i>' : ""}${escapeHtml(finding.severity)}</span></td><td>${verdictBadge(finding.value)}</td><td><a class="finding-title" href="#finding/${finding.id}/${reportContext().run.id}">${escapeHtml(finding.title)}</a><p class="table-subtext"><span class="method">GET</span> ${escapeHtml(finding.path)}</p></td><td class="muted nowrap">${escapeHtml(findingRecordedDate(reportContext().run))}</td><td><a class="icon-button row-link" href="#finding/${finding.id}/${reportContext().run.id}" aria-label="${finding.id} 상세 보기">${icon("chevron")}</a></td></tr>`).join("")}</tbody></table></div>`;
}
function resultMetrics(context, cases) {
  const candidateCount = Math.max(surfaceInventory(context.run).candidateCount, cases.length);
  const metrics = [["진단 후보", candidateCount, "확정 취약점과 구분"], ["판정 발행", cases.length, "판단불가·허용 포함"], ["확인된 취약점", cases.filter((item) => item.value === "confirmed").length, "근거를 확인한 사례"], ["오탐 검토 기록", "—", "독립 검토 기록 없음"]];
  return `<section class="result-metrics" aria-label="판정 요약 지표">${metrics.map(([label, value, note]) => `<div class="stat-card"><span class="stat-label">${label}</span><strong class="stat-value">${value}</strong><p class="stat-foot">${note}</p></div>`).join("")}</section>`;
}
function results() {
  const requestedRun = allRuns().find((run) => run.id === getRoute().id);
  if (requestedRun) state.resultRun = requestedRun;
  const context = reportContext();
  const cases = reportFindings();
  const counts = Object.fromEntries(Object.keys(verdicts).map((value) => [value, cases.filter((item) => item.value === value).length]));
  const stopped = context.run.status === "stopped";
  const unpublished = context.run.status === "running" || stopped && !cases.length;
  const incomplete = coverageRows(context.run).filter((row) => row.status !== "complete").length;
  return `${taskSectionHeading("취약점·판정", context.run.status === "running" ? "근거 검증과 최종 판정이 끝나면 이 작업의 결과가 표시됩니다." : "확인된 취약점과 추가 검토가 필요한 사례를 함께 확인하세요.")}${retestBanner(context.run)}${context.run.status === "partial" ? `<div class="info-note warning-note" role="status">${icon("alert")}<p>일부 확인 불가 작업입니다. ${incomplete}개 검사 항목의 제한·미확인 사유를 보존합니다. 아래 판정은 확보한 근거의 범위에 한하며 전체 검사 완료나 취약점 부재를 뜻하지 않습니다. <a class="text-link" href="#coverage/${context.run.id}">미완료 범위 보기</a></p></div>` : ""}${stopped ? `<div class="info-note warning-note">${icon("alert")}<p>가상 진단이 중단됐습니다. 확보한 관찰 기록은 보존하며, 미완료 검사에서 판정·PoC를 만들지 않습니다.</p></div>` : ""}<div class="result-summary"><div><span class="result-summary-icon">${icon("shield")}</span><div><strong>${unpublished ? stopped ? "중단으로 최종 판정이 발행되지 않았습니다" : "아직 최종 판정이 발행되지 않았습니다" : `${cases.length}개 사례에서 ${counts.confirmed}건의 취약점이 확인되었습니다`}</strong><p>${unpublished ? "판정 미발행을 취약점 없음으로 해석하지 않습니다. 관찰 기록과 미확인 사유를 함께 검토하세요." : `${counts.suspected + counts.undecidable}건은 추가 검토가 필요하며, ${counts.allowed}건은 등록 정책상 접근이 허용됩니다. 모두 가상 사례입니다.`}</p></div></div>${badge("예시 결과", "purple")}</div>${resultMetrics(context, cases)}<section class="card"><div class="toolbar results-toolbar"><div class="filter-tabs" role="group" aria-label="판정 필터">${[["all", "전체", cases.length], ["confirmed", "확인됨", counts.confirmed], ["suspected", "의심", counts.suspected], ["undecidable", "판단불가", counts.undecidable], ["allowed", "접근 허용", counts.allowed]].map(([value, label, count]) => `<button class="filter-tab ${state.filter === value ? "active" : ""}" data-action="filter" data-value="${value}" aria-pressed="${state.filter === value}">${label}<span>${count}</span></button>`).join("")}</div><label class="search-field compact">${icon("search")}<input id="result-search" placeholder="결과 또는 경로 검색" aria-label="결과 검색" value="${escapeHtml(state.query)}"></label></div><div id="results-table">${resultsTable()}</div><div class="table-caption"><span id="result-count">${resultRows().length}개 결과</span><span>정책상 접근 허용은 전체 시스템의 안전을 뜻하지 않습니다.</span></div></section>`;
}
function finding() {
  const item = selectedFinding();
  const context = reportContext();
  if (!item || getRoute().runId && !allRuns().some((run) => run.id === getRoute().runId)) return `${taskSectionHeading("결과 상세", "이 작업에서 아직 확인된 사례가 없습니다.")}<a class="button secondary" href="#results/${context.run.id}">진단 결과로 돌아가기</a>`;
  const confirmed = item.value === "confirmed";
  const summaries = {
    confirmed: "소유자 A의 자료가 다른 계정 B에게도 반환되는 가상 사례입니다. 등록된 접근 정책과 서로 다른 신원, 실제 데이터 일치를 함께 확인한 판정 예시입니다.",
    suspected: "서로 다른 계정에서 같은 청구서 데이터가 관찰된 가상 사례입니다. 신원과 데이터 비교는 확인됐지만 기대 접근 정책이 없어 취약점 확정을 보류했습니다.",
    undecidable: "교차 요청의 전송 상태가 불명확한 가상 사례입니다. 전송되지 않았거나 접근이 차단됐다고 단정하지 않으며, 취약점 없음으로 해석하지 않습니다.",
    allowed: "등록된 팀 공유 정책이 평가 계정의 접근을 허용하는 가상 사례입니다. 실제 HTTP 성공이나 다른 기능의 취약점 부재를 뜻하지 않습니다.",
  };
  if (item.retestOutcome) summaries.undecidable = item.retestOutcome === "not-reproduced" ? "현재 조건에서 기존 재현 경로의 교차 자료가 관찰되지 않은 가상 사례입니다. 수정 완료나 다른 경로의 취약점 부재를 증명하지 않습니다." : "현재 계정의 신원 근거가 부족한 가상 사례입니다. 확인하지 못한 결과를 수정 완료로 처리하지 않습니다.";
  return `<a class="back-link" href="#results/${context.run.id}">${icon("left")}이 작업의 취약점·판정</a>${taskSectionHeading(escapeHtml(item.title), `${item.id} · ${escapeHtml(context.target.name)} · 수평 접근 권한`, `<a class="button secondary" href="#knowledge/${context.run.id}/${item.id}">${icon("activity")}KG에서 보기</a>` + button("HTML 보고서", "export-report", "secondary", "download"))}
    <div class="detail-badges">${verdictBadge(item.value)}${badge(`심각도 · ${item.severity}`, confirmed ? "danger" : "neutral")}<span class="muted small-text">${icon("calendar")}기록일 ${escapeHtml(findingRecordedDate(context.run))}</span></div>
    <div class="finding-layout"><div class="finding-main"><section class="card"><div class="card-body"><h2 class="section-title">무엇을 확인했나요?</h2><p class="finding-description">${summaries[item.value]}</p><div class="finding-key-facts"><span>검사 유형 <strong>${escapeHtml(findingCategory(item))}</strong></span><span>관련 자원 <strong>${escapeHtml(item.resource)}</strong></span></div><div class="endpoint-box"><span class="method">GET</span><code>${escapeHtml(item.path)}</code>${badge("가상 요청", "neutral")}</div></div></section>
    ${findingReproductionSummary(item, context)}
    <section class="card"><div class="detail-tabs" role="tablist" aria-label="진단 근거 상세">${[["evidence", "판정 근거"], ["poc", "재현 절차 · PoC"], ["timeline", "요청 타임라인"]].map(([key, label]) => `<button type="button" id="tab-${key}" role="tab" aria-controls="detail-panel" aria-selected="${state.detailTab === key}" tabindex="${state.detailTab === key ? 0 : -1}" class="tab-button ${state.detailTab === key ? "active" : ""}" data-action="detail-tab" data-value="${key}">${label}</button>`).join("")}</div><div class="card-body detail-panel" id="detail-panel" role="tabpanel" aria-labelledby="tab-${state.detailTab}">${state.detailTab === "evidence" ? evidencePanel(item) : state.detailTab === "poc" ? pocPanel(item) : timelinePanel(item)}</div></section></div>
    <aside class="finding-side">${findingHttpExamples(item, context)}<section class="card"><div class="card-body"><h2 class="section-title">사례 정보</h2><dl class="detail-meta"><div><dt>대상</dt><dd>${escapeHtml(context.target.name)}</dd></div><div><dt>자원</dt><dd>${escapeHtml(item.resource)}</dd></div><div><dt>접근 정책</dt><dd>${escapeHtml(item.policy)}</dd></div><div><dt>소유자 역할 A</dt><dd>${escapeHtml(context.owner)}</dd></div><div><dt>평가 역할 B</dt><dd>${escapeHtml(context.evaluated)}</dd></div><div><dt>재현 절차</dt><dd>${confirmed ? badge("문서화 예시", "purple") : badge("미제공", "neutral")}</dd></div></dl></div></section><div class="detail-tip">${icon("flask")}<p>화면 검토를 위한 가상 사례입니다. 표시된 근거와 응답 조각은 실제 캡처가 아닙니다.</p></div>${retestCard(item)}</aside></div>${evidenceChain(item)}`;
}
function evidencePanel(item) {
  if (item.retestOutcome) return `<div class="state-callout neutral">${icon("help")}<h3>${item.retestOutcome === "not-reproduced" ? "이번 조건에서 미재현" : "현재 신원 근거 확인 불가"}</h3><p>${item.retestOutcome === "not-reproduced" ? "등록된 비교 경로에서 교차 자료가 관찰되지 않은 예시입니다. 과거 근거는 유지하고, 전체 취약점 부재와 수정 완료를 단정하지 않습니다." : "계정 신원을 확인하지 못해 비교를 완료하지 않은 예시입니다. 미실행과 근거 부족을 보존합니다."}</p></div>`;
  if (item.value === "undecidable") return `<div class="state-callout neutral">${icon("help")}<h3>판정을 내릴 근거가 충분하지 않습니다</h3><p>교차 요청의 전송 여부와 응답 근거를 확인할 수 없습니다. 자동으로 재전송하거나 이 항목을 정상으로 처리하지 않습니다.</p></div><ul class="check-list"><li class="check-item">${icon("check")}소유자 계정과 등록된 접근 정책 확인</li><li class="check-item unresolved">${icon("help")}평가 계정 요청의 전송 상태 확인 불가</li><li class="check-item unresolved">${icon("help")}교차 응답 근거 없음 · 데이터 비교 보류</li></ul>`;
  if (item.value === "allowed") return `<div class="state-callout info">${icon("users")}<h3>등록된 공유 정책상 허용된 접근입니다</h3><p>평가 계정 B의 유효한 신원과 이 사례에 적용되는 팀 공유 정책이 검증됐다고 가정한 예시입니다.</p></div><ul class="check-list"><li class="check-item">${icon("check")}평가 계정 B의 신원 확인</li><li class="check-item">${icon("check")}해당 자원에 적용되는 등록 공유 정책 확인</li><li class="check-item">${icon("check")}유효기간과 팀 구성원 범위 확인</li></ul><p class="muted">이 판정은 실제 접근 성공이나 전체 서비스의 안전을 보장하지 않습니다.</p>`;
  return `<h3 class="subsection-title">판정에 사용한 조건</h3><ul class="check-list"><li class="check-item ${item.value === "suspected" ? "unresolved" : ""}">${icon(item.value === "suspected" ? "help" : "check")}<span>${item.value === "suspected" ? "기대 접근 정책 미등록 — 금지 여부 추가 확인 필요" : "등록 정책: 소유자 외 접근 금지 · 공유/위임 예외 없음"}</span></li><li class="check-item">${icon("check")}소유자 A와 평가 계정 B가 서로 다른 검증 주체</li><li class="check-item">${icon("check")}같은 자원의 비자명한 데이터가 두 응답에 포함</li><li class="check-item">${icon("check")}입력 반사와 공통 화면 템플릿으로 인한 오인 제외</li></ul><div class="section-inline-heading"><h3 class="subsection-title">응답 근거 비교</h3><span class="muted small-text">비식별 합성 데이터</span></div><div class="evidence-grid">${[`소유자 역할 A · ${reportContext().owner}`, `평가 역할 B · ${reportContext().evaluated}`].map((label) => `<div class="evidence-panel"><div class="evidence-heading"><strong>${label}</strong>${badge("200", "success")}</div><pre class="code-block"><code>{
  "resource": "${item.resource}",
  "object_id": "&lt;RESOURCE_ID&gt;",
  "owner": "&lt;ACCOUNT_A&gt;",
  "data_match": true
}</code></pre><div class="evidence-footer">${icon("check")}같은 자원 · 데이터 일치</div></div>`).join("")}</div><p class="small-text muted mt-16">상태 코드 200만으로 판정하지 않습니다. 위 내용은 실제 원문 응답이 아닌 비교 화면 예시입니다.</p>`;
}
function pocText(item) {
  return `# ABC2LAB · 가상 사례 ${item.id}\n# 대상: ${reportContext().target.name} · 소유자 역할 A: ${reportContext().owner} / 평가 역할 B: ${reportContext().evaluated}\n# 실행하지 않은 placeholder 템플릿입니다.\n# 등록 대상·자원·계정은 별도 확인이 필요합니다.\n\n# 1. 소유자 A의 기준 요청\ncurl --request GET \\\n  '\${REGISTERED_ORIGIN}${item.path.replace(/\{[^}]+\}/g, "\${RESOURCE_ID}")}' \\\n  --header 'Authorization: Bearer \${SESSION_A}'\n\n# 2. 같은 자원에 평가 계정 B로 비교\ncurl --request GET \\\n  '\${REGISTERED_ORIGIN}${item.path.replace(/\{[^}]+\}/g, "\${RESOURCE_ID}")}' \\\n  --header 'Authorization: Bearer \${SESSION_B}'\n\n# 표시된 절차는 별도 재실행하지 않았습니다.`;
}
function pocPanel(item) {
  if (item.value !== "confirmed") return `<div class="empty-state">${icon("file")}<h3>이 사례에는 취약점 PoC를 제공하지 않습니다</h3><p>${item.value === "allowed" ? "등록 정책상 허용 판정입니다. 취약점 재현 절차로 표시하지 않습니다." : "판정이 확정되지 않았거나 필요한 실행 근거가 부족합니다."}</p>${button("판정 근거 확인", "detail-tab", "secondary small", "left", 'data-value="evidence"')}</div>`;
  return `<div class="section-inline-heading"><div><h3 class="subsection-title">재현 절차</h3><p class="muted small-text">문서화된 예시 · 별도 재실행 없음</p></div>${button("템플릿 복사", "copy-poc", "secondary small", "copy")}</div><ol class="poc-steps"><li>등록된 대상과 정책이 현재도 유효한지 확인합니다.</li><li>서로 다른 A/B 계정의 신원을 확인합니다.</li><li>소유자 A로 자원을 조회한 뒤 같은 자원에 B로 접근한 결과를 비교합니다.</li><li>단순 상태 코드가 아닌 실제 데이터와 접근 정책을 대조합니다.</li></ol><div class="code-toolbar"><span>${icon("file")}placeholder-request.sh</span>${badge("미실행 템플릿", "neutral")}</div><pre class="code-block poc-code"><code>${escapeHtml(pocText(item))}</code></pre><p class="muted small-text mt-16">토큰·계정·자원 값은 포함하지 않습니다. 이 목업에는 요청을 실행하는 기능이 없습니다.</p>`;
}
function timelinePanel(item) {
  if (item.retestOutcome) return `<div class="scan-notice">${icon("clock")}<div><strong>새 진단의 확인 기록</strong><p>${item.retestOutcome === "not-reproduced" ? "신원·정책 확인 → 기존 비교 경로 관찰 → 교차 자료 미관찰 → 판정 한계 기록" : "신원 확인 불가 → 비교 미실행 → 확인 불가 기록"}. 모든 기록은 합성 예시이며 과거 결과는 변경하지 않습니다.</p></div></div>`;
  const rows = item.value === "undecidable" ? [["기준 요청", "소유자 A", "전송됨", "기준 근거 예시 보존"], ["교차 요청", "평가 계정 B", "확인 불가", "전송 여부와 캡처 확인 불가"], ["판정", "—", "판단불가", "불확실성을 그대로 보존"]] : item.value === "allowed" ? [["신원 확인", "평가 계정 B", "확인됨", "가상 신원 근거 대조"], ["정책 확인", "등록 정책", "접근 허용", "사례에 적용되는 공유 범위 확인"], ["판정", "—", "접근 허용", "실제 HTTP 성공을 주장하지 않음"]] : [["기준 요청", "소유자 A", "전송됨", "응답 근거 예시 저장"], ["교차 요청", "평가 계정 B", "전송됨", "같은 자원의 응답 근거 예시 저장"], ["비교·판정", "—", verdicts[item.value].label, "신원·정책·데이터 근거 연결"]];
  return `<p class="muted small-text">모든 항목은 가상 기록입니다. 보고서 작성은 대상 요청을 추가로 보내지 않습니다.</p><div class="timeline-list">${rows.map(([title, account, status, text], index) => `<div class="timeline-item"><span class="timeline-point">${index + 1}</span><div><div class="timeline-heading"><strong>${title}</strong>${badge(status, status === "확인 불가" ? "warning" : "neutral")}</div><p>${account} · ${text}</p><small>2026.10.22 ${item.time} · 예시 기록</small></div></div>`).join("")}</div>`;
}
function render(focus = true) {
  const route = getRoute();
  const priorInput = !focus && document.activeElement?.matches("input:not([type=range])") ? { id: document.activeElement.id, start: document.activeElement.selectionStart, end: document.activeElement.selectionEnd } : null;
  const priorLink = !focus && document.activeElement?.matches("a[href]") ? document.activeElement.getAttribute("href") : null;
  const priorAction = !focus ? document.activeElement?.dataset?.action : null;
  const priorValue = !focus ? document.activeElement?.dataset?.value : null;
  if (taskRoutes.includes(route.name)) {
    const selected = allRuns().find((item) => item.id === (route.name === "finding" ? route.runId : route.id));
    if (selected) state.resultRun = selected;
  }
  document.title = `ABC2LAB · ${taskRun()?.name || routeNames[route.name]}`;
  document.querySelector("#breadcrumbs").textContent = taskRoutes.includes(route.name) ? `진단 작업 / ${taskRun()?.id || "기록 없음"} / ${routeNames[route.name]}` : routeNames[route.name];
  renderNavigation();
  const requestedRun = taskRoutes.includes(route.name) && (route.name === "finding" ? route.runId : location.hash.slice(1).split("/")[1]);
  if (requestedRun && !allRuns().some((run) => run.id === requestedRun)) {
    view.innerHTML = `${heading("진단 기록을 찾을 수 없습니다", "목업에서 생성한 기록은 현재 탭에만 유지되며 새로고침하면 초기화됩니다.")}<a class="button secondary" href="#scans">진단 작업으로 이동</a>`;
    toggleMenu(false);
    if (focus) view.querySelector("h1")?.focus({ preventScroll: true });
    return;
  }
  const renderers = { overview, scans, "new-scan": newScan, scan, results, finding, coverage, assets: graphScreen, knowledge: graphScreen, flow: graphScreen, reproduction, report: taskReport };
  const run = taskRun();
  if (run && state.detailRunId !== run.id) {
    Object.assign(state, { detailRunId: run.id, filter: "all", query: "", coverageFilter: "all", coverageQuery: "", coverageSelected: null, reproductionSelected: null });
  }
  view.innerHTML = (run ? taskHeader(run) : "") + `<div class="task-panel">${renderers[route.name]()}</div>`;
  toggleMenu(false);
  if (focus) { view.querySelector("h1")?.focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: "instant" }); }
  else if (priorInput) {
    const input = document.getElementById(priorInput.id);
    input?.focus({ preventScroll: true });
    if (input && priorInput.start !== null) input.setSelectionRange(priorInput.start, priorInput.end);
  }
  else if (priorLink) [...document.querySelectorAll("a[href]")].find((link) => link.getAttribute("href") === priorLink)?.focus({ preventScroll: true });
  else if (priorAction) view.querySelector(`[data-action="${priorAction}"]${priorValue ? `[data-value="${priorValue}"]` : ""}`)?.focus({ preventScroll: true });
}
function openDialog(title, body, actions = "") {
  const dialog = document.querySelector("#app-dialog");
  dialog.innerHTML = `<div class="dialog-heading"><h2 id="dialog-title">${title}</h2>${button("", "close-dialog", "icon-button ghost", "close", 'aria-label="대화상자 닫기"')}</div><div class="dialog-body">${body}</div><div class="dialog-actions">${actions || button("확인", "close-dialog", "primary")}</div>`;
  dialog.showModal();
}
function commandResults(query = "") {
  const text = query.trim().toLowerCase();
  const runs = allRuns().filter((run) => `${run.id} ${run.name} ${run.target.name} ${run.target.url}`.toLowerCase().includes(text));
  if (!runs.length) return `<p class="command-empty" role="status">일치하는 작업이 없습니다. 이름·대상·ID를 바꿔 검색해 보세요.</p>`;
  return runs.map((run) => `<a class="command-result" href="#scan/${run.id}" data-action="open-search-result"><span><strong>${escapeHtml(run.name)}</strong><small>${run.id} · ${escapeHtml(run.target.name)}</small></span>${runBadge(run.status)}${icon("arrow")}</a>`).join("");
}

function openTaskSearch() {
  const dialog = document.querySelector("#app-dialog");
  if (dialog.open) dialog.close();
  openDialog("작업 빠른 검색", `<label class="command-search search-field" for="command-search">${icon("search")}<input id="command-search" aria-label="작업 빠른 검색어" placeholder="작업 이름, 대상 또는 ID" autocomplete="off"></label><div class="command-results" id="command-results" aria-label="작업 검색 결과">${commandResults()}</div><p class="small-text muted">Enter로 작업 열기 · Esc로 닫기</p>`, button("닫기", "close-dialog", "secondary small"));
  document.querySelector("#command-search").focus();
}

function exportReport() {
  const context = reportContext();
  const cases = reportFindings();
  if (context.run.status === "running") { toast("작업이 끝난 뒤 보고서를 내려받을 수 있습니다."); return; }
  const report = `<!doctype html><html lang="ko"><meta charset="utf-8"><title>ABC2LAB 가상 진단 보고서</title><style>body{font:15px/1.7 system-ui,sans-serif;max-width:900px;margin:48px auto;padding:0 24px;color:#20273b}h1{font-size:28px}article{padding:24px 0;border-top:1px solid #ddd}pre{white-space:pre-wrap;padding:20px;background:#f3f4f8;border-radius:8px}small{color:#666}</style><h1>ABC2LAB · 가상 진단 보고서</h1><p>화면 검토용 합성 데이터이며 실제 진단·전송·재실행 기록이 아닙니다.</p><p>${escapeHtml(context.target.name)} · ${escapeHtml(context.run.name)} · 가상 사례 ${cases.length}건</p><p>소유자 역할 A: ${context.owner} / 평가 역할 B: ${context.evaluated}</p>${context.run.status === "stopped" ? "<p>작업 중단 · 최종 판정 미발행. 관찰 기록과 미실행·미확인 사유를 보존하며 취약점 없음이나 신원 실패로 해석하지 않습니다.</p>" : ""}${context.run.retestCaseId ? `<p>수정 확인: ${escapeHtml(context.run.sourceRunId)} → ${context.run.id}. ${context.run.status === "stopped" ? "중단됨" : context.run.retestScenario === "not-reproduced" ? "이번 조건에서 미재현" : context.run.retestScenario === "unverified" ? "확인 불가" : "이전과 같은 판정 예시"}. 미재현은 수정 완료나 전체 취약점 부재의 증명이 아닙니다.</p>` : ""}<h2>검사 범위 예시</h2><p>등록된 동작 ${context.target.endpoints}개와 구분한 선택 작업 ${coverageRows(context.run).length}개입니다. 웹 전체의 검사율은 알 수 없습니다.</p><ul>${coverageRows(context.run).map((row) => `<li>${escapeHtml(row.path)} — ${coverageStates[row.status].label}: ${escapeHtml(row.reason)}</li>`).join("")}</ul>${cases.map((item) => `<article><small>${item.id} · ${verdicts[item.value].label} · ${item.severity}</small><h2>${escapeHtml(item.title)}</h2><p>GET ${escapeHtml(item.path)}</p><p>등록 정책 예시: ${escapeHtml(item.policy)}</p>${item.value === "confirmed" ? `<h3>미실행 PoC 템플릿</h3><pre>${escapeHtml(pocText(item))}</pre>` : "<p>취약점 재현 절차 미제공. 판정과 제한 사유를 보존합니다.</p>"}</article>`).join("")}<p>정책상 접근 허용은 전체 시스템의 안전을 뜻하지 않습니다.</p></html>`;
  const url = URL.createObjectURL(new Blob([report], { type: "text/html;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "ABC2LAB-demo-report.html";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
  toast("가상 데이터로 작성한 HTML 보고서를 내려받았습니다.");
}
function saveConfig(form) {
  const data = new FormData(form);
  state.configs[state.provider] = { name: String(data.get("profileName") || ""), endpoint: String(data.get("endpoint") || ""), model: String(data.get("model") || ""), timeout: String(data.get("timeout") || "30"), tokens: String(data.get("tokens") || "4096") };
}
document.addEventListener("click", async (event) => {
  if (event.target.closest(".activity-item")) state.resultRun = historicalRuns[0];
  if (event.target.closest("#navigation a, .brand")) toggleMenu(false);
  const element = event.target.closest("[data-action]");
  if (!element || element.disabled) return;
  const action = element.dataset.action;
  if (action === "open-search") openTaskSearch();
  else if (action === "open-search-result") document.querySelector("#app-dialog").close();
  else if (action === "reset-run-filters") { state.runQuery = ""; state.runFilter = "all"; render(false); }
  else if (action === "new") {
    if (state.run?.status === "running") { toast("진행 중인 가상 진단이 있습니다."); navigate(`scan/${state.run.id}`); }
    else { delete state.form.retestCaseId; delete state.form.sourceRunId; delete state.form.originalFinding; state.newStep = 1; invalidatePreflight(); navigate("new-scan"); }
  } else if (action === "configure-scan") { state.newStep = 3; invalidatePreflight(); navigate("new-scan"); }
  else if (action === "go-scans") navigate("scans");
  else if (action === "go-results") navigate(`results/${allRuns().find((run) => run.id === getRoute().id)?.id || state.run?.id || state.resultRun.id}`);
  else if (action === "open-run") navigate(`scan/${state.run.id}`);
  else if (action === "previous-step") {
    if (state.newStep === 2) {
      const data = new FormData(document.querySelector("#new-scan-form"));
      state.form.owner = String(data.get("owner")); state.form.evaluated = String(data.get("evaluated")); state.form.ai = true;
    }
    if (state.newStep === 3) captureModelDraft(document.querySelector("#new-scan-form"));
    invalidatePreflight(); state.newStep = Math.max(1, state.newStep - 1); render();
  }
  else if (action === "filter") { state.filter = element.dataset.value; render(false); }
  else if (action === "reset-filters") { state.filter = "all"; state.query = ""; render(false); }
  else if (action === "detail-tab") { state.detailTab = element.dataset.value; render(false); document.querySelector(`#tab-${state.detailTab}`)?.focus({ preventScroll: true }); }
  else if (action === "finish-run") finishRun();
  else if (action === "stop-run") openDialog("진단을 중지할까요?", "<p>중단 전에 확인한 근거는 보존하고, 아직 확인하지 못한 항목은 미완료로 남깁니다.</p><p class=\"muted\">현재 작업은 가상 진단입니다.</p>", `${button("계속 진단", "close-dialog", "secondary")}${button("진단 중지", "confirm-stop", "danger", "stop")}`);
  else if (action === "confirm-stop") {
    clearInterval(runTimer);
    if (state.run?.status !== "running") {
      document.querySelector("#app-dialog").close(); render(); toast("이미 완료된 가상 진단입니다. 결과를 확인해 주세요."); return;
    }
    Object.assign(state.run, { status: "stopped", duration: "중단됨", count: 0 });
    state.run.count = findingsForRun(state.run).filter((item) => item.value === "confirmed").length;
    state.resultRun = state.run;
    state.run.logs.push({ time: "11:00:05", text: "사용자가 진단을 중단했습니다. 미확인 상태를 보존합니다.", kind: "warning" });
    document.querySelector("#app-dialog").close(); render(); toast("가상 진단을 중지했습니다.");
  } else if (action === "export-report") exportReport();
  else if (action === "copy-poc") {
    const item = selectedFinding();
    try { await navigator.clipboard.writeText(pocText(item)); toast("미실행 placeholder 템플릿을 복사했습니다."); }
    catch { openDialog("템플릿 복사", `<p>아래 텍스트를 선택해 복사해 주세요.</p><textarea class="copy-fallback" readonly aria-label="복사용 PoC 템플릿">${escapeHtml(pocText(item))}</textarea>`); }
  } else if (action === "test-connection") {
    const form = document.querySelector("#new-scan-form");
    if (!form.reportValidity()) return;
    saveConfig(form);
    const provider = state.provider;
    clearTimeout(connectionTimer);
    state.connection = "testing"; render(false);
    connectionTimer = setTimeout(() => {
      if (provider !== state.provider) return;
      state.connection = "success";
      if (getRoute().name === "new-scan" && state.newStep === 3) render(false);
      toast("예시 연결 성공입니다. 실제 모델 API는 호출하지 않았습니다.");
    }, 800);
  } else if (action === "close-dialog") document.querySelector("#app-dialog").close();
  else if (action === "help") openDialog("ABC2LAB 목업 둘러보기", '<p>가상 데이터로 작업 생성부터 그래프·근거 검토까지 살펴보는 목업입니다.</p><ol><li><strong>새 진단</strong>에서 대상·계정·범위를 선택하세요.</li><li>가상 진행을 기다리거나 <strong>데모 빠르게 완료</strong>를 누르세요.</li><li><strong>작업 상세</strong>에서 그래프·취약점·재현 현황과 근거·PoC를 확인하세요.</li><li><strong>새 진단의 모델·실행 설정</strong>에서 모델 연결 방식을 바꾸고, <strong>작업 상세의 그래프</strong>에서 자산·KG·진단 흐름을 살펴보세요.</li></ol><p class="muted">대상·LLM·DB를 호출하지 않으며, 새로고침하면 초기화됩니다.</p>');
});
document.addEventListener("submit", (event) => {
  if (event.target.id !== "new-scan-form") return;
  event.preventDefault();
  const form = event.target;
  if (!form.reportValidity()) return;
  const data = new FormData(form);
  if (state.newStep === 1) { state.form.name = String(data.get("scanName")).trim(); state.form.target = String(data.get("target")); if (!state.form.name) { document.querySelector("#scan-name").setCustomValidity("진단 이름을 입력해 주세요."); form.reportValidity(); return; } }
  if (state.newStep === 2) {
    state.form.owner = String(data.get("owner")); state.form.evaluated = String(data.get("evaluated")); state.form.ai = true;
    if (state.form.owner === state.form.evaluated) { document.querySelector("#account-error").hidden = false; return; }
  }
  if (state.newStep === 3) readScanSettings(form);
  if (state.newStep < 4) { invalidatePreflight(); state.newStep += 1; render(); }
  else startRun();
});
document.addEventListener("input", (event) => {
  if (event.target.id === "command-search") document.querySelector("#command-results").innerHTML = commandResults(event.target.value);
  else if (event.target.id === "result-search") { state.query = event.target.value; document.querySelector("#results-table").innerHTML = resultsTable(); document.querySelector("#result-count").textContent = `${resultRows().length}개 결과`; }
  else if (event.target.id === "run-search") { state.runQuery = event.target.value; const form = event.target; const position = form.selectionStart; render(false); const input = document.querySelector("#run-search"); input.focus(); input.setSelectionRange(position, position); }
  else if (event.target.id === "scan-name") event.target.setCustomValidity("");
  else if (event.target.closest(".scan-model-settings") && event.target.id !== "api-key") {
    captureModelDraft(document.querySelector("#new-scan-form"));
    invalidatePreflight();
    clearTimeout(connectionTimer);
    state.connection = "idle";
    const status = document.querySelector(".connection-status");
    if (status) {
      status.classList.remove("connected");
      status.querySelector("span").innerHTML = `${icon("globe")}설정이 변경되었습니다. 연결 확인은 데모로 진행합니다.`;
      const testButton = status.querySelector("button");
      testButton.disabled = false; testButton.textContent = "연결 확인 (데모)";
    }
  }
});
document.addEventListener("change", (event) => {
  if (event.target.id === "run-status") { state.runFilter = event.target.value; render(false); document.querySelector("#run-status").focus({ preventScroll: true }); }
  else if (event.target.name === "provider") { captureModelDraft(document.querySelector("#new-scan-form")); invalidatePreflight(); state.provider = event.target.value; state.connection = "idle"; clearTimeout(connectionTimer); render(false); }
  else if (event.target.name === "target") {
    const form = document.querySelector("#new-scan-form");
    state.form.name = form.elements.scanName.value; state.form.target = event.target.value; state.scopeResult = null; invalidatePreflight(); render(false);
  }
});
document.addEventListener("keydown", (event) => {
  if (event.isComposing) return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openTaskSearch(); return; }
  if (event.target.id === "command-search" && ["ArrowDown", "Enter"].includes(event.key)) {
    event.preventDefault();
    const first = document.querySelector(".command-result");
    if (event.key === "Enter") first?.click();
    else first?.focus();
  } else if (event.target.closest(".command-result") && ["ArrowDown", "ArrowUp"].includes(event.key)) {
    event.preventDefault();
    const links = [...document.querySelectorAll(".command-result")];
    const index = links.indexOf(event.target.closest(".command-result"));
    const next = event.key === "ArrowDown" ? Math.min(links.length-1,index+1) : index-1;
    if (next < 0) document.querySelector("#command-search").focus();
    else links[next]?.focus();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.target.getAttribute("role") !== "tab" || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const tabs = [...event.target.closest('[role="tablist"]').querySelectorAll('[role="tab"]')];
  const current = tabs.indexOf(event.target);
  const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  tabs[next].click();
});
function toggleMenu(open) {
  const mobile = window.matchMedia("(max-width: 700px)").matches;
  document.querySelector("#sidebar").inert = mobile && !open;
  document.querySelector("#sidebar").setAttribute("aria-hidden", String(mobile && !open));
  document.body.classList.toggle("mobile-menu-open", open);
  document.querySelector("#nav-backdrop").hidden = !open;
  document.querySelector("#menu-toggle").setAttribute("aria-expanded", String(open));
}
document.querySelector("#menu-toggle").addEventListener("click", () => toggleMenu(!document.body.classList.contains("mobile-menu-open")));
document.querySelector("#nav-backdrop").addEventListener("click", () => toggleMenu(false));
document.addEventListener("keydown", (event) => { if (event.key === "Escape") toggleMenu(false); });
window.matchMedia("(max-width: 700px)").addEventListener("change", () => toggleMenu(false));
window.addEventListener("hashchange", () => { state.detailTab = "evidence"; render(); });
paintIcons();
render(false);
