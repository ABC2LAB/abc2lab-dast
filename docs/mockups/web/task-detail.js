"use strict";

// A task is one synthetic run. Every detail view resolves its scope from the
// URL so following evidence links cannot silently switch to another task.
const taskRoutes = ["scan", "results", "finding", "coverage", "assets", "knowledge", "flow", "reproduction", "report"];

function taskRun() {
  const [route, id, runId] = location.hash.slice(1).split("/");
  if (!taskRoutes.includes(route)) return null;
  const requested = route === "finding" ? runId : id;
  return requested ? allRuns().find((run) => run.id === requested) : route === "scan" ? state.run || state.resultRun : state.resultRun;
}

function taskSectionHeading(title, subtitle, actions = "") {
  return `<div class="page-heading task-section-heading"><div><h2>${title}</h2><p class="page-subtitle">${subtitle}</p></div><div class="heading-actions">${actions}</div></div>`;
}

function refreshTaskProgress() {
  const progress = document.querySelector(".task-progress-line");
  const run = taskRun();
  if (!progress || !run) return;
  const stage = progress.querySelector("span");
  if (stage.textContent !== stageNames[run.stage]) stage.textContent = stageNames[run.stage];
  progress.querySelector("strong").textContent = `${run.progress}%`;
  progress.querySelector('[role="progressbar"]').setAttribute("aria-valuenow", run.progress);
  progress.querySelector(".progress-bar").style.width = `${run.progress}%`;
}

function taskHeader(run) {
  const route = getRoute().name;
  const active = ["assets", "knowledge", "flow"].includes(route) ? "assets" : route === "finding" ? "results" : route;
  const progress = run.status === "complete" ? 100 : run.progress;
  return `<header class="task-header">
    <a class="back-link task-back" href="#scans">${icon("left")}진단 작업 목록</a>
    <div class="task-heading"><div><p class="task-eyebrow">DIAGNOSTIC TASK · ${run.id}</p><h1 class="page-title" tabindex="-1">${escapeHtml(run.name)}</h1></div><div class="heading-actions">${run.status === "running" ? button("진단 중지", "stop-run", "secondary", "stop") + button("데모 빠르게 완료", "finish-run", "primary", "arrow") : `<a class="button secondary" href="#report/${run.id}">${icon("file")}보고서 보기</a>`}</div></div>
    <div class="task-metadata">${runBadge(run.status)}<span>${icon("globe")}${escapeHtml(run.target.name)}</span><span>${escapeHtml(run.target.url)}</span><span>${icon("clock")}${escapeHtml(run.date)}</span>${badge("가상 작업", "purple")}</div>
    ${progress !== undefined ? `<div class="task-progress-line"><span role="status" aria-live="polite" aria-atomic="true">${run.status === "running" ? stageNames[run.stage] : run.status === "stopped" ? "사용자 중단 · 미완료 상태 보존" : "가상 진단 처리 완료"}</span><strong>${progress}%</strong><div class="progress-track" role="progressbar" aria-label="작업 진행률" aria-valuenow="${progress}" aria-valuemin="0" aria-valuemax="100"><div class="progress-bar" style="width:${progress}%"></div></div></div>` : ""}
    <nav class="task-tabs" aria-label="작업 상세 메뉴">${[["scan", "activity", "요약"], ["assets", "globe", "그래프"], ["results", "shield", "취약점·판정"], ["reproduction", "flask", "재현 현황"], ["coverage", "grid", "검사 범위"], ["report", "file", "보고서·설정"]].map(([key, glyph, label]) => `<a href="#${key}/${run.id}" ${active === key ? 'aria-current="page"' : ""}>${icon(glyph)}${label}</a>`).join("")}</nav>
  </header>`;
}

function taskOverview(run) {
  const rows = coverageRows(run);
  const cases = findingsForRun(run);
  const verified = cases.filter((item) => item.value === "confirmed");
  const complete = rows.filter((row) => row.status === "complete").length;
  const limited = rows.filter((row) => ["limited", "unknown"].includes(row.status)).length;
  const running = run.status === "running";
  const logs = run.logs || [{ time: run.date.split(" ")[1], text: run.status === "partial" ? "일부 항목을 확인하지 못했습니다. 사유와 기록을 검토하세요." : "가상 진단의 결과와 저장 기록을 검토할 수 있습니다.", kind: "info" }];
  return `${taskSectionHeading("작업 요약", running ? "검사가 진행되는 동안 같은 작업에서 그래프와 비교 현황을 살펴보세요." : "이 작업에서 확인한 결과와 아직 확인하지 못한 범위를 함께 살펴보세요.")}${retestBanner(run)}
    <div class="task-summary-grid">${[["확인된 취약점", `${verified.length}건`, running ? "최종 판정 전 · 집계 대기" : run.status === "stopped" ? "중단 · 최종 판정 미발행" : "근거를 확인한 판정 예시"], ["비교·검사 처리", `${complete} / ${rows.length}`, "이번 작업에 선택한 항목 기준"], ["추가 확인 필요", `${limited}건`, "정책 부족·전송 불명 등 사유 보존"], ["PoC 문서화", `${verified.length}건`, "별도 재실행 없이 작성된 예시"]].map(([label, value, note]) => `<div class="task-metric"><small>${label}</small><strong>${value}</strong><p>${note}</p></div>`).join("")}</div>
    <div class="task-overview-grid"><div>
      <section class="card"><div class="card-header"><h2 class="section-title">진단 진행 흐름</h2>${runBadge(run.status)}</div><div class="card-body"><div class="task-stage-strip">${stageNames.map((name, index) => {
        const done = run.status === "complete" || run.stage !== undefined && index < run.stage;
        const current = run.stage === index && run.status !== "complete";
        const label = done ? "완료" : current ? running ? "진행 중" : "중단됨" : run.status === "partial" ? "기록 확인 필요" : "대기";
        return `<div class="${done ? "complete" : current ? running ? "active" : "stopped" : ""}"><span>${done ? icon("check") : index + 1}</span><strong>${name}</strong><small>${label}</small></div>`;
      }).join("")}</div><p class="small-text muted mt-16">가상 진행 상태입니다. 실제 대상 통신은 없으며, 완료는 전체 웹의 안전을 뜻하지 않습니다.</p></div></section>
      <section class="card mt-24"><div class="card-header"><h2 class="section-title">최근 진행 내역</h2><a class="text-link" href="#flow/${run.id}">흐름으로 보기 ${icon("arrow")}</a></div><div class="task-activity-list" role="log" aria-label="작업 진행 내역">${logs.slice(-6).map((entry) => `<div class="task-activity-item">${icon(entry.kind === "success" ? "check" : entry.kind === "warning" ? "alert" : "activity")}<div><strong>${escapeHtml(entry.text)}</strong><time>${escapeHtml(entry.time)} · 합성 기록</time></div></div>`).join("")}</div></section>
    </div><aside><section class="card"><div class="card-header"><h2 class="section-title">이 작업 살펴보기</h2></div><div class="task-links">${[["assets", "globe", "자산·지식 그래프", "발견 경로와 계정·자원·정책 관계"], ["reproduction", "flask", "재현·비교 현황", "기준·교차 검사와 근거 처리 상태"], ["results", "shield", "취약점과 판정 근거", running ? "판정 완료 뒤 결과와 PoC 검토" : `${verified.length}건의 확인된 취약점과 판정 한계`], ["coverage", "grid", "미완료 범위", "차단·미실행·전송 불명 사유"]].map(([key, glyph, title, text]) => `<a href="#${key}/${run.id}">${icon(glyph)}<div><strong>${title}</strong><span>${text}</span></div>${icon("chevron")}</a>`).join("")}</div></section><div class="detail-tip mt-24">${icon("info")}<p>현재 작업의 기록만 표시합니다. 재현 현황을 열거나 그래프를 재생해도 새 대상 요청은 발생하지 않습니다.</p></div></aside></div>`;
}

function reproductionState(row, run) {
  const item = findingsForRun(run).find((entry) => entry.id === row.id);
  if (row.status === "blocked") return { label: "정책 차단", color: "warning", text: "보호 규칙으로 미전송", item };
  if (row.status === "not_run") return { label: "미실행", color: "neutral", text: "확인하지 못한 범위", item };
  if (row.status === "unknown") return { label: "전송 불명", color: "warning", text: "응답 근거 미확보 · 자동 재전송 없음", item };
  if (row.status === "waiting") {
    const current = coverageRows(run).find((entry) => entry.status === "waiting")?.id === row.id && run.stage >= 1;
    return { label: current ? run.stage >= 2 ? "비교 검증 중" : "후보 탐색 중" : "대기 중", color: current ? "purple" : "neutral", text: "가상 진행 · 판정 확정 전", item };
  }
  if (!item) return { label: row.status === "limited" ? "일부 확인" : "관찰 기록 보존", color: row.status === "limited" ? "warning" : "info", text: run.status === "stopped" ? "작업 중단 · 최종 판정 미발행" : "최종 판정 대기 · 합성 기록", item };
  if (item.value === "confirmed") return { label: "재현 근거 확보", color: "success", text: "PoC 문서화 · 별도 재실행 없음", item };
  return { label: item.retestOutcome === "not-reproduced" ? "이번 조건에서 미재현" : item.value === "suspected" ? "정책 추가 확인" : item.value === "allowed" ? "정책상 접근 허용" : "확인 불가", color: item.value === "allowed" ? "info" : "warning", text: item.value === "allowed" ? "취약점 PoC 제공 대상 아님" : "판정 한계와 미확인 사유 보존", item };
}

function reproductionDetail(row, run) {
  const info = reproductionState(row, run);
  return `<section class="card mt-24" aria-label="선택한 재현 상세"><div class="card-header"><h2 class="section-title">${escapeHtml(row.title)} · ${row.id}</h2>${badge(info.label, info.color)}</div><div class="card-body"><div class="endpoint-box"><span class="method">GET</span><code>${escapeHtml(row.path)}</code></div><div class="task-stage-detail">${["기준 관찰 A", "교차 관찰 B", "정책 근거"].map((label, index) => `<div><strong>${label}</strong>${coverageSignal(row.signals[index])}</div>`).join("")}</div><p>${escapeHtml(row.reason)}</p><p class="small-text muted">${info.text}. 표시된 처리 상태는 취약점 판정이나 수정 완료와 구분합니다.</p><div class="heading-actions"><a class="button secondary" href="#flow/${run.id}/${row.id}">${icon("activity")}처리 흐름 보기</a>${info.item ? `<a class="button secondary" href="#finding/${row.id}/${run.id}">${icon("file")}${info.item.value === "confirmed" ? "근거·재현 절차 보기" : "판정 근거 보기"}</a>` : ""}</div></div></section>`;
}

function reproduction() {
  const run = taskRun();
  const rows = coverageRows(run);
  const selected = rows.find((row) => row.id === state.reproductionSelected) || rows.find((row) => row.status === "waiting") || rows[0];
  return `${taskSectionHeading("재현·비교 현황", "기준 요청과 교차 검사의 처리 상태를 사례별로 확인하세요.")}
    <div class="scan-notice">${icon("flask")}<div><strong>${run.status === "running" ? "진단 중 수행하는 비교 검사의 가상 진행입니다" : "이 작업의 비교 기록과 재현 근거를 검토합니다"}</strong><p>PoC는 확보한 기록으로 문서화합니다. 별도의 자동 재실행은 없으며, 수정 확인은 사례 상세에서 새 작업으로 시작합니다.</p></div></div>
    <section class="card mt-24"><div class="card-header"><h2 class="section-title">사례별 처리 상태<span class="section-count">${rows.length}</span></h2>${badge(run.status === "running" ? "진행 시연" : "저장 기록 예시", "purple")}</div><div class="task-reproduction-list">${rows.map((row) => {
      const info = reproductionState(row, run);
      return `<div class="reproduction-row"><span class="reproduction-icon ${info.color}">${icon(info.color === "purple" ? "activity" : info.color === "success" ? "check" : info.color === "warning" ? "alert" : "flask")}</span><div class="reproduction-copy"><strong>${escapeHtml(row.title)}</strong><small>${row.id} · GET ${escapeHtml(row.path)}</small></div><div class="reproduction-status">${badge(info.label, info.color)}<small>${info.text}</small></div><div class="reproduction-actions">${button("상세", "select-reproduction", "ghost small", "chevron", `data-value="${row.id}" aria-label="${row.id} 재현 상세" aria-pressed="${selected.id === row.id}"`)}</div></div>`;
    }).join("")}</div></section>${selected ? reproductionDetail(selected, run) : ""}`;
}

function taskReport() {
  const run = taskRun();
  const profile = run.modelProfile;
  const limits = run.executionLimits;
  const reportReady = run.status !== "running";
  return `${taskSectionHeading("보고서·작업 설정", "이 작업을 시작할 때 적용한 설정과 결과 내보내기를 확인하세요.")}
    <section class="card"><div class="card-body"><h2 class="section-title">${reportReady ? "진단 기록 내보내기" : "보고서 준비 중"}</h2><p>${reportReady ? "판정·근거·PoC 문서화 예시와 함께 미완료 범위를 보존합니다." : "작업이 끝나면 같은 상세 페이지에서 가상 보고서를 내려받을 수 있습니다."}</p>${button("HTML 보고서 다운로드", "export-report", "primary", "download", reportReady ? "" : "disabled")}<p class="small-text muted mt-16">합성 데이터 보고서이며 실제 검증·재실행 증명은 아닙니다.</p></div></section>
    <div class="task-config-grid mt-24"><section class="card"><div class="card-body"><h2 class="section-title">대상·계정</h2><dl class="detail-meta"><div><dt>대상</dt><dd>${escapeHtml(run.target.name)}</dd></div><div><dt>주소</dt><dd>${escapeHtml(run.target.url)}</dd></div><div><dt>소유자 / 평가 계정</dt><dd>${accountLabel(run.owner || "buyer-a")} / ${accountLabel(run.evaluated || "buyer-b")}</dd></div><div><dt>검사 유형</dt><dd>수평 접근 권한 · 읽기 검사</dd></div></dl></div></section><section class="card"><div class="card-body"><h2 class="section-title">모델·실행 설정</h2><dl class="detail-meta"><div><dt>연결 방식</dt><dd>${profile ? profile.provider === "ollama" ? "Ollama" : "외부/내부 API" : "이 과거 예시에는 설정 기록 없음"}</dd></div><div><dt>선택 모델</dt><dd>${escapeHtml(profile?.model || "기록 없음")}</dd></div><div><dt>실행 한도</dt><dd>${limits ? `최대 ${limits.maxAttempts}회 · ${limits.maxDuration}분 · 동시 ${limits.concurrency}개` : "기록 없음"}</dd></div></dl><p class="small-text muted">작업 시작 시의 설정입니다. 새 작업에서 설정을 바꿔도 이 작업은 바뀌지 않습니다. 인증 값은 표시·보관하지 않습니다.</p></div></section></div>`;
}

document.addEventListener("click", (event) => {
  const element = event.target.closest('[data-action="select-reproduction"]');
  if (!element) return;
  state.reproductionSelected = element.dataset.value;
  render(false);
});
