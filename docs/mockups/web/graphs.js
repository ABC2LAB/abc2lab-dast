"use strict";

// All graph data is generated from the selected synthetic run. Exploring a
// diagram never schedules a task, visits the target, or invokes a model.
const graphViews = {
  assets: { title: "자산 그래프", icon: "globe", description: "발견·등록된 엔드포인트를 도메인·서비스·경로별로 살펴보세요." },
  knowledge: { title: "지식 그래프 · KG", icon: "users", description: "사용자·페이지·API·자원 구조와 정책·판정 근거를 관점별로 확인하세요." },
  flow: { title: "진단 흐름", icon: "activity", description: "진단이 어떤 순서로 진행됐고 어디에서 제한됐는지 살펴보세요." },
};
const graphStatuses = {
  registered: { label: "등록 정보", color: "purple" },
  observed: { label: "관찰·처리 기록", color: "info" },
  limited: { label: "일부 확인", color: "warning" },
  inferred: { label: "추론 가설", color: "warning" },
  unknown: { label: "미확인", color: "neutral" },
  blocked: { label: "차단", color: "warning" },
  pending: { label: "미실행·대기", color: "neutral" },
  active: { label: "진행 중", color: "purple" },
};
const GRAPH_NODE_WIDTH = 224;
const GRAPH_NODE_HEIGHT = 112;
const graphNodeTypes = { target: ["대상", "globe"], service: ["웹 서비스", "server"], group: ["경로 그룹", "grid"], fold: ["접힌 묶음", "plus"], page: ["페이지", "file"], endpoint: ["엔드포인트", "scan"], resource: ["자원", "database"], account: ["계정", "users"], policy: ["정책", "shield"], evidence: ["근거", "file"], verdict: ["판정", "check"], stage: ["진단 단계", "activity"] };
const graphState = { knowledgeView: "structure", detailed: false, scope: "", node: null, edge: null, search: "", relation: "all", neighbors: false, assetLimits: {}, zoom: 1, flowStep: null };
let flowTimer = null;
let graphDrag = null;

function graphContext() {
  const run = taskRun();
  const mode = getRoute().name;
  const rows = coverageRows(run);
  const requestedCase = getRoute().runId;
  const row = requestedCase ? rows.find((item) => item.id === requestedCase && (mode === "flow" || item.item)) : rows.find((item) => item.item) || rows[0];
  return { run, mode, row, rows };
}

function graphNode(id, label, type, x, y, status, description, meta = "") {
  return { id, label, type, x, y, status, description, meta };
}

function graphEdge(id, from, to, label, status, description, labelOffset = 0) {
  return { id, from, to, label, status, description, labelOffset };
}

function rowGraphStatus(row) {
  return ({ complete: "observed", limited: "limited", unknown: "unknown", blocked: "blocked", not_run: "pending", waiting: "pending" })[row.status];
}

function graphLanes(titles, height) {
  return titles.map(([title, subtitle], index) => ({ x: index * 280 + 12, y: 20, width: 256, height: height - 36, title, subtitle }));
}

function knowledgeGraph(context) {
  const { run, row } = context;
  const item = row.item;
  const observed = rowGraphStatus(row);
  const ready = !["waiting", "not_run"].includes(row.status);
  const published = findingsForRun(run).some((entry) => entry.id === row.id);
  const missingPolicy = item?.value === "suspected";
  const allowed = item?.value === "allowed";
  const unverifiedIdentity = item?.retestOutcome === "unverified";
  const policyStatus = missingPolicy ? "unknown" : "registered";
  const nodes = [
    graphNode("owner", accountLabel(run.owner || "buyer-a"), "account", 140, 190, "registered", "등록된 소유자 계정의 별칭입니다. 프로필 등록과 현재 세션의 신원 검증은 별개입니다.", "소유자 역할 A"),
    graphNode("role", "등록 역할", "policy", 140, 610, "registered", "두 계정의 역할 프로필 예시입니다. 같은 역할이라는 사실만으로 객체 접근을 허용하지 않습니다.", "계정 프로필"),
    graphNode("evaluated", accountLabel(run.evaluated || "buyer-b"), "account", 140, 390, unverifiedIdentity ? "unknown" : "registered", "평가 계정 B입니다. 계정별 신원 근거와 현재 세션 유효성은 실행 시 별도로 검증합니다.", "평가 역할 B"),
    graphNode("operation", row.path, "endpoint", 420, 190, observed, row.reason, "등록 동작 · GET"),
    graphNode("policy", missingPolicy ? "기대 정책 미등록" : "기대 접근 정책", "policy", 420, 610, policyStatus, item?.policy || "정책 근거 확인 필요", missingPolicy ? "권한 추정 금지" : "신뢰된 등록 출처 예시"),
    graphNode("resource", row.title, "resource", 420, 390, "registered", "등록된 자원과 계정 연결을 사용하는 예시입니다. 조회 성공만으로 소유권을 만들지 않습니다.", "객체 값 비공개"),
    graphNode("evidence", allowed ? "신원·정책 근거" : "관찰·비교 근거", "evidence", 700, 290, ready ? unverifiedIdentity ? "unknown" : observed : "pending", allowed ? "유효한 정책에 따른 허용 판정 예시이며 비교 전송 성공을 주장하지 않습니다." : row.reason, "저장 요약 · 합성 자료"),
    graphNode("verdict", published ? verdicts[item.value].label : run.status === "stopped" ? "판정 미발행" : "판정 대기", "verdict", 980, 290, published ? item?.value === "undecidable" ? "unknown" : "observed" : "pending", published ? row.reason : "최종 검증 전에는 판정을 표시하지 않습니다.", "취약점 판정과 관계 상태 구분"),
    graphNode("hypothesis", "연관 자원 가설", "resource", 700, 610, "inferred", "관찰로 확인되지 않은 관계 제안 예시입니다. 실행 허가나 확정된 취약점으로 승격하지 않습니다.", "미검증 제안"),
  ];
  const edges = [
    graphEdge("owner-role", "owner", "role", "역할 등록", "registered", "계정 프로필에서 등록한 역할 연결입니다.", -45),
    graphEdge("evaluated-role", "evaluated", "role", "역할 등록", "registered", "공통 역할은 접근 허용의 충분한 근거가 아닙니다.", -45),
    graphEdge("owner-observation", "owner", "operation", allowed ? "동작 등록" : "기준 관찰 A", allowed ? "registered" : observed, "기준 계정과 동작의 연결입니다. 현재 작업의 관찰 상태를 함께 확인합니다."),
    graphEdge("cross-observation", "evaluated", "operation", allowed ? "평가 주체" : "교차 관찰 B", unverifiedIdentity ? "unknown" : observed, row.reason, -28),
    graphEdge("operation-resource", "operation", "resource", "대상 자원", "registered", "동작과 자원의 등록 연결 예시입니다."),
    graphEdge("policy-resource", "policy", "resource", "소유·접근 범위", policyStatus, "기대 정책의 자원·주체·동작 대응 관계입니다. 관찰에서 소유권을 추정하지 않습니다."),
    graphEdge("resource-evidence", "resource", "evidence", "근거 연결", ready ? observed : "pending", row.reason),
    graphEdge("policy-verdict", "policy", "verdict", "정책 대조", policyStatus, item?.policy || "정책 미확인"),
    graphEdge("evidence-verdict", "evidence", "verdict", "판정 근거", published ? observed : "pending", "확보한 근거와 미확인 조건을 판정에 연결합니다.", 48),
    graphEdge("resource-hypothesis", "resource", "hypothesis", "추가 관계 제안", "inferred", "후속 검토를 위한 가설이며 저장된 관찰 사실과 구분합니다.", 20),
  ];
  const optional = new Set(["role", "hypothesis"]);
  const displayedNodes = graphState.detailed ? nodes : nodes.filter((node) => !optional.has(node.id));
  const displayedIds = new Set(displayedNodes.map((node) => node.id));
  const displayedEdges = edges.filter((edge) => displayedIds.has(edge.from) && displayedIds.has(edge.to));
  const verdict = displayedNodes.find((node) => node.id === "verdict");
  if (published) verdict.verdictValue = item.value;
  return { nodes: displayedNodes, edges: displayedEdges, width: 1120, height: 700, lanes: graphLanes([["01 · 검사 계정", "누가 접근하나요?"], ["02 · 대상·정책", "무엇에, 어떤 권한으로?"], ["03 · 근거", "어떤 기록이 있나요?"], ["04 · 판정", "근거를 어떻게 판단했나요?"]], 700), note: "계정 → 대상·정책 → 근거 → 판정 순서로 살펴보세요. 관계의 존재와 취약점 판정은 구분합니다." };
}

function diagnosticGraph(context) {
  const { run, row } = context;
  const waiting = ["waiting", "not_run"].includes(row.status);
  const blocked = row.status === "blocked";
  const unknown = row.status === "unknown";
  const allowed = row.item?.value === "allowed";
  const identityMissing = row.item?.retestOutcome === "unverified";
  const published = findingsForRun(run).some((entry) => entry.id === row.id);
  const definitions = [
    ["register", "대상·계정 등록", "등록 범위·설정 확인", "registered"],
    ["discover", "동작 후보 확인", row.path, waiting ? "pending" : "observed"],
    ["baseline", "기준 관찰 A", allowed ? "비교 관찰 주장 없음" : "소유자 기준 근거", blocked || waiting || allowed || identityMissing ? "pending" : "observed"],
    ["policy", "교차 실행 정책", blocked ? "등록 보호 규칙으로 차단" : "실행 허가와 기대 정책 구분", blocked ? "blocked" : waiting ? "pending" : "registered"],
    ["execute", "교차 요청 B", unknown ? "전송 여부 불명" : allowed ? "실제 전송 주장 없음" : "전송 기록 예시", blocked || waiting || allowed || identityMissing ? "pending" : unknown ? "unknown" : "observed"],
    ["evidence", "근거 저장·비교", row.reason, unknown || identityMissing ? "unknown" : blocked || waiting ? "pending" : "observed"],
    ["judge", "근거 판정", published ? verdicts[row.item.value].label : run.status === "stopped" ? "중단 · 판정 미발행" : "판정 대기", !published ? "pending" : unknown || identityMissing ? "unknown" : "observed"],
    ["report", "결과·제한 기록", "미완료·차단·불확실성 보존", run.status === "running" ? "pending" : "observed"],
  ];
  const activeRow = context.rows.find((entry) => entry.status === "waiting");
  const liveIndex = run.status === "running" && row.id === activeRow?.id && !blocked && !unknown && !identityMissing ? Math.min(5, Math.floor(run.progress * 8 / 100)) : null;
  const nodes = definitions.map(([id, label, description, status], index) => {
    if (liveIndex !== null && index >= liveIndex) status = index === liveIndex ? "active" : "pending";
    const future = graphState.flowStep !== null && index > graphState.flowStep;
    const node = graphNode(id, label, "stage", 140 + (index % 4) * 280, index < 4 ? 190 : 490, future ? "pending" : status, future ? "재생 위치가 아직 이 단계에 도달하지 않았습니다. 저장된 자료 자체는 변경하지 않습니다." : description, `${String(index + 1).padStart(2, "0")} · ${future ? "재생 대기" : graphStatuses[status].label}`);
    node.step = index;
    return node;
  });
  const hasLimit = blocked || unknown || waiting || row.status === "limited" || identityMissing;
  if (hasLimit) nodes.push(graphNode("limit", blocked ? "정책 차단 기록" : unknown ? "전송 불명 기록" : "제한·미확인 기록", "stage", 700, 760, blocked ? "blocked" : unknown ? "unknown" : "limited", row.reason, "별도 사유 보존"));
  const edges = definitions.slice(1).map((entry, index) => graphEdge(`flow-${index}`, definitions[index][0], entry[0], ["후보", "기준 확인", "실행 준비", "허가 재검사", "근거 인계", "검증", "집계"][index], nodes[index + 1].status, "작업과 근거 처리의 인과 순서 예시입니다. 화면 재생이 대상 요청을 발생시키지 않습니다."));
  if (hasLimit) edges.push(graphEdge("limit-branch", blocked ? "policy" : "execute", "limit", blocked ? "차단" : unknown ? "전송 불명" : "제한 기록", blocked ? "blocked" : unknown ? "unknown" : "limited", row.reason, 60));
  return { nodes, edges, width: 1120, height: hasLimit ? 850 : 650, flowRows: true, note: "번호 1–8 순서의 저장 기록입니다. 대상 서비스의 실제 업무 흐름이나 모델 내부 사고 과정을 나타내지 않습니다." };
}

function buildGraph(context) {
  return context.mode === "assets" ? assetGraph(context) : context.mode === "knowledge" ? graphState.knowledgeView === "structure" ? surfaceGraph(context) : knowledgeGraph(context) : diagnosticGraph(context);
}

function filteredGraph(model) {
  if (model.assetTree) return model;
  let nodes = model.nodes;
  let edges = model.edges;
  if (graphState.relation !== "all") {
    edges = edges.filter((edge) => edge.status === graphState.relation);
    const ids = new Set(edges.flatMap((edge) => [edge.from, edge.to]));
    nodes = nodes.filter((node) => ids.has(node.id));
  }
  if (graphState.search.trim()) {
    const query = graphState.search.toLowerCase().trim();
    const matches = new Set(nodes.filter((node) => `${node.label} ${node.meta} ${node.method || ""}`.toLowerCase().includes(query)).map((node) => node.id));
    edges = edges.filter((edge) => matches.has(edge.from) || matches.has(edge.to));
    const connected = new Set([...matches, ...edges.flatMap((edge) => [edge.from, edge.to])]);
    nodes = nodes.filter((node) => connected.has(node.id));
  }
  if (graphState.neighbors && graphState.node) {
    edges = edges.filter((edge) => edge.from === graphState.node || edge.to === graphState.node);
    const connected = new Set([graphState.node, ...edges.flatMap((edge) => [edge.from, edge.to])]);
    nodes = nodes.filter((node) => connected.has(node.id));
  }
  const ids = new Set(nodes.map((node) => node.id));
  edges = edges.filter((edge) => ids.has(edge.from) && ids.has(edge.to));
  return { ...model, nodes, edges };
}

function edgeGeometry(edge, model) {
  if (model.surfaceTree) return surfaceEdgeGeometry(edge, model);
  const from = model.nodes.find((node) => node.id === edge.from);
  const to = model.nodes.find((node) => node.id === edge.to);
  const halfWidth = GRAPH_NODE_WIDTH / 2, halfHeight = GRAPH_NODE_HEIGHT / 2;
  if (edge.id === "limit-branch") {
    const blocked = from.id === "policy";
    return { path: blocked ? `M${from.x+halfWidth},${from.y} H1106 V660 H${to.x} V${to.y-halfHeight}` : `M${from.x},${from.y+halfHeight} V660 H${to.x} V${to.y-halfHeight}`, x: blocked ? 980 : 420, y: 660 };
  }
  if (model.flowRows && edge.id === "flow-3") return { path: `M${from.x+halfWidth},${from.y} H1106 V336 H14 V${to.y} H${to.x-halfWidth}`, x: 560, y: 336 };
  if (edge.id === "policy-verdict") return { path: `M${from.x},${from.y+halfHeight} V684 H${to.x} V${to.y+halfHeight}`, x: 700, y: 684 };
  if (edge.id === "owner-role") return { path: `M${from.x-halfWidth},${from.y} H18 V${to.y} H${to.x-halfWidth}`, x: 140, y: 500 };
  const vertical = from.x === to.x;
  const direction = Math.sign(vertical ? to.y - from.y : to.x - from.x);
  const x1 = from.x + (vertical ? 0 : direction * halfWidth), y1 = from.y + (vertical ? direction * halfHeight : 0);
  const x2 = to.x - (vertical ? 0 : direction * halfWidth), y2 = to.y - (vertical ? direction * halfHeight : 0);
  const middle = (x1+x2)/2;
  return { path: vertical ? `M${x1},${y1} V${y2}` : `M${x1},${y1} H${middle} V${y2} H${x2}`, x: middle, y: (y1+y2)/2 };
}

let graphMeasureContext = null;
function graphTextWidth(text, size = 16, weight = 750) {
  graphMeasureContext ||= document.createElement("canvas").getContext("2d");
  graphMeasureContext.font = `${weight} ${size}px ${getComputedStyle(document.documentElement).getPropertyValue("--font")}`;
  return graphMeasureContext.measureText(text).width;
}

function graphLabelLines(text, available = GRAPH_NODE_WIDTH - 32, fontSize = 16, fontWeight = 750) {
  const lines = [];
  let line = "";
  const tokens = text.startsWith("/") ? text.match(/\/[^/]*|[^/]+/g) : text.split(/(?<=\s)/);
  for (const token of tokens) {
    if (line && graphTextWidth(line + token, fontSize, fontWeight) > available) {
      lines.push(line.trim()); line = "";
    }
    for (const character of token) {
      if (line && graphTextWidth(line + character, fontSize, fontWeight) > available) {
        lines.push(line.trim()); line = "";
      }
      line += character;
    }
  }
  if (line.trim()) lines.push(line.trim());
  if (lines.length <= 2) return lines;
  let last = lines.slice(1).join("");
  while (graphTextWidth(last + "…", fontSize, fontWeight) > available) last = last.slice(0,-1);
  return [lines[0], last + "…"];
}

function edgeLabelPosition(edge, line, model, placed) {
  const width = Math.max(58, graphTextWidth(edge.label, 12, 650) + 18);
  const offsets = [[0,0], [0,-24], [0,24], [0,-78], [0,78], [-60,0], [60,0]];
  for (const [dx,dy] of offsets) {
    const box = { x: line.x + dx - width/2, y: line.y + dy - 12, width, height: 24 };
    const overlaps = (other) => box.x < other.x + other.width && box.x + width > other.x && box.y < other.y + other.height && box.y + box.height > other.y;
    if (box.x < 4 || box.x + width > model.width - 4 || box.y < 82 || box.y + 24 > model.height - 4) continue;
    if (model.nodes.some((node) => overlaps({ x:node.x-GRAPH_NODE_WIDTH/2-5, y:node.y-GRAPH_NODE_HEIGHT/2-5, width:GRAPH_NODE_WIDTH+10, height:GRAPH_NODE_HEIGHT+10 })) || placed.some(overlaps)) continue;
    placed.push(box);
    return { ...box, cx: line.x + dx, cy: line.y + dy };
  }
  return null;
}

function graphBackground(model) {
  if (model.surfaceTree) return surfaceGraphBackground(model);
  if (model.lanes) return model.lanes.map((lane) => `<g class="graph-lane"><rect class="lane-bg" x="${lane.x}" y="80" width="${lane.width}" height="${lane.height-64}" rx="14"/><text class="lane-title" x="${lane.x+16}" y="34">${escapeHtml(lane.title)}</text><text class="lane-subtitle" x="${lane.x+16}" y="56">${escapeHtml(lane.subtitle)}</text></g>`).join("");
  return [[80, "01–04 · 실행 준비", "대상·계정 → 후보 → 기준 관찰 → 실행 정책"], [380, "05–08 · 실행과 결과 확인", "교차 요청 → 근거 → 판정 → 결과 기록"]].map(([y,title,subtitle]) => `<g class="graph-lane"><rect class="lane-bg" x="12" y="${y}" width="1096" height="220" rx="14"/><text class="lane-title" x="28" y="${y+24}">${title}</text><text class="lane-subtitle" x="540" y="${y+24}">${subtitle}</text></g>`).join("");
}

function graphSvg(model) {
  const placed = [];
  const selectedEdge = model.edges.find((edge) => edge.id === graphState.edge);
  const selectedNodes = new Set(selectedEdge ? [selectedEdge.from, selectedEdge.to] : graphState.node ? [graphState.node] : []);
  return `<svg class="graph-canvas" style="width:${model.width * graphState.zoom}px;height:${model.height * graphState.zoom}px" viewBox="0 0 ${model.width} ${model.height}" role="group" aria-label="선택 가능한 ${graphViews[getRoute().name].title} 노드와 관계">
    <title>가상 진단 자료의 부분 그래프. 유형별 영역과 단계 번호 순서로 읽으세요.</title><defs><marker id="graph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="context-stroke"/></marker></defs>
    ${graphBackground(model)}
    ${model.edges.map((edge) => {
      const line = edgeGeometry(edge, model);
      const selected = graphState.edge ? graphState.edge === edge.id : [edge.from, edge.to].includes(graphState.node);
      const label = selected || graphState.detailed ? edgeLabelPosition(edge, line, model, placed) : null;
      return `<g class="graph-edge ${edge.status} ${selected ? "highlight" : selectedNodes.size ? "is-muted" : ""}" role="button" tabindex="0" aria-label="관계: ${escapeHtml(edge.label)} · ${graphStatuses[edge.status].label}" aria-pressed="${graphState.edge === edge.id}" data-action="graph-edge" data-value="${edge.id}" aria-controls="graph-detail"><title>${escapeHtml(edge.label)} · ${graphStatuses[edge.status].label}</title><path class="edge-hit" d="${line.path}" fill="none" stroke="transparent" stroke-width="20"/><path class="edge-line" d="${line.path}"/>${label ? `<rect class="edge-label" x="${label.x}" y="${label.y}" width="${label.width}" height="24" rx="6"/><text class="edge-label" x="${label.cx}" y="${label.cy+4}" text-anchor="middle">${escapeHtml(edge.label)}</text>` : ""}</g>`;
    }).join("")}
    ${model.nodes.map((node) => {
      if (model.surfaceTree) return surfaceNodeSvg(node);
      const [kind, symbol] = graphNodeTypes[node.type];
      const statusLabel = node.statusLabel || graphStatuses[node.status].label;
      const lines = graphLabelLines(node.label);
      return `<g class="graph-node type-${node.type} status-${node.status} ${node.verdictValue ? `outcome-${node.verdictValue}` : ""} ${graphState.node === node.id ? "selected" : ""}" transform="translate(${node.x-GRAPH_NODE_WIDTH/2},${node.y-GRAPH_NODE_HEIGHT/2})" role="button" tabindex="0" aria-label="${escapeHtml(node.label)} · ${kind} · ${statusLabel}" aria-pressed="${graphState.node === node.id}" data-action="graph-node" data-value="${node.id}" aria-controls="graph-detail"><title>${escapeHtml(node.label)} · ${escapeHtml(node.meta)} · ${statusLabel}</title><rect class="node-surface" width="${GRAPH_NODE_WIDTH}" height="${GRAPH_NODE_HEIGHT}" rx="12"/><rect class="node-accent" width="4" height="${GRAPH_NODE_HEIGHT-24}" x="0" y="12" rx="2"/><rect class="node-icon-bg" x="12" y="10" width="26" height="26" rx="7"/><svg class="node-symbol" x="17" y="15" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[symbol]}</svg><text class="node-type" x="46" y="27">${escapeHtml(node.step === undefined ? node.method ? `${node.method} · ${kind}` : kind : `${String(node.step+1).padStart(2,"0")} · ${kind}`)}</text>${lines.map((line,index) => `<text class="label" x="16" y="${54+index*19}">${escapeHtml(line)}</text>`).join("")}<circle class="status-dot" cx="18" cy="96" r="3.5"/><text class="node-status" x="29" y="100">${statusLabel}</text></g>`;
    }).join("")}
  </svg>`;
}

function graphDetail(context, model) {
  const edge = model.edges.find((item) => item.id === graphState.edge);
  const node = model.nodes.find((item) => item.id === graphState.node);
  const selected = edge || node;
  if (context.mode === "assets" && node) { const detail = assetDetail(context, model, node); if (detail) return detail; }
  if (!selected) return `<aside class="card graph-detail graph-inspector-empty" id="graph-detail">${icon("eye")}<div><h2>궁금한 노드나 연결선을 선택하세요</h2><p>전체 이름·연결 의미·출처를 확인할 수 있습니다. 선택한 연결이 강조되고, 나머지 선은 옅어집니다.</p></div></aside>`;
  const adjacent = node ? model.edges.filter((item) => item.from === node.id || item.to === node.id) : [];
  const referenceCase = selected.caseId || (model.surfaceTree ? null : context.row.id);
  const caseRow = context.rows.find((row) => row.id === referenceCase);
  const canOpen = caseRow?.item && findingsForRun(context.run).some((item) => item.id === referenceCase);
  return `<aside class="card graph-detail" id="graph-detail" aria-label="그래프 선택 상세"><div class="graph-detail-heading"><div><p class="graph-kind">${edge ? "선택한 관계" : `선택한 ${graphNodeTypes[node.type][0]}`}</p><h2>${escapeHtml(selected.label)}</h2></div>${badge(graphStatuses[selected.status].label, graphStatuses[selected.status].color)}</div><div class="graph-detail-content"><div><p>${escapeHtml(selected.description)}</p><div class="graph-related-list"><h3>${edge ? "연결된 노드" : "주변 연결"}</h3>${edge ? [edge.from, edge.to].map((id) => `<button type="button" data-action="graph-node" data-value="${id}">${escapeHtml(model.nodes.find((item) => item.id === id)?.label)}${icon("chevron")}</button>`).join("") : adjacent.map((item) => `<button type="button" data-action="graph-edge" data-value="${item.id}">${escapeHtml(item.label)}${icon("chevron")}</button>`).join("")}${node ? button(graphState.neighbors ? "전체 표시로 돌아가기" : "주변 연결만 보기", "graph-neighbors", "secondary small", "eye") : ""}${canOpen && context.mode !== "assets" ? `<a href="#finding/${referenceCase}/${context.run.id}">사례 판정 근거 보기 ${icon("arrow")}</a>` : ""}</div></div><dl class="graph-detail-list"><dt>작업</dt><dd>${escapeHtml(context.run.target.name)} · ${context.run.id}</dd><dt>표시 출처</dt><dd>${selected.status === "inferred" ? "미검증 관계 제안 예시" : selected.status === "registered" ? "등록 정보 예시" : "합성 작업·관찰 요약"}</dd><dt>참조</dt><dd>${context.run.id} / ${escapeHtml(selected.id)}</dd>${edge ? `<dt>연결 방향</dt><dd>${escapeHtml(model.nodes.find((item) => item.id === edge.from)?.label)} → ${escapeHtml(model.nodes.find((item) => item.id === edge.to)?.label)}</dd>` : ""}</dl></div></aside>`;
}

function graphRegion(context) {
  const model = filteredGraph(buildGraph(context));
  if (!model.nodes.some((node) => node.id === graphState.node)) graphState.node = null;
  if (!model.edges.some((edge) => edge.id === graphState.edge)) graphState.edge = null;
  const zoom = `${Math.round(graphState.zoom * 100)}%`;
  return `<div class="graph-layout"><section class="card graph-card ${context.mode === "assets" ? "asset-graph-card" : model.surfaceTree ? "surface-graph-card" : ""}"><div class="graph-card-header"><div><h2 class="section-title">${graphViews[context.mode].title}</h2><span class="small-text muted" id="graph-count">노드 ${model.nodes.length} · 관계 ${model.edges.length}${context.mode === "assets" ? ` · ${displayedCaseCount(context, model)}/${context.rows.length}개 엔드포인트` : model.surfaceTree ? ` · ${model.nodes.filter((node) => node.type === "endpoint").length}/${model.totalPaths}개 경로` : graphState.detailed ? " · 세부 관계" : " · 핵심 관계"}</span></div><div class="graph-tools">${context.mode === "assets" ? `${button("전체 펼치기", "asset-expand-all", "secondary small", "plus")}${button("기본 보기", "asset-default", "ghost small")}` : ""}${button("−", "graph-zoom-out", "ghost small", "", 'aria-label="그래프 축소"')}<span class="small-text muted" id="graph-zoom-label">${zoom}</span>${button("+", "graph-zoom-in", "ghost small", "", 'aria-label="그래프 확대"')}${button("맞춤", "graph-fit", "secondary small")}${button("100%", "graph-readable", "secondary small", "", 'aria-label="읽기 크기 100%"')}</div></div><div class="graph-viewport" style="--graph-view-height:${Math.min(model.height+8,760)}px" tabindex="0" aria-label="그래프 영역. 배경 드래그 또는 스크롤로 이동할 수 있습니다.">${model.nodes.length ? graphSvg(model) : `<div class="graph-empty">${icon("search")}<h3>표시할 연결이 없습니다</h3><p>검색어와 검사·관계 상태를 확인하세요.</p>${button("그래프 필터 초기화", "graph-reset", "secondary")}</div>`}</div><div class="table-caption graph-caption"><span>${context.mode === "assets" ? "경로 묶음을 선택해 펼치거나 엔드포인트의 메서드·변수·상태를 확인하세요." : "노드·선을 선택하면 연결과 전체 이름을 확인할 수 있습니다."}</span><span>배경 드래그·스크롤로 이동</span></div></section>${graphDetail(context, model)}</div>`;
}

function displayedCaseCount(context, model) {
  return model.nodes.filter((node) => node.endpoint).length;
}

function graphOverview(context, model) {
  if (context.mode === "assets") return assetOverview(context, model);
  if (model.surfaceTree) return surfaceGraphOverview(context, model);
  const { row, run, mode } = context;
  const published = findingsForRun(run).find((item) => item.id === row.id);
  const reading = mode === "knowledge" ? ["검사 계정", "대상·정책", "근거", "판정"] : ["01–04 실행 준비", "05–08 실행·결과 확인"];
  const summary = `<strong>${escapeHtml(row.title)} · ${row.id}</strong> ${published ? verdictBadge(published.value) : badge(mode === "flow" && row.status === "blocked" ? "정책 차단" : run.status === "stopped" ? "중단 · 판정 미발행" : "판정 확정 전", "neutral")}<br>${escapeHtml(row.reason)}`;
  return `<section class="graph-overview" id="graph-overview" aria-label="그래프 읽기 안내"><div class="graph-reading-order">${reading.map((label) => `<span>${label}</span>`).join("")}</div><p class="graph-case-summary">${summary}</p></section>`;
}

function graphDetailLabel(context) {
  if (context.mode === "knowledge") {
    if (graphState.knowledgeView === "structure") return graphState.detailed ? "핵심 경로만" : "전체 경로 표시";
    return graphState.detailed ? "핵심 관계만" : "세부 관계 표시";
  }
  return graphState.detailed ? "관계 이름 숨기기" : "관계 이름 표시";
}

function graphScreen() {
  const context = graphContext();
  if (!context.row) return `${taskSectionHeading("연결된 사례를 찾을 수 없습니다", "선택한 작업에 속하는 사례·작업만 그래프로 표시합니다.")}<a class="button secondary" href="#assets/${context.run.id}">이 작업의 자산 그래프 보기</a>`;
  const scope = `${context.mode}/${context.run.id}/${context.row.id}/${getRoute().runId || "all"}`;
  if (graphState.scope !== scope) {
    clearInterval(flowTimer);
    flowTimer = null;
    Object.assign(graphState, { scope, knowledgeView: getRoute().runId ? "evidence" : "structure", node: null, edge: null, search: "", relation: "all", neighbors: false, assetLimits: {}, detailed: false, zoom: 1, flowStep: null });
  }
  const viewInfo = graphViews[context.mode];
  const model = buildGraph(context);
  const stateLabel = context.mode === "assets" ? "검사 상태" : "관계 상태";
  const stateOptions = context.mode === "assets" ? [["all", "전체 검사 상태"], ...Object.entries(coverageStates).map(([key, info]) => [key, info.label])] : [["all", "전체 관계"], ["registered", "등록 정보"], ["observed", "관찰·처리 기록"], ["limited", "일부 확인"], ["inferred", "추론 가설"], ["unknown", "미확인"], ["blocked", "차단"]];
  const legend = context.mode === "assets" ? '<span>실선 · URL 구조</span><span class="legend-limited">주황 · 일부 확인/차단</span><span class="legend-unknown">점선 테두리 · 전송 불명/접힌 묶음</span><span>미실행·대기와 판정은 별도 표시</span>' : '<span>실선 · 등록/관찰 기록</span><span class="legend-limited">주황 · 일부 확인/차단</span><span class="legend-inferred">점선 · 미검증 가설</span><span class="legend-unknown">짧은 점선 · 미확인</span><span>옅은 선 · 선택 범위 밖</span>';
  return `${taskSectionHeading(viewInfo.title, viewInfo.description)}
    <nav class="graph-tabs" aria-label="그래프 관점">${Object.entries(graphViews).map(([mode, info]) => `<a href="#${mode}/${context.run.id}${mode === "assets" || mode === "knowledge" ? "" : `/${context.row.id}`}" ${mode === context.mode ? 'aria-current="page"' : ""}>${icon(info.icon)}${info.title}</a>`).join("")}</nav>
    ${context.mode === "knowledge" ? `<div class="knowledge-views" role="group" aria-label="KG 보기 전환">${[["structure", "웹 구조"], ["evidence", "판정 근거"]].map(([value,label]) => `<button type="button" class="button secondary small" data-action="knowledge-view" data-value="${value}" aria-pressed="${graphState.knowledgeView === value}">${label}</button>`).join("")}</div>` : ""}
    ${graphOverview(context, filteredGraph(model))}
    <div class="graph-controls"><label class="search-field compact">${icon("search")}<input id="graph-search" aria-label="그래프 검색" placeholder="노드 이름·경로 검색" value="${escapeHtml(graphState.search)}"></label><label for="graph-relation">${stateLabel}<select id="graph-relation" aria-label="${stateLabel}">${stateOptions.map(([value, label]) => `<option value="${value}" ${graphState.relation === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>${context.mode === "assets" || context.mode === "knowledge" && graphState.knowledgeView === "structure" ? "" : `<label for="graph-case">사례·작업<select id="graph-case" aria-label="사례·작업">${context.rows.filter((row) => context.mode === "flow" || row.item).map((row) => `<option value="${row.id}" ${row.id === context.row.id ? "selected" : ""}>${row.id} · ${escapeHtml(row.title)}</option>`).join("")}</select></label>`}${button(graphDetailLabel(context), "graph-details", "secondary small graph-toggle", "eye", `id="graph-detail-toggle" aria-pressed="${graphState.detailed}"`)}${button("초기화", "graph-reset", "ghost small")}</div>
    ${context.mode === "flow" ? `<div class="graph-replay" aria-label="진단 흐름 재생">${button(flowTimer ? "재생 일시정지" : "처음부터 재생", "flow-play", "secondary", "activity", 'id="flow-play"')}${button("이전", "flow-previous", "ghost small", "left")}${button("다음", "flow-next", "ghost small", "arrow")}<label for="flow-step">단계 위치<input type="range" aria-label="단계 위치" id="flow-step" min="0" max="7" value="${graphState.flowStep ?? 7}"></label><span id="flow-position" class="small-text muted" aria-live="polite">${graphState.flowStep === null ? "저장된 흐름 전체 · 대상 재실행 없음" : `${graphState.flowStep+1} / 8 단계 · 저장 기록 재생`}</span></div>` : ""}
    <div id="graph-region">${graphRegion(context)}</div><div class="graph-legend">${legend}</div><p class="small-text muted graph-caption">${escapeHtml(model.note)} 모든 자료는 가상이며, 원문·인증 값은 표시하지 않습니다.</p>`;
}

function repaintGraph(focusNode = false) {
  if (!graphViews[getRoute().name]) return;
  const region = document.querySelector("#graph-region");
  if (!region || !graphContext().row) return;
  const viewport = document.querySelector(".graph-viewport");
  const focused = document.activeElement?.closest(".graph-node, .graph-edge");
  const focusTarget = region.contains(focused) ? { action: focused.dataset.action, value: focused.dataset.value } : null;
  const scroll = [viewport?.scrollLeft || 0, viewport?.scrollTop || 0];
  region.innerHTML = graphRegion(graphContext());
  const overview = document.querySelector("#graph-overview");
  if (overview) overview.outerHTML = graphOverview(graphContext(), filteredGraph(buildGraph(graphContext())));
  const next = document.querySelector(".graph-viewport");
  if (next) { next.scrollLeft = scroll[0]; next.scrollTop = scroll[1]; }
  const restoreFocus = focusNode && graphState.node ? { action: "graph-node", value: graphState.node } : focusTarget;
  if (restoreFocus) {
    const element = document.querySelector(`[data-action="${restoreFocus.action}"][data-value="${restoreFocus.value}"]`) || next;
    element?.focus({ preventScroll: true });
  }
}

function updateFlowPosition() {
  const slider = document.querySelector("#flow-step");
  if (!slider) return;
  slider.value = graphState.flowStep ?? 7;
  document.querySelector("#flow-position").textContent = graphState.flowStep === null ? "저장된 흐름 전체 · 대상 재실행 없음" : `${graphState.flowStep + 1} / 8 단계 · 저장 기록 재생`;
  document.querySelector("#flow-play").innerHTML = `${icon("activity")}${flowTimer ? "재생 일시정지" : "처음부터 재생"}`;
}

document.addEventListener("click", (event) => {
  const element = event.target.closest("[data-action]");
  if (!element || element.disabled || !graphViews[getRoute().name]) return;
  const action = element.dataset.action;
  if (handleAssetAction(action, element.dataset.value)) return;
  if (action === "knowledge-view") {
    Object.assign(graphState, { knowledgeView: element.dataset.value, node: null, edge: null, search: "", relation: "all", detailed: false, neighbors: false, zoom: 1 });
    render(false);
    document.querySelector(`[data-action="knowledge-view"][data-value="${graphState.knowledgeView}"]`)?.focus({ preventScroll: true });
    return;
  }
  if (action === "graph-details") {
    graphState.detailed = !graphState.detailed;
    if (!graphState.detailed && graphState.relation === "inferred") { graphState.relation = "all"; document.querySelector("#graph-relation").value = "all"; }
    repaintGraph();
    const toggle = document.querySelector("#graph-detail-toggle");
    toggle.setAttribute("aria-pressed", String(graphState.detailed));
    toggle.innerHTML = `${icon("eye")}${graphDetailLabel(graphContext())}`;
  }
  else if (action === "graph-node") { graphState.node = element.dataset.value; graphState.edge = null; repaintGraph(true); }
  else if (action === "graph-edge") { graphState.edge = element.dataset.value; graphState.node = null; repaintGraph(); document.querySelector(`.graph-edge[data-value="${graphState.edge}"]`)?.focus({ preventScroll: true }); }
  else if (action === "graph-neighbors") { graphState.neighbors = !graphState.neighbors; graphState.edge = null; repaintGraph(); }
  else if (["graph-zoom-in", "graph-zoom-out", "graph-fit", "graph-readable"].includes(action)) {
    const model = buildGraph(graphContext());
    graphState.zoom = action === "graph-readable" ? 1 : Math.max(.25, Math.min(1.6, action === "graph-fit" ? Math.min(document.querySelector(".graph-viewport").clientWidth / model.width, document.querySelector(".graph-viewport").clientHeight / model.height) : graphState.zoom + (action === "graph-zoom-in" ? .1 : -.1)));
    if (["graph-fit", "graph-readable"].includes(action)) { const viewport = document.querySelector(".graph-viewport"); viewport.scrollTo(0,0); }
    const canvas = document.querySelector(".graph-canvas");
    if (canvas) { canvas.style.width = `${model.width * graphState.zoom}px`; canvas.style.height = `${model.height * graphState.zoom}px`; }
    document.querySelector("#graph-zoom-label").textContent = `${Math.round(graphState.zoom * 100)}%`;
  } else if (action === "graph-reset") {
    Object.assign(graphState, { search: "", relation: "all", neighbors: false, node: null, edge: null });
    document.querySelector("#graph-search").value = "";
    document.querySelector("#graph-relation").value = "all";
    repaintGraph();
  } else if (["flow-play", "flow-previous", "flow-next"].includes(action)) {
    const wasPlaying = Boolean(flowTimer);
    clearInterval(flowTimer); flowTimer = null;
    if (action === "flow-play" && !wasPlaying) {
      graphState.flowStep = 0;
      flowTimer = setInterval(() => {
        if (getRoute().name !== "flow") { clearInterval(flowTimer); flowTimer = null; return; }
        graphState.flowStep = Math.min(7, graphState.flowStep + 1);
        if (graphState.flowStep === 7) { clearInterval(flowTimer); flowTimer = null; }
        repaintGraph(); updateFlowPosition();
      }, 850);
    } else if (action !== "flow-play") graphState.flowStep = Math.max(0, Math.min(7, (graphState.flowStep ?? (action === "flow-next" ? -1 : 8)) + (action === "flow-next" ? 1 : -1)));
    repaintGraph(); updateFlowPosition();
  }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "graph-search") { graphState.search = event.target.value; repaintGraph(); }
  else if (event.target.id === "flow-step") { clearInterval(flowTimer); flowTimer = null; graphState.flowStep = Number(event.target.value); repaintGraph(); updateFlowPosition(); }
});
document.addEventListener("change", (event) => {
  if (event.target.id === "graph-case") navigate(`${getRoute().name}/${taskRun().id}/${event.target.value}`);
  else if (event.target.id === "graph-relation") {
    graphState.relation = event.target.value; graphState.neighbors = false;
    if (graphState.relation === "inferred" && !graphState.detailed) document.querySelector("#graph-detail-toggle").click();
    else repaintGraph();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.target.matches(".graph-node, .graph-edge") && ["Enter", " "].includes(event.key)) { event.preventDefault(); event.target.dispatchEvent(new MouseEvent("click", { bubbles: true })); }
});
document.addEventListener("pointerdown", (event) => {
  const viewport = event.target.closest(".graph-viewport");
  if (!viewport || event.pointerType === "touch" || event.button !== 0 || event.target.closest("[data-action]")) return;
  graphDrag = { viewport, x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop };
  viewport.setPointerCapture(event.pointerId); viewport.classList.add("dragging");
});
document.addEventListener("pointermove", (event) => {
  if (!graphDrag) return;
  graphDrag.viewport.scrollLeft = graphDrag.left - event.clientX + graphDrag.x;
  graphDrag.viewport.scrollTop = graphDrag.top - event.clientY + graphDrag.y;
});
function finishGraphDrag() { graphDrag?.viewport.classList.remove("dragging"); graphDrag = null; }
document.addEventListener("pointerup", finishGraphDrag);
document.addEventListener("pointercancel", finishGraphDrag);
window.addEventListener("hashchange", () => { clearInterval(flowTimer); flowTimer = null; finishGraphDrag(); });
