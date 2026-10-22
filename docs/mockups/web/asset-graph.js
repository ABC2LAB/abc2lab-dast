"use strict";

// Synthetic endpoint inventory only. URL parsing and grouping do not send requests.
const ASSET_GROUP_LIMIT = 4;
const ASSET_ROW_GAP = 128;

function assetInventory(context) {
  const origin = new URL(context.run.target.url);
  return context.rows.map((row) => ({
    id: `endpoint-${row.id}`, row, method: row.method || "미확인", path: row.path,
    group: `/${row.path.split("/").filter(Boolean)[0] || ""}`,
    origin: origin.origin, hostname: origin.hostname,
    service: `${origin.protocol === "https:" ? "HTTPS" : "HTTP"} :${origin.port || (origin.protocol === "https:" ? "443" : "80")}`,
    parameters: [...row.path.matchAll(/\{([^}]+)\}/g)].map((match) => match[1]),
    source: "합성 경로 목록",
  }));
}

function assetMatches(endpoint) {
  const query = graphState.search.trim().toLowerCase();
  return (graphState.relation === "all" || endpoint.row.status === graphState.relation)
    && `${endpoint.hostname} ${endpoint.service} ${endpoint.method} ${endpoint.path} ${endpoint.row.title} ${endpoint.row.id}`.toLowerCase().includes(query);
}

function assetGroupRows(endpoints) {
  const groups = new Map();
  endpoints.forEach((endpoint) => {
    if (!groups.has(endpoint.group)) groups.set(endpoint.group, []);
    groups.get(endpoint.group).push(endpoint);
  });
  return [...groups.entries()].map(([path, items]) => ({ id: `group-${encodeURIComponent(path)}`, path, items }));
}

function assetPreferred(endpoints) {
  const first = [endpoints[0], ...["unknown", "blocked", "not_run", "waiting"].map((status) => endpoints.find((endpoint) => endpoint.row.status === status))].filter(Boolean);
  return [...new Set([...first, ...endpoints])];
}

function assetGraph(context) {
  const inventory = assetInventory(context);
  const groups = assetGroupRows(inventory.filter(assetMatches));
  const filtered = Boolean(graphState.search.trim()) || graphState.relation !== "all";
  const nodes = [], edges = [];
  let nextY = 154;
  const groupCenters = [];
  groups.forEach((group) => {
    const limit = filtered ? group.items.length : (graphState.assetLimits[group.id] ?? ASSET_GROUP_LIMIT);
    const preferred = new Set(assetPreferred(group.items).slice(0, limit));
    const visible = group.items.filter((endpoint) => preferred.has(endpoint));
    const hidden = group.items.filter((endpoint) => !preferred.has(endpoint));
    const startY = nextY;
    visible.forEach((endpoint) => {
      const node = graphNode(endpoint.id, endpoint.path, "endpoint", 980, nextY, rowGraphStatus(endpoint.row), endpoint.row.reason, `${endpoint.method} · ${endpoint.row.title}`);
      Object.assign(node, { endpoint, statusLabel: coverageStates[endpoint.row.status].label, method: endpoint.method });
      nodes.push(node);
      edges.push(graphEdge(`route-${endpoint.row.id}`, group.id, endpoint.id, "경로 포함", "registered", "경로 템플릿의 구조적 포함 관계입니다. 요청 전송이나 접근 허용을 증명하지 않습니다."));
      nextY += ASSET_ROW_GAP;
    });
    if (hidden.length) {
      const fold = graphNode(`fold-${group.id}`, `엔드포인트 ${hidden.length}개 더`, "fold", 980, nextY, "registered", "같은 경로 그룹에서 접어 둔 엔드포인트입니다. 선택하면 목록을 확인하고 더 펼칠 수 있습니다.", `${group.path} · 접힌 항목`);
      Object.assign(fold, { group, hidden, statusLabel: `${hidden.length}개 접힘` });
      nodes.push(fold);
      edges.push(graphEdge(`fold-edge-${group.id}`, group.id, fold.id, "묶음", "registered", `${hidden.length}개 엔드포인트가 생략되어 있습니다. 검사 상태는 각 항목에서 확인합니다.`));
      nextY += ASSET_ROW_GAP;
    }
    const center = startY + Math.min(2, Math.max(0, visible.length + (hidden.length ? 1 : 0) - 1)) * ASSET_ROW_GAP / 2;
    const node = graphNode(group.id, group.path, "group", 700, center, "registered", "경로 첫 구간이 같은 엔드포인트를 묶었습니다. 별도 페이지나 서버의 존재를 추정하지 않습니다.", `${group.items.length}개 엔드포인트`);
    Object.assign(node, { group, hidden, statusLabel: `${visible.length}/${group.items.length}개 표시` });
    nodes.push(node);
    edges.push(graphEdge(`service-${group.id}`, "service", group.id, "경로 그룹", "registered", "같은 origin의 URL 경로를 묶은 표시입니다."));
    groupCenters.push(center);
  });
  const height = Math.max(550, nextY - 40);
  if (groups.length) {
    const sample = inventory[0];
    const center = Math.min(350, (groupCenters[0] + groupCenters.at(-1)) / 2);
    const domain = graphNode("target", sample.hostname, "target", 140, center, "registered", "이번 작업의 등록 origin에서 읽은 도메인입니다. 추가 서브도메인이나 IP는 추정하지 않습니다.", context.run.target.name);
    domain.statusLabel = "등록 대상";
    const service = graphNode("service", sample.service, "service", 420, center, "registered", "등록 URL의 scheme과 명시적 또는 기본 포트입니다. 서버 응답이나 기술 스택을 확인했다는 의미는 아닙니다.", sample.origin);
    service.statusLabel = "등록 URL 기준";
    nodes.unshift(domain, service);
    edges.unshift(graphEdge("domain-service", "target", "service", "웹 서비스", "registered", "등록 origin의 도메인·프로토콜·포트 관계입니다."));
  }
  return {
    nodes, edges, inventory, groups, assetTree: true, width: 1120, height,
    lanes: graphLanes([["01 · 도메인", "작업의 등록 대상"], ["02 · 웹 서비스", "프로토콜 · 포트"], ["03 · 경로 그룹", "URL 첫 구간으로 묶기"], ["04 · 엔드포인트", "메서드 · 경로 템플릿"]], height),
    note: `현재 작업의 합성 경로 ${inventory.length}개를 자산으로 묶었습니다. 발견·등록 단서는 전송·검사 완료와 별개이며, 미발견 자산이나 웹 전체 구조는 알 수 없습니다.`,
  };
}

function assetGroupActions(node) {
  const group = node.group;
  const filtered = Boolean(graphState.search.trim()) || graphState.relation !== "all";
  if (!group || filtered) return "";
  return `<div class="asset-group-actions">${node.hidden.length ? button(`${Math.min(ASSET_GROUP_LIMIT, node.hidden.length)}개 더 펼치기`, "asset-expand-group", "secondary small", "plus", `data-value="${group.id}"`) : ""}${button("이 그룹 접기", "asset-collapse-group", "ghost small", "", `data-value="${group.id}"`)}</div>`;
}

function assetEndpointList(endpoints) {
  return `<ul class="asset-endpoint-list">${endpoints.map((endpoint) => `<li><button type="button" data-action="asset-select-endpoint" data-value="${endpoint.id}"><span class="asset-method">${endpoint.method}</span><span class="asset-endpoint-path">${escapeHtml(endpoint.path)}<small>${escapeHtml(endpoint.row.title)}</small></span>${badge(coverageStates[endpoint.row.status].label, coverageStates[endpoint.row.status].color)}${icon("chevron")}</button></li>`).join("")}</ul>`;
}

function assetDetail(context, model, node) {
  if (!node) return null;
  const endpoint = node.endpoint;
  if (!endpoint && !node.group && !["target", "service"].includes(node.id)) return null;
  const selected = endpoint?.row;
  const verdict = selected && findingsForRun(context.run).find((item) => item.id === selected.id);
  const summary = endpoint ? `${endpoint.method} ${endpoint.path}` : node.label;
  const statusLabel = node.statusLabel || graphStatuses[node.status].label;
  const facts = endpoint ? `<dt>도메인 / Origin</dt><dd>${escapeHtml(endpoint.origin)}</dd><dt>메서드</dt><dd><span class="asset-method">${endpoint.method}</span></dd><dt>경로 템플릿</dt><dd><code>${escapeHtml(endpoint.path)}</code></dd><dt>경로 변수</dt><dd>${endpoint.parameters.length ? endpoint.parameters.map((name) => `<span class="asset-param">${escapeHtml(name)} <small>path</small></span>`).join(" ") : "없음"}</dd><dt>표시 출처</dt><dd>${escapeHtml(endpoint.source)} · 발견/등록 단서 예시</dd><dt>검사 상태</dt><dd>${badge(statusLabel, coverageStates[selected.status].color)}</dd><dt>전송 해석</dt><dd>${selected.status === "unknown" ? "교차 요청 전송 불명 · 자동 재전송 없음" : selected.status === "blocked" ? "보호 규칙으로 미전송" : ["waiting", "not_run"].includes(selected.status) ? "전송 근거 미확인" : selected.item?.value === "allowed" || selected.item?.retestOutcome === "unverified" ? "비교 전송 성공 주장 없음" : "관찰·비교 기록 예시 · 상세 근거 확인"}</dd><dt>연결된 판정</dt><dd>${verdict ? verdictBadge(verdict.value) : "최종 판정 미발행"}</dd>` : `<dt>작업</dt><dd>${escapeHtml(context.run.target.name)} · ${context.run.id}</dd><dt>표시 근거</dt><dd>${node.group ? "URL 경로의 구조적 묶음" : "등록 origin 예시"}</dd><dt>Origin</dt><dd>${escapeHtml(model.inventory[0].origin)}</dd><dt>엔드포인트</dt><dd>${node.group ? `${node.group.items.length}개 · 현재 검색/필터 결과 기준` : `${model.inventory.length}개 · 작업 전체`}</dd>`;
  return `<aside class="card graph-detail asset-detail" id="graph-detail" aria-label="그래프 선택 상세"><div class="graph-detail-heading"><div><p class="graph-kind">${endpoint ? "선택한 엔드포인트" : node.type === "fold" ? "접힌 엔드포인트 묶음" : `선택한 ${graphNodeTypes[node.type][0]}`}</p><h2>${escapeHtml(summary)}</h2></div>${badge(statusLabel, endpoint ? coverageStates[selected.status].color : "neutral")}</div><div class="graph-detail-content"><div><p>${escapeHtml(node.description)}</p>${endpoint ? `<div class="asset-detail-actions">${verdict ? `<a class="button secondary small" href="#finding/${selected.id}/${context.run.id}">관련 판정 근거 ${icon("arrow")}</a>` : ""}<a class="button secondary small" href="#coverage/${context.run.id}">검사 범위 보기 ${icon("arrow")}</a></div><p class="small-text muted">경로 변수는 이름만 표시합니다. 실제 값·헤더·토큰·원문 응답은 포함하지 않습니다.</p>` : node.group ? `${assetGroupActions(node)}${assetEndpointList(node.type === "fold" ? node.hidden : node.group.items)}` : `<p class="small-text muted">IP·서버 종류·프레임워크는 확인 근거가 없어 표시하지 않습니다.</p>`}</div><dl class="graph-detail-list asset-facts">${facts}<dt>참조</dt><dd>${context.run.id} / ${escapeHtml(selected?.id || node.id)}</dd></dl></div></aside>`;
}

function assetOverview(context, model) {
  const shown = model.nodes.filter((node) => node.endpoint).length;
  const matched = model.inventory.filter(assetMatches).length;
  const total = model.inventory.length;
  const limited = context.rows.filter((row) => row.status !== "complete").length;
  const domainCount = model.inventory.length ? 1 : 0;
  return `<section class="graph-overview asset-overview" id="graph-overview" aria-label="그래프 읽기 안내"><div class="asset-summary-grid"><div><span>도메인 · 웹 서비스</span><strong>${domainCount}<small>개</small> · ${domainCount}<small>개</small></strong></div><div><span>엔드포인트 · 작업 전체</span><strong>${total}<small>개</small></strong></div><div><span>화면에 펼침 / 필터 결과</span><strong>${shown} / ${matched}<small>개</small></strong></div><div><span>미완료·추가 확인</span><strong>${limited}<small>개</small></strong></div></div><p class="graph-case-summary"><strong>표시 ${shown}/${total}개 엔드포인트</strong> · 접힌 ${Math.max(0, matched - shown)}개 · 경로 목록은 합성 예시입니다. 발견된 경로가 모두 검사되었다는 뜻은 아닙니다.</p></section>`;
}

function handleAssetAction(action, value) {
  const context = graphContext();
  if (context.mode !== "assets") return false;
  const groups = assetGroupRows(assetInventory(context));
  const group = groups.find((item) => item.id === value);
  if (action === "asset-expand-group" && group) graphState.assetLimits[group.id] = (graphState.assetLimits[group.id] ?? ASSET_GROUP_LIMIT) + ASSET_GROUP_LIMIT;
  else if (action === "asset-collapse-group" && group) { graphState.assetLimits[group.id] = 0; graphState.node = group.id; }
  else if (action === "asset-expand-all") groups.forEach((item) => { graphState.assetLimits[item.id] = item.items.length; });
  else if (action === "asset-default") {
    Object.assign(graphState, { assetLimits: {}, node: null, edge: null, neighbors: false, search: "", relation: "all" });
    document.querySelector("#graph-search").value = "";
    document.querySelector("#graph-relation").value = "all";
  }
  else if (action === "asset-select-endpoint") {
    const endpoint = groups.flatMap((item) => item.items).find((item) => item.id === value);
    if (!endpoint) return false;
    const parent = groups.find((item) => item.items.includes(endpoint));
    graphState.assetLimits[parent.id] = parent.items.length;
    graphState.node = endpoint.id; graphState.edge = null; graphState.neighbors = false;
  } else return false;
  repaintGraph(true);
  if (action === "asset-select-endpoint") {
    const node = buildGraph(context).nodes.find((item) => item.id === graphState.node);
    const viewport = document.querySelector(".graph-viewport");
    viewport.scrollTo({ left: Math.max(0, node.x * graphState.zoom - viewport.clientWidth / 2), top: Math.max(0, node.y * graphState.zoom - viewport.clientHeight / 2) });
  }
  return true;
}
