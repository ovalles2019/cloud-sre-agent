const $ = (id) => document.getElementById(id);

let costChart = null;
let signalChart = null;
let latestIncident = null;
let expandedIncident = null;
let feedItems = [];

const ORB_CIRC = 327;

const chartDefaults = {
  grid: "rgba(255,255,255,0.04)",
  tick: "#8b8b9e",
  teal: "#00ffd5",
  violet: "#7c6bff",
  coral: "#ff6b4a",
  amber: "#ffb020",
  ok: "#3dffab",
};

/* ── Utilities ── */

function fmtUsd(n) {
  return "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function animateValue(el, end, duration = 900, prefix = "", suffix = "") {
  if (!el) return;
  const start = parseFloat(el.dataset.val || "0") || 0;
  const diff = end - start;
  if (Math.abs(diff) < 0.01) {
    el.textContent = prefix + (Number.isInteger(end) ? end : end.toFixed(1)) + suffix;
    el.dataset.val = end;
    return;
  }
  const t0 = performance.now();
  const step = (now) => {
    const p = Math.min((now - t0) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    const cur = start + diff * eased;
    el.textContent =
      prefix +
      (Number.isInteger(end) ? Math.round(cur) : cur.toFixed(1)) +
      suffix;
    if (p < 1) requestAnimationFrame(step);
    else el.dataset.val = end;
  };
  requestAnimationFrame(step);
}

function toast(msg, type = "ok") {
  const box = $("toasts");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translateY(8px)";
    el.style.transition = "0.3s ease";
    setTimeout(() => el.remove(), 300);
  }, 3200);
}

function addFeed(msg, type = "info") {
  const ts = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  feedItems.unshift({ msg: `[${ts}] ${msg}`, type });
  feedItems = feedItems.slice(0, 8);
  const el = $("feedList");
  if (!el) return;
  el.innerHTML = feedItems
    .map((f) => `<li class="feed-item ${f.type}">${f.msg}</li>`)
    .join("");
}

function setStatus(state, text) {
  const dot = $("statusDot");
  dot.className = "pulse-dot " + (state || "");
  $("statusText").textContent = text;
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

/* ── Pipeline animation ── */

const PIPE_STEPS = ["collect", "reason", "gate", "act"];

function setPipelineStep(activeIdx) {
  PIPE_STEPS.forEach((name, i) => {
    const el = document.querySelector(`.pipe-step[data-step="${name}"]`);
    const mini = document.querySelectorAll(".pm-step")[i];
    if (!el) return;
    el.classList.remove("active", "done");
    mini?.classList.remove("active", "done");
    if (i < activeIdx) {
      el.classList.add("done");
      mini?.classList.add("done");
    } else if (i === activeIdx) {
      el.classList.add("active");
      mini?.classList.add("active");
    }
  });
}

function resetPipeline() {
  setPipelineStep(-1);
}

async function animatePipelineDuringRun() {
  for (let i = 0; i < PIPE_STEPS.length; i++) {
    setPipelineStep(i);
    await new Promise((r) => setTimeout(r, 400));
  }
  setPipelineStep(PIPE_STEPS.length);
}

/* ── Health orb ── */

function renderHealth(data) {
  const score = data.health_score;
  animateValue($("healthScore"), Math.round(score));
  const fill = $("orbFill");
  const bar = $("healthBar");
  if (fill) {
    fill.style.strokeDashoffset = ORB_CIRC - (ORB_CIRC * score) / 100;
    fill.style.stroke = score >= 70 ? chartDefaults.teal : score >= 40 ? chartDefaults.amber : chartDefaults.coral;
  }
  if (bar) bar.style.width = score + "%";

  animateValue($("mtdSpend"), data.mtd_spend_usd, 800, "$", "");
  const deltaEl = $("costDelta");
  const delta = data.cost_delta_pct;
  if (deltaEl) {
    deltaEl.textContent = (delta >= 0 ? "+" : "") + delta.toFixed(1) + "% vs prior";
    deltaEl.className = "kpi-delta" + (delta <= 0 ? " positive" : "");
  }
  animateValue($("openIncidents"), data.open_incidents);
  animateValue($("pendingApprovals"), data.pending_approvals);
  $("pillAlarms").textContent = data.active_alarms + " alarms";
  $("pillServices").textContent = data.services_monitored.length;

  $("navIncidents").textContent = data.open_incidents;
  $("navApprovals").textContent = data.pending_approvals;
  $("incidentCount").textContent = data.recent_incidents.length;
}

/* ── Charts ── */

function renderCostChart(byService) {
  const labels = Object.keys(byService);
  const values = Object.values(byService);
  const ctx = $("costChart").getContext("2d");
  if (costChart) costChart.destroy();

  const grad = ctx.createLinearGradient(0, 0, 0, 240);
  grad.addColorStop(0, "rgba(0, 255, 213, 0.7)");
  grad.addColorStop(1, "rgba(124, 107, 255, 0.4)");

  costChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: grad,
        borderColor: chartDefaults.teal,
        borderWidth: 1,
        borderRadius: 8,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 800, easing: "easeOutQuart" },
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: { color: chartDefaults.tick, font: { family: "JetBrains Mono", size: 10 } },
          grid: { display: false },
        },
        y: {
          ticks: { color: chartDefaults.tick, font: { family: "JetBrains Mono", size: 10 } },
          grid: { color: chartDefaults.grid },
        },
      },
    },
  });
}

function renderSignalChart(sparklines) {
  const labels = Array.from({ length: 24 }, (_, i) => `${i}h`);
  const colors = [chartDefaults.teal, chartDefaults.coral, chartDefaults.violet, chartDefaults.ok, chartDefaults.amber];
  const datasets = Object.entries(sparklines).map(([key, points], idx) => {
    const c = colors[idx % colors.length];
    return {
      label: key,
      data: points,
      borderColor: c,
      backgroundColor: c + "18",
      tension: 0.4,
      pointRadius: 0,
      pointHoverRadius: 4,
      borderWidth: 2,
      fill: idx === 0,
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
      animation: { duration: 800 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          labels: { color: chartDefaults.tick, font: { size: 11 }, boxWidth: 10, padding: 14 },
        },
      },
      scales: {
        x: {
          ticks: { color: "#55556a", maxTicksLimit: 8, font: { size: 10 } },
          grid: { display: false },
        },
        y: {
          ticks: { color: chartDefaults.tick, font: { size: 10 } },
          grid: { color: chartDefaults.grid },
        },
      },
    },
  });
}

/* ── Incidents ── */

function renderIncidents(incidents) {
  const el = $("incidentList");
  if (!incidents.length) {
    el.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">◎</div>
        <p>No incidents yet</p>
        <span>Run analysis to generate your first report</span>
      </div>`;
    return;
  }

  el.innerHTML = incidents
    .map((inc, idx) => {
      const isOpen = expandedIncident === inc.incident_id;
      const actions = (inc.recommended_actions || [])
        .map(
          (a) => `
        <div class="action-item">
          <span class="risk ${a.risk}">${a.risk}</span>
          <span>${a.title}</span>
        </div>`
        )
        .join("");

      return `
      <article class="incident-card ${isOpen ? "expanded" : ""}" data-id="${inc.incident_id}" style="animation-delay:${idx * 60}ms">
        <div class="incident-head" data-toggle="${inc.incident_id}">
          <div class="sev-indicator ${inc.severity}"></div>
          <div class="incident-body">
            <h3>${inc.title}</h3>
            <p>${inc.summary}</p>
            <div class="incident-meta">
              ${sevTag(inc.severity)}
              <span class="tag">${inc.status.replace(/_/g, " ")}</span>
              <span class="tag">${inc.metric_anomalies?.length || 0} metric</span>
              <span class="tag">${inc.cost_anomalies?.length || 0} cost</span>
            </div>
          </div>
          <svg class="chevron" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
        </div>
        <div class="incident-detail">
          <div class="incident-detail-inner">
            <div class="rca-block">
              <strong>Root cause hypothesis</strong>
              ${inc.root_cause_hypothesis || "—"}
            </div>
            ${actions ? `<div class="action-list">${actions}</div>` : ""}
          </div>
        </div>
      </article>`;
    })
    .join("");

  el.querySelectorAll("[data-toggle]").forEach((head) => {
    head.addEventListener("click", () => {
      const id = head.dataset.toggle;
      expandedIncident = expandedIncident === id ? null : id;
      renderIncidents(incidents);
      if (expandedIncident && incidents.find((i) => i.incident_id === id)?.agent_trace) {
        renderTrace(incidents.find((i) => i.incident_id === id).agent_trace);
      }
    });
  });
}

/* ── Approvals ── */

function renderApprovals(approvals) {
  const el = $("approvalList");
  const pending = approvals.filter((a) => a.status === "pending");

  if (!pending.length) {
    el.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">✓</div>
        <p>Queue clear</p>
        <span>Write actions will appear here for approval</span>
      </div>`;
    return;
  }

  el.innerHTML = pending
    .map(
      (a, idx) => `
    <div class="approval-card" data-id="${a.approval_id}" style="animation-delay:${idx * 80}ms">
      <h3>${a.action.title}</h3>
      <p>${a.action.description}</p>
      <div class="approval-meta">tool: ${a.action.tool_name} · ${a.action.estimated_impact || "impact TBD"}</div>
      <div class="approval-actions">
        <button class="btn ok sm" data-decision="approved" data-id="${a.approval_id}">Approve & execute</button>
        <button class="btn danger sm" data-decision="rejected" data-id="${a.approval_id}">Reject</button>
      </div>
    </div>`
    )
    .join("");

  el.querySelectorAll("button[data-decision]").forEach((btn) => {
    btn.addEventListener("click", () => decideApproval(btn.dataset.id, btn.dataset.decision));
  });
}

/* ── Trace ── */

function renderTrace(steps) {
  const el = $("traceLog");
  if (!steps?.length) {
    el.innerHTML = `<div class="empty-state inline"><p>Agent trace will appear after analysis</p></div>`;
    return;
  }
  el.innerHTML = steps
    .map(
      (s, idx) => `
    <div class="trace-step" style="animation-delay:${idx * 70}ms">
      <span class="trace-num">${String(s.step).padStart(2, "0")}</span>
      <span class="trace-phase">${s.phase.replace(/_/g, " ")}</span>
      <span class="trace-summary">${s.summary}</span>
      <span class="trace-ms">${s.duration_ms}ms</span>
    </div>`
    )
    .join("");
}

/* ── Data loading ── */

async function loadDashboard() {
  const data = await api("/v1/dashboard");
  renderHealth(data);
  renderCostChart(data.cost_by_service);
  renderSignalChart(data.metric_sparklines);
  renderIncidents(data.recent_incidents);
  if (data.recent_incidents[0]?.agent_trace) {
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
  $("runBtnMobile")?.setAttribute("disabled", "true");
  resetPipeline();
  addFeed("Agent analysis initiated", "info");

  const pipePromise = animatePipelineDuringRun();

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

    await pipePromise;

    $("pillMode").textContent = result.mode;
    latestIncident = result.incident;
    expandedIncident = result.incident.incident_id;

    addFeed(`Incident opened: ${result.incident.title}`, "warn");
    addFeed(`${result.approval_requests.length} write actions queued for approval`, "info");

    const all = await api("/v1/incidents");
    renderIncidents([
      result.incident,
      ...all.filter((i) => i.incident_id !== result.incident.incident_id),
    ].slice(0, 8));
    renderTrace(result.incident.agent_trace);
    renderApprovals(result.approval_requests);
    await loadDashboard();

    setStatus("live", "analysis complete");
    toast(`Incident created · ${result.approval_requests.length} approvals pending`);
    scrollToSection("incidents");
  } catch (err) {
    console.error(err);
    setStatus("error", "error");
    addFeed("Analysis failed — check connection", "warn");
    toast("Analysis failed", "err");
    resetPipeline();
  } finally {
    $("runBtn").disabled = false;
    $("runBtnMobile")?.removeAttribute("disabled");
  }
}

async function decideApproval(id, decision) {
  setStatus("busy", "processing");
  try {
    const result = await api(`/v1/approvals/${id}/decide`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        note: decision === "approved" ? "Approved via UI" : "Rejected via UI",
        decided_by: "operator",
      }),
    });
    await loadApprovals();
    await loadDashboard();
    setStatus("live", decision === "approved" ? "executed" : "rejected");
    addFeed(
      decision === "approved"
        ? `Remediation executed: ${result.action?.tool_name || id}`
        : `Action rejected: ${result.action?.title || id}`,
      decision === "approved" ? "ok" : "info"
    );
    toast(decision === "approved" ? "Remediation executed" : "Action rejected");
  } catch (err) {
    console.error(err);
    setStatus("error", "error");
    toast("Approval action failed", "err");
  }
}

/* ── Navigation ── */

function scrollToSection(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
}

function setActiveNav(section) {
  document.querySelectorAll(".nav-item, .bn-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.section === section);
  });
}

function initNavigation() {
  const links = document.querySelectorAll("[data-section]");
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) setActiveNav(e.target.id);
      });
    },
    { rootMargin: "-30% 0px -60% 0px", threshold: 0 }
  );
  document.querySelectorAll(".section").forEach((s) => observer.observe(s));

  links.forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const id = link.dataset.section;
      scrollToSection(id);
      closeDrawer();
    });
  });
}

function openDrawer() {
  $("drawer").classList.add("open");
  $("drawerBackdrop").classList.add("open");
  document.body.style.overflow = "hidden";
}

function closeDrawer() {
  $("drawer").classList.remove("open");
  $("drawerBackdrop").classList.remove("open");
  document.body.style.overflow = "";
}

/* ── Boot ── */

async function boot() {
  initNavigation();
  $("menuBtn")?.addEventListener("click", openDrawer);
  $("drawerBackdrop")?.addEventListener("click", closeDrawer);
  $("runBtn").addEventListener("click", runAnalysis);
  $("runBtnMobile")?.addEventListener("click", runAnalysis);
  $("refreshBtn").addEventListener("click", async () => {
    setStatus("busy", "refreshing");
    addFeed("Dashboard refresh", "info");
    try {
      await loadDashboard();
      await loadApprovals();
      setStatus("live", "connected");
      toast("Dashboard updated");
    } catch {
      setStatus("error", "offline");
    }
  });

  try {
    const health = await api("/healthz");
    $("pillMode").textContent = health.runtime || (health.demo_mode ? "demo" : "live");
    $("brandSub").textContent =
      health.runtime === "live-aws" ? "Live AWS · Bedrock" : "Demo · Render";
    setStatus("live", health.runtime === "live-aws" ? "live aws" : "online");
    addFeed(`Connected · ${health.runtime} mode`, "ok");
    await loadDashboard();
    await loadApprovals();
    if (latestIncident?.agent_trace) renderTrace(latestIncident.agent_trace);
  } catch (err) {
    console.error(err);
    setStatus("error", "offline");
    addFeed("Backend unreachable", "warn");
  }
}

boot();
