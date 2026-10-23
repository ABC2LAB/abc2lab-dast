"use strict";

// Presentation-only helpers for the finding detail screen. They render
// placeholders and never send, replay, or copy a request.
function findingCategory(item) {
  if (item?.retestOutcome) return "접근 권한 재검토";
  if (["confirmed", "suspected", "undecidable"].includes(item?.value)) return "BOLA / IDOR";
  if (item?.value === "allowed") return "등록 접근 정책";
  return "접근 권한 재검토";
}

function findingRecordedDate(run) {
  const value = String(run?.date || "").trim().split(/\s+/, 1)[0];
  return /^\d{4}\.\d{2}\.\d{2}$/.test(value) ? value : "기록일 미상";
}

function findingContextValue(context, key, fallback) {
  return escapeHtml(context?.[key] || fallback);
}

function findingReproductionSummary(item, context = {}) {
  const owner = findingContextValue(context, "owner", "소유자 A");
  const evaluated = findingContextValue(context, "evaluated", "평가 계정 B");
  let steps;
  let note = "실제 명령을 실행하지 않는 화면 검토용 절차입니다.";

  if (item?.retestOutcome === "not-reproduced") {
    steps = [
      "이전 판정과 저장된 근거를 그대로 보존합니다.",
      "이번 조건에서 기존 비교 경로가 재현되지 않았음을 기록합니다.",
      "이번 미재현을 수정 완료나 전체 취약점 부재로 단정하지 않습니다.",
    ];
  } else if (item?.retestOutcome === "unverified") {
    steps = [
      "이전 판정과 저장된 근거를 그대로 보존합니다.",
      "현재 평가 계정의 신원 근거를 확인하지 못한 상태를 기록합니다.",
      "신원 미확인을 수정 완료나 안전한 결과로 단정하지 않습니다.",
    ];
  } else if (item?.value === "confirmed") {
    steps = [
      `등록 정책과 서로 다른 주체(${owner} / ${evaluated})를 확인합니다.`,
      "소유자 A로 같은 자원의 기준 조회를 확인합니다.",
      "평가 계정 B로 같은 자원을 비교한 기록을 확인합니다.",
      "데이터 일치·반사·공통 템플릿·접근 정책을 대조합니다.",
    ];
  } else if (item?.value === "suspected") {
    steps = [
      `서로 다른 A/B 주체(${owner} / ${evaluated})와 정책 등록 여부를 확인합니다.`,
      "소유자 A로 기준 조회, 평가 계정 B로 같은 자원 비교 절차를 검토합니다.",
      "데이터 일치와 반사·공통 템플릿 여부를 대조합니다.",
      "기대 접근 정책을 보완 확인하기 전에는 확정 판정이나 실행 가능한 PoC로 취급하지 않습니다.",
    ];
    note = "정책 근거가 보완되기 전까지 실행 가능한 PoC로 오인하지 않습니다. 실제 명령은 실행하지 않습니다.";
  } else if (item?.value === "allowed") {
    steps = [
      `평가 계정 ${evaluated}의 신원과 등록된 정책 출처를 확인합니다.`,
      "해당 주체·자원·동작 범위와 공유·위임 허용 조건을 대조합니다.",
      "정책상 허용은 실제 비교 전송 성공이나 전체 안전을 뜻하지 않음을 기록합니다.",
    ];
    note = "정책상 허용 사례이며 실제 전송이나 재현 명령을 주장하지 않습니다.";
  } else {
    steps = [
      "교차 요청의 전송 상태와 저장된 응답 근거가 있는지 확인합니다.",
      "전송 불명·응답 미확보를 취약점 없음으로 바꾸지 않습니다.",
      "불확실한 상태에서는 자동 재전송하지 않고 확인 불가 사유를 보존합니다.",
    ];
  }

  return `<section class="card finding-steps" aria-label="재현·검토 단계"><div class="card-header"><h2 class="section-title">재현·검토 단계</h2><span class="badge neutral">실행 안 함</span></div><div class="card-body"><ol>${steps.map((step) => `<li>${step}</li>`).join("")}</ol><p class="small-text muted">${note}</p></div></section>`;
}

function findingSyntheticHost(context) {
  try {
    const host = new URL(context?.target?.url || "https://target.test").hostname;
    return host.endsWith(".test") ? host : "target.test";
  } catch {
    return "target.test";
  }
}

function findingRequestPath(item) {
  return String(item?.path || "/registered/resource/{resource_id}").replace(/\{[^}]+\}/g, "<RESOURCE_ID>");
}

function findingHttpExamples(item, context = {}) {
  const host = findingSyntheticHost(context);
  const request = `GET ${findingRequestPath(item)} HTTP/1.1\nHost: ${host}\n\n# 인증 헤더와 쿠키는 표시하지 않습니다.`;
  let response;
  let responseNote;

  if (item?.retestOutcome === "not-reproduced") {
    response = "기존 비교 응답 원문 없음\n이번 조건에서 미재현 기록만 보존";
    responseNote = "미재현은 수정 완료나 전체 취약점 부재를 증명하지 않습니다.";
  } else if (item?.retestOutcome === "unverified") {
    response = "응답 원문 없음\n평가 계정 신원 근거 확인 불가";
    responseNote = "신원 근거 부족 상태를 보존하며 안전한 결과로 단정하지 않습니다.";
  } else if (["confirmed", "suspected"].includes(item?.value)) {
    response = `HTTP/1.1 200 OK\nContent-Type: application/json\n\n{\n  "resource": "<RESOURCE>",\n  "owner": "<OWNER_A>",\n  "data": "<COMPARISON_PLACEHOLDER>"\n}`;
    responseNote = "합성 응답 예시입니다. 상태 코드 200만으로 판정하지 않습니다.";
  } else if (item?.value === "allowed") {
    response = "비교 응답 제공 없음\n등록 정책상 허용 근거만 표시";
    responseNote = "정책상 허용은 비교 전송 성공이나 취약점 부재를 뜻하지 않습니다.";
  } else {
    response = "응답 근거 없음\n전송 상태: UNKNOWN\n자동 재전송하지 않음";
    responseNote = "전송 불명은 빈 성공 응답이나 안전한 결과로 바꾸지 않습니다.";
  }

  return `<section class="card http-examples" aria-label="요청·응답 예시"><div class="card-header"><h2 class="section-title">요청·응답 예시</h2><span class="badge neutral">합성 예시 · 실행 안 함</span></div><div class="card-body"><div class="http-example-grid"><div class="http-example"><div class="code-toolbar"><span>요청 · 실행 안 함</span></div><pre class="code-block"><code>${escapeHtml(request)}</code></pre></div><div class="http-example"><div class="code-toolbar"><span>응답 · 원문 아님</span></div><pre class="code-block"><code>${escapeHtml(response)}</code></pre><p class="small-text muted">${escapeHtml(responseNote)}</p></div></div><p class="small-text muted">실제 인증 값과 원문 캡처를 포함하지 않은 합성 예시입니다.</p></div></section>`;
}
