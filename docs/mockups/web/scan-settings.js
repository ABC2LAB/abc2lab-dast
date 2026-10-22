"use strict";

// New-scan settings are presentation-only. Secret fields are intentionally never
// copied into state or passed to the mock saveConfig helper.
function scanSettingsConfig() {
  const provider = state.provider === "external" ? "external" : "ollama";
  return state.configs[provider];
}

function scanSettingsPanel() {
  const config = scanSettingsConfig();
  const provider = state.provider === "external" ? "external" : "ollama";
  const options = state.form;
  return `<section class="scan-model-settings" aria-labelledby="scan-settings-title">
    <div class="section-inline-heading"><div><h3 id="scan-settings-title" class="subsection-title">모델과 실행 설정</h3><p class="small-text muted">이번 진단에 적용할 모델·실행 한도를 선택합니다.</p></div>${badge("진단별 설정", "purple")}</div>
    <fieldset class="field"><legend>모델 연결</legend><div class="provider-grid">${[["ollama", "server", "로컬 Ollama", "내 환경의 로컬 모델"], ["external", "globe", "외부 / 내부 API", "등록한 모델 API"]].map(([value, glyph, label, description]) => `<label class="provider-card ${provider === value ? "selected" : ""}"><input type="radio" name="provider" value="${value}" ${provider === value ? "checked" : ""}>${icon(glyph)}<strong>${label}</strong><small>${description}</small></label>`).join("")}</div></fieldset>
    <div class="field"><label for="profile-name">프로필 이름</label><input id="profile-name" name="profileName" value="${escapeHtml(config.name)}" required maxlength="60"></div>
    <div class="field"><label for="model-endpoint">서버 주소</label><input id="model-endpoint" name="endpoint" type="url" value="${escapeHtml(config.endpoint)}" required><small>${provider === "ollama" ? "실제 배포 시 app이 내부 Ollama 서비스에 연결합니다." : "목업은 입력한 주소로 연결하지 않습니다."}</small></div>
    <div class="field"><label for="model-id">모델 ID</label><input id="model-id" name="model" value="${escapeHtml(config.model)}" required maxlength="100"></div>
    ${provider === "external" ? `<div class="field"><label for="api-key">API 키</label><input id="api-key" type="password" autocomplete="off" placeholder="실제 키 없이 화면을 검토할 수 있습니다."><small>이 목업은 키를 저장하거나 전송하지 않습니다.</small></div>` : ""}
    <div class="field-row"><div class="field"><label for="model-timeout">응답 대기 시간 (초)</label><input id="model-timeout" name="timeout" type="number" min="1" max="120" required value="${escapeHtml(config.timeout)}"></div><div class="field"><label for="model-tokens">출력 토큰 상한</label><input id="model-tokens" name="tokens" type="number" min="128" max="32768" required value="${escapeHtml(config.tokens)}"></div></div>
    <div class="field-row"><div class="field"><label for="max-attempts">최대 시도 횟수</label><input id="max-attempts" name="maxAttempts" type="number" min="1" max="500" required value="${escapeHtml(options.maxAttempts ?? 60)}"><small>1~500회 · 기본 60회</small></div><div class="field"><label for="max-duration">최대 실행 시간 (분)</label><input id="max-duration" name="maxDuration" type="number" min="1" max="120" required value="${escapeHtml(options.maxDuration ?? 5)}"><small>1~120분 · 기본 5분</small></div></div>
    <div class="field"><label for="concurrency">동시 요청 수</label><input id="concurrency" name="concurrency" type="number" min="1" max="4" required value="${escapeHtml(options.concurrency ?? 1)}"><small>S1 예시 기본값은 1개입니다.</small></div>
    <div class="connection-status ${state.connection === "success" ? "connected" : ""}"><span>${icon(state.connection === "success" ? "check" : "globe")}${state.connection === "testing" ? "예시 상태를 확인하는 중…" : state.connection === "success" ? "예시 연결 성공 · 실제 모델 호출 없음" : "아직 연결 확인을 하지 않았습니다."}</span>${button(state.connection === "testing" ? "확인 중…" : "연결 확인 (데모)", "test-connection", "secondary small", "", state.connection === "testing" ? "disabled" : "")}</div>
  </section>`;
}

function scanLocalConfigSummary() {
  return `<details class="inline-settings"><summary>로컬 실행 구성 보기</summary><div class="system-services"><div class="system-service"><span class="stat-icon purple">${icon("server")}</span><div><strong>app</strong><small>웹 화면 · API · 진단 worker</small></div>${badge("표시 예시", "neutral")}</div><div class="system-service"><span class="stat-icon purple">${icon("sparkle")}</span><div><strong>ollama</strong><small>선택 가능한 로컬 모델</small></div>${badge("표시 예시", "neutral")}</div><div class="system-service"><span class="stat-icon purple">${icon("database")}</span><div><strong>db</strong><small>PostgreSQL + AGE</small></div>${badge("표시 예시", "neutral")}</div></div></details>`;
}

function readScanSettings(form) {
  const data = new FormData(form);
  const bounded = (name, fallback, min, max) => Math.min(max, Math.max(min, Number.parseInt(data.get(name), 10) || fallback));
  state.form.maxAttempts = bounded("maxAttempts", 60, 1, 500);
  state.form.maxDuration = bounded("maxDuration", 5, 1, 120);
  state.form.concurrency = bounded("concurrency", 1, 1, 4);
  state.form.provider = data.get("provider") === "external" ? "external" : "ollama";
  state.provider = state.form.provider;
  if (typeof saveConfig === "function") saveConfig(form);
}

function captureModelDraft(form) {
  if (!form?.querySelector("#model-id")) return;
  saveConfig(form);
  for (const name of ["maxAttempts", "maxDuration", "concurrency"]) {
    state.form[name] = form.elements[name].value;
  }
}
