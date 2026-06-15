const $ = (id) => document.getElementById(id);

let costChart = null;
let signalChart = null;
let latestIncident = null;
let pendingApprovals = [];

function setStatus(state, text) {
  const dot = $("statusDot");
  dot.className = "dot " + (state || "");
  $("statusText").textContent = text;
}

function fmtUsd(n) {
  return "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function sevTag(sev) {
  return `<span class="tag ${sev}">${sev}</span>`;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function renderHealth(data) {
  const score = data.health_score;
  const ring = $("healthRing");
  ring.style.setProperty("--score", score);
  ring.dataset.score = Math.round(score);
  $("mtdSpend").textContent = fmtUsd(data.mtd_spend_usd);
  $("costDelta").textContent = (data.cost_delta_pct >= 0 ? "+" : "") + data.cost_delta_pct.toFixed(1) + "%";
  $("openIncidents").textContent = data.open_incidents;
  $("pendingApprovals").textContent = data.pending_approvals;
  $("pillAlarms").textContent = data.active_alarms;
  $("pillServices").textContent = data.services_monitored.length;
}

function renderCostChart(byService) {
  const labels = Object.keys(byService);
  const values = Object.values(byService);
  const ctx = $("costChart").getContext("2d");
  if (costChart) costChart.destroy();
  costChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "USD",
        data: values,
        backgroundColor: "rgba(56,189,248,.55)",
        borderColor: "#38bdf8",
        borderWidth: 1,
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,.04)" } },
        y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,.04)" } },
      },
    },
  });
}

function renderSignalChart(sparklines) {
  const labels = Array.from({ length: 24 }, (_, i) => i);
  const datasets = Object.entries(sparklines).map(([key, points], idx) => {
    const colors = ["#38bdf8", "#fb7185", "#a78bfa", "#34d399", "#fbbf24"];
    const c = colors[idx % colors.length];
    return {
      label: key,
      data: points,
      borderColor: c,
      backgroundColor: c + "22",
      tension: 0.35,
      pointRadius: 0,
      borderWidth: 2,
    };
  });
  const ctx = $("signalChart").getContext("2d");
  if (signalChart) signalChart.destroy();
  signalChart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#94a3b8", boxWidth: 10 } } },
      scales: {
        x: { ticks: { color: "#64748b", maxTicksLimit: 8 }, grid: { display: false } },
        y: { ticks: { color: "#64748b" }, grid: { color: "rgba(255,255,255,.04)" } },
      },
    },
  });
}

function renderIncidents(incidents) {
  const el = $("incidentList");
  if (!incidents.length) {
    el.innerHTML = '<div class="empty">Run analysis to generate an incident report.</div>';
    $("incidentCount").textContent = "0";
    return;
  }
  $("incidentCount").textContent = String(incidents.length);
  el.innerHTML = incidents.map((inc) => `
    <article class="incident" data-id="${inc.incident_id}">
      <h4>${inc.title}</h4>
      <p>${inc.summary}</p>
      <p style="font-size:12px;margin-bottom:8px"><strong>RCA:</strong> ${inc.root_cause_hypothesis || "—"}</p>
      <div class="meta">
        ${sevTag(inc.severity)}
        <span class="tag">${inc.status}</span>
        <span class="tag">${inc.metric_anomalies.length} metric · ${inc.cost_anomalies.length} cost</span>
      </div>
    </article>
  `).join("");
}

function renderApprovals(approvals) {
  const el = $("approvalList");
  pendingApprovals = approvals.filter((a) => a.status === "pending");
  if (!pendingApprovals.length) {
    el.innerHTML = '<div class="empty">No pending write actions.</div>';
    return;
  }
  el.innerHTML = pendingApprovals.map((a) => `
    <div class="approval" data-id="${a.approval_id}">
      <h4>${a.action.title}</h4>
      <p>${a.action.description}</p>
      <p class="mono" style="font-size:11px;color:var(--faint);margin-bottom:8px">tool: ${a.action.tool_name} · impact: ${a.action.estimated_impact || "—"}</p>
      <div class="approval-actions">
        <button class="btn ok" data-decision="approved" data-id="${a.approval_id}">✓ Approve & execute</button>
        <button class="btn danger" data-decision="rejected" data-id="${a.approval_id}">✕ Reject</button>
      </div>
    </div>
  `).join("");

  el.querySelectorAll("button[data-decision]").forEach((btn) => {
    btn.addEventListener("click", () => decideApproval(btn.dataset.id, btn.dataset.decision));
  });
}

function renderTrace(steps) {
  const el = $("traceLog");
  if (!steps || !steps.length) {
    el.innerHTML = '<div class="empty">Agent trace will appear after analysis.</div>';
    return;
  }
  el.innerHTML = steps.map((s) => `
    <div class="trace-line">
      <span>#${s.step}</span>
      <span class="phase">${s.phase}</span>
      <span>${s.summary}</span>
      <span class="ms">${s.duration_ms}ms</span>
    </div>
  `).join("");
}

async function loadDashboard() {
  const data = await api("/v1/dashboard");
  renderHealth(data);
  renderCostChart(data.cost_by_service);
  renderSignalChart(data.metric_sparklines);
  renderIncidents(data.recent_incidents);
  if (data.recent_incidents[0]?.agent_trace) {
    renderTrace(data.recent_incidents[0].agent_trace);
    latestIncident = data.recent_incidents[0];
  }
}

async function loadApprovals() {
  const approvals = await api("/v1/approvals");
  renderApprovals(approvals);
}

async function runAnalysis() {
  setStatus("busy", "agent running");
  $("runBtn").disabled = true;
  try {
    const result = await api("/v1/agent/analyze", {
      method: "POST",
      body: JSON.stringify({
        scope: "full",
        lookback_hours: 24,
        include_cost: true,
        include_metrics: true,
        include_trusted_advisor: true,
      }),
    });
    $("pillMode").textContent = result.mode;
    latestIncident = result.incident;
    renderIncidents([result.incident, ...(await api("/v1/incidents")).filter((i) => i.incident_id !== result.incident.incident_id)].slice(0, 5));
    renderTrace(result.incident.agent_trace);
    renderApprovals(result.approval_requests);
    await loadDashboard();
    setStatus("live", "analysis complete");
  } catch (err) {
    console.error(err);
    setStatus("", "error");
  } finally {
    $("runBtn").disabled = false;
  }
}

async function decideApproval(id, decision) {
  setStatus("busy", "executing remediation");
  try {
    await api(`/v1/approvals/${id}/decide`, {
      method: "POST",
      body: JSON.stringify({ decision, note: decision === "approved" ? "Approved via UI" : "Rejected via UI", decided_by: "demo-operator" }),
    });
    await loadApprovals();
    await loadDashboard();
    setStatus("live", decision === "approved" ? "remediation executed" : "action rejected");
  } catch (err) {
    console.error(err);
    setStatus("", "approval error");
  }
}

async function boot() {
  try {
    const health = await api("/healthz");
    $("pillMode").textContent = health.runtime || (health.demo_mode ? "demo" : "live");
    if (health.public_url) {
      document.querySelector(".brand small").textContent =
        health.runtime === "live-aws" ? "Live AWS · Bedrock" : "Demo · Render";
    }
    setStatus("live", health.runtime === "live-aws" ? "live aws" : "connected");
    await loadDashboard();
    await loadApprovals();
  } catch (err) {
    console.error(err);
    setStatus("", "offline");
  }
}

$("runBtn").addEventListener("click", runAnalysis);
$("refreshBtn").addEventListener("click", async () => {
  setStatus("busy", "refreshing");
  await loadDashboard();
  await loadApprovals();
  setStatus("live", "connected");
});

boot();
