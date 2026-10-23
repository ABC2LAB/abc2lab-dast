"use strict";

// Synthetic web-surface data is deliberately separate from the evidence/KG
// graph. It describes discovered structure only; it does not infer a request,
// response, identity verification, or a vulnerability verdict.
const surfaceFixtures = [
  { caseId: "CASE-001", pageId: "page-orders", pageLabel: "/orders" },
  { caseId: "CASE-002", pageId: "page-profile", pageLabel: "/account/profile" },
  { caseId: "CASE-003", pageId: "page-invoices", pageLabel: "/billing/invoices" },
  { caseId: "CASE-004", pageId: "page-addresses", pageLabel: "/account/addresses" },
  { caseId: "CASE-005", pageId: "page-team-documents", pageLabel: "/teams/documents" },
  { caseId: "CASE-006", pageId: "page-files", pageLabel: "/files" },
];

function surfaceReady(run) {
  if (!run) return false;
  return !(run.status === "running" || run.status === "stopped") || run.stage >= 1;
}

function surfaceParameters(path) {
  return [...String(path).matchAll(/\{([^}]+)\}/g)].map((match) => match[1]);
}

function surfaceRows(run) {
  if (!surfaceReady(run) || typeof coverageRows !== "function") return [];
  const rows = coverageRows(run);
  return surfaceFixtures.map((fixture) => {
    const row = rows.find((candidate) => candidate.id === fixture.caseId);
    if (!row?.item) return null;
    return { ...fixture, method: row.method || "미확인", path: row.path, resource: row.item.resource };
  }).filter(Boolean);
}

/** Return the discovered pages, endpoints, parameters, resources, and bindings for a run. */
function surfaceInventory(run) {
  const rows = surfaceRows(run);
  const pages = rows.map(({ pageId, pageLabel, caseId }) => ({ id: pageId, label: pageLabel, caseId }));
  const endpoints = rows.map((row) => ({
    id: `endpoint-${row.caseId.toLowerCase()}`,
    caseId: row.caseId,
    method: row.method,
    path: row.path,
    parameters: surfaceParameters(row.path),
    pageId: row.pageId,
  }));
  const resources = rows.map((row) => ({ id: `resource-${row.caseId.toLowerCase()}`, caseId: row.caseId, label: row.resource }));
  const bindings = rows.map((row) => ({ caseId: row.caseId, pageId: row.pageId, endpointId: `endpoint-${row.caseId.toLowerCase()}`, resourceId: `resource-${row.caseId.toLowerCase()}` }));
  return { pages, endpoints, resources, bindings, candidateCount: endpoints.length, parameterCount: endpoints.reduce((count, endpoint) => count + endpoint.parameters.length, 0) };
}

/** Render four calculated discovery KPIs for the selected run. */
function surfaceKpis(run) {
  const inventory = surfaceInventory(run);
  const source = run ? `${run.id} · 합성 탐색 자료` : "선택된 작업 없음";
  const cards = [
    ["탐색된 페이지", inventory.pages.length, "페이지 구조"],
    ["수집된 API", inventory.endpoints.length, "엔드포인트 후보"],
    ["발견된 파라미터", inventory.parameterCount, "경로 변수 이름"],
    ["진단 후보", inventory.candidateCount, "검사에 연결된 사례"],
  ];
  return `<section class="surface-stats stats-grid" aria-label="웹 표면 요약">${cards.map(([label, value, note]) => `<div class="stat-card"><div class="stat-card-heading"><span>${label}</span>${icon("globe")}</div><strong>${value}</strong><small>${note} · ${escapeHtml(source)}</small></div>`).join("")}</section>`;
}

/** Render a compact User/Role → Page → Endpoint → Resource overview. */
function surfaceSummary(run) {
  const inventory = surfaceInventory(run);
  if (!inventory.pages.length) return `<section class="surface-summary card" aria-label="웹 구조 요약"><div class="card-header"><h2 class="section-title">웹 구조 요약</h2><span class="small-text muted">탐색 대기</span></div><div class="surface-empty">${icon("globe")}<strong>탐색 자료가 아직 없습니다</strong><p>웹 기능 탐색 자료가 준비되면 이 작업의 페이지·엔드포인트 구조가 표시됩니다.</p></div></section>`;
  const paths = inventory.bindings.slice(0, 4).map((binding) => {
    const page = inventory.pages.find((item) => item.id === binding.pageId);
    const endpoint = inventory.endpoints.find((item) => item.id === binding.endpointId);
    const resource = inventory.resources.find((item) => item.id === binding.resourceId);
    return { binding, page, endpoint, resource };
  });
  const node = (x, y, label, type, caseId, title) => `<a href="#knowledge/${run.id}" class="surface-svg-node ${type}" xlink:href="#knowledge/${run.id}" aria-label="${escapeHtml(`${caseId} ${title} ${label}`)}"><title>${escapeHtml(`${caseId} · ${title} · ${label}`)}</title><circle cx="${x}" cy="${y}" r="14"></circle><text x="${x + 20}" y="${y + 5}">${escapeHtml(label)}</text></a>`;
  const lines = paths.map(({ binding, page, endpoint, resource }, index) => {
    const y = 54 + index * 42;
    return `<path class="surface-svg-edge" d="M92 ${index % 2 ? 180 : 60} C150 ${index % 2 ? 180 : 60}, 164 ${y}, 208 ${y}"></path><path class="surface-svg-edge" d="M222 ${y} C280 ${y}, 324 ${y}, 362 ${y}"></path><path class="surface-svg-edge" d="M390 ${y} C444 ${y}, 490 ${y}, 534 ${y}"></path>${node(208, y, page.label, "page", binding.caseId, "페이지")}${node(376, y, endpoint.method, "endpoint", binding.caseId, endpoint.path)}${node(548, y, resource.label, "resource", binding.caseId, "자원")}`;
  }).join("");
  return `<section class="surface-summary card" aria-label="웹 구조 요약"><div class="card-header"><div><h2 class="section-title">웹 구조 요약</h2><p class="small-text muted">등록된 사용자·역할에서 발견된 페이지와 API 후보를 연결합니다.</p></div><a class="button secondary small" href="#knowledge/${run.id}">자세히 보기 ${icon("arrow")}</a></div><div class="surface-mini-graph"><div class="surface-legend"><span><i class="account"></i>사용자·역할</span><span><i class="page"></i>페이지</span><span><i class="endpoint"></i>엔드포인트</span><span><i class="resource"></i>자원</span></div><div class="surface-mini-canvas" tabindex="0" aria-label="웹 구조 요약 그래프. 좌우 스크롤로 이동할 수 있습니다."><svg class="surface-mini-svg" width="640" height="240" viewBox="0 0 640 240" role="group" aria-label="사용자·역할, 페이지, 엔드포인트, 자원 관계 미리보기"><title>사용자·역할 → 페이지 → 엔드포인트 → 자원</title>${lines}${node(92, 60, "소유자 A", "account", "등록", "사용자·역할")}${node(92, 180, "평가자 B", "account", "등록", "사용자·역할")}</svg></div></div><p class="surface-source">출처: ${escapeHtml(run.id)} · 합성 탐색·등록 관계. 전송 성공·신원 검증·판정을 의미하지 않습니다.</p></section>`;
}

function surfaceGraphNode(id, label, type, x, y, caseId, description, meta) {
  const node = graphNode(id, label, type, x, y, ["page", "endpoint"].includes(type) ? "observed" : "registered", description, meta);
  node.caseId = caseId;
  return node;
}

function surfaceGraphEdge(id, from, to, label, caseId, description) {
  const edge = graphEdge(id, from, to, label, label === "API 후보" ? "observed" : "registered", description);
  edge.caseId = caseId;
  return edge;
}

/** Build a four-column structure graph from explicit discovered-path fixtures. */
function surfaceGraph(context) {
  const run = context?.run || taskRun();
  const inventory = surfaceInventory(run);
  const available = new Set(inventory.endpoints.map((endpoint) => endpoint.caseId));
  const selectedCases = new Set(inventory.bindings.slice(0, 4).map((binding) => binding.caseId));
  const expandForFilter = Boolean(graphState.search?.trim()) || graphState.relation !== "all";
  const rows = surfaceFixtures.filter((fixture) => available.has(fixture.caseId) && (graphState.detailed || expandForFilter || selectedCases.has(fixture.caseId)));
  const nodes = [];
  const edges = [];
  if (rows.length) {
    nodes.push(surfaceGraphNode("surface-owner", `${accountLabel(run.owner || "buyer-a")} · 소유자`, "account", 140, 210, null, "등록된 소유자 프로필입니다. 신원 검증 결과를 주장하지 않습니다.", "owner · 등록 프로필"));
    nodes.push(surfaceGraphNode("surface-evaluated", `${accountLabel(run.evaluated || "buyer-b")} · 평가`, "account", 140, 430, null, "등록된 평가 프로필입니다. 신원 검증 결과를 주장하지 않습니다.", "evaluated · 등록 프로필"));
  }
  rows.forEach((fixture, index) => {
    const row = inventory.endpoints.find((endpoint) => endpoint.caseId === fixture.caseId);
    const resource = inventory.resources.find((item) => item.caseId === fixture.caseId);
    const y = 154 + index * 128;
    const prefix = fixture.caseId.toLowerCase();
    const ids = { page: `${prefix}-page`, endpoint: `${prefix}-endpoint`, resource: `${prefix}-resource` };
    nodes.push(surfaceGraphNode(ids.page, fixture.pageLabel, "page", 420, y, fixture.caseId, "합성 탐색에서 연결한 페이지 구조입니다.", "페이지 발견"));
    const endpointNode = surfaceGraphNode(ids.endpoint, row.path, "endpoint", 700, y, fixture.caseId, "발견된 엔드포인트 후보와 경로 변수 이름입니다.", `${row.parameters.length ? `변수: ${row.parameters.join(", ")}` : "변수 없음"}`);
    endpointNode.method = row.method;
    nodes.push(endpointNode);
    nodes.push(surfaceGraphNode(ids.resource, resource.label, "resource", 980, y, fixture.caseId, "엔드포인트에 등록된 자원 이름입니다. 응답·비교 성공을 의미하지 않습니다.", "자원 연결"));
    edges.push(surfaceGraphEdge(`${prefix}-owner-page`, "surface-owner", ids.page, "역할 연결", fixture.caseId, "등록 프로필에서 페이지 구조로 이어진 합성 관계입니다."));
    edges.push(surfaceGraphEdge(`${prefix}-evaluated-page`, "surface-evaluated", ids.page, "역할 연결", fixture.caseId, "평가 프로필에서 페이지 구조로 이어진 합성 관계입니다."));
    edges.push(surfaceGraphEdge(`${prefix}-page-endpoint`, ids.page, ids.endpoint, "API 후보", fixture.caseId, "페이지에서 발견된 엔드포인트 후보입니다."));
    edges.push(surfaceGraphEdge(`${prefix}-endpoint-resource`, ids.endpoint, ids.resource, "자원 연결", fixture.caseId, "등록된 자원 이름과 엔드포인트 후보의 관계입니다."));
  });
  const height = rows.length ? Math.max(540, rows.length * 128 + 120) : 380;
  return { nodes, edges, width: 1120, height, lanes: graphLanes([["01 · 사용자·역할", "등록 프로필"], ["02 · 페이지", "탐색 구조"], ["03 · 엔드포인트", "API 후보"], ["04 · 자원", "등록 연결"]], height), note: "웹 구조 그래프는 발견·등록 관계를 보여줍니다. 근거·판정 그래프와 다르며 전송 성공, 신원 검증, 취약점 판정을 추정하지 않습니다.", surfaceTree: true, totalPaths: inventory.bindings.length };
}

/** Explain the surface graph scope and report displayed paths from graph nodes. */
function surfaceGraphOverview(context, model) {
  const run = context?.run || taskRun();
  const endpoints = (model?.nodes || []).filter((node) => node.type === "endpoint");
  const total = model?.totalPaths ?? endpoints.length;
  return `<section class="graph-overview" id="graph-overview" aria-label="웹 구조 그래프 안내"><div><strong>사용자·역할 → 페이지 → 엔드포인트 → 자원</strong><p>표시 경로 ${endpoints.length}개 · 작업 전체 ${total}개 · ${escapeHtml(run?.id || "선택된 작업 없음")}</p></div><div class="graph-overview-legend"><span><i class="account"></i>사용자·역할</span><span><i class="page"></i>페이지</span><span><i class="endpoint"></i>엔드포인트</span><span><i class="resource"></i>자원</span></div><small>합성 탐색 자료 · 페이지·API·자원을 선택한 뒤 관련 사례로 이동할 수 있습니다.</small></section>`;
}

/** Keep the task graph's type headings while giving its links an open canvas. */
function surfaceGraphBackground(model) {
  return model.lanes.map((lane) => `<g class="surface-column-heading"><text x="${lane.x + 16}" y="34">${escapeHtml(lane.title)}</text><text class="surface-column-subtitle" x="${lane.x + 16}" y="56">${escapeHtml(lane.subtitle)}</text></g>`).join("");
}

/** Connect the same circular anchors used by the dashboard's visual language. */
function surfaceEdgeGeometry(edge, model) {
  const from = model.nodes.find((node) => node.id === edge.from);
  const to = model.nodes.find((node) => node.id === edge.to);
  const x1 = from.x - 80 + 22, y1 = from.y - 1;
  const x2 = to.x - 80 - 22, y2 = to.y - 1;
  const bend = Math.max(56, (x2 - x1) * .45);
  return { path: `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`, x: (x1 + x2) / 2, y: (y1 + y2) / 2 };
}

/** Render a keyboard-selectable circle with its full details kept in the inspector. */
function surfaceNodeSvg(node) {
  const [kind, symbol] = graphNodeTypes[node.type];
  const lines = graphLabelLines(node.label, 140, 14, 650);
  const status = graphStatuses[node.status].label;
  return `<g class="graph-node surface-node ${node.type} type-${node.type} status-${node.status} ${graphState.node === node.id ? "selected" : ""}" transform="translate(${node.x - 112},${node.y - 56})" role="button" tabindex="0" aria-label="${escapeHtml(node.label)} · ${kind} · ${status}" aria-pressed="${graphState.node === node.id}" data-action="graph-node" data-value="${node.id}" aria-controls="graph-detail"><title>${escapeHtml(node.label)} · ${escapeHtml(node.meta)} · ${status}</title><rect class="surface-node-hit" x="2" y="3" width="220" height="106" rx="12"/><circle class="surface-node-ring" cx="32" cy="55" r="28"/><circle class="surface-node-disc" cx="32" cy="55" r="22"/><svg class="surface-node-symbol" x="22" y="45" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[symbol]}</svg><text class="surface-node-kind" x="68" y="25">${escapeHtml(node.method ? `${node.method} · ${kind}` : node.type === "account" ? "사용자·역할" : kind)}</text>${lines.map((line,index) => `<text class="surface-node-label" x="68" y="${49 + index * 18}">${escapeHtml(line)}</text>`).join("")}<text class="surface-node-status" x="68" y="94">${status}</text></g>`;
}
