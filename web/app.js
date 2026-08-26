const $ = (id) => document.getElementById(id);

let costChart = null;
let signalChart = null;
let latestIncident = null;
let expandedIncident = null;
let feedItems = [];
let lastReasoner = "";

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

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
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
    .map((f) => `<li class="feed-item ${escapeHtml(f.type)}">${escapeHtml(f.msg)}</li>`)
    .join("");
}

function setStatus(state, text) {
  const dot = $("statusDot");
  dot.className = "pulse-dot " + (state || "");
  $("statusText").textContent = text;
}

function reasonerFromIncident(inc) {
  const tag = (inc?.tags || []).find((t) => String(t).startsWith("reasoner:"));
  return tag ? tag.split(":")[1] : "";
}

function setReasonerChip(reasoner) {
  lastReasoner = reasoner || lastReasoner;
  const chip = $("reasonerChip");
  const label = $("reasonerLabel");
  const pipe = $("pipeReasonSub");
  if (!chip || !label) return;
  if (reasoner === "bedrock") {
    chip.dataset.kind = "bedrock";
    label.textContent = "Claude";
    if (pipe) pipe.textContent = "Claude on Bedrock";
  } else if (reasoner === "rules_engine") {
    chip.dataset.kind = "rules";
    label.textContent = "Rules";
    if (pipe) pipe.textContent = "Deterministic rules engine";
  } else {
    chip.dataset.kind = "";
    label.textContent = "Idle";
  }
}

function setAttentionBanner(pendingCount) {
  const banner = $("attnBanner");
  const title = $("attnTitle");
  if (!banner || !title) return;
  if (pendingCount > 0) {
    banner.classList.remove("hidden");
    title.textContent =
      pendingCount === 1 ? "1 write waiting on you" : `${pendingCount} writes waiting on you`;
  } else {
    banner.classList.add("hidden");
  }
}

function sevTag(sev) {
  return `<span class="tag ${escapeHtml(sev)}">${escapeHtml(sev)}</span>`;
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

  $("mtdSpend").textContent = fmtUsd(data.mtd_spend_usd);
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

  const caption = $("healthCaption");
  if (caption) {
    if (data.pending_approvals > 0) {
      caption.textContent = "Degraded by HITL queue — decisions pending";
    } else if (score >= 80) {
      caption.textContent = "Healthy — no blocking operator work";
    } else if (score >= 50) {
      caption.textContent = "Watch — open incidents need review";
    } else {
      caption.textContent = "Stressed — multiple open issues";
    }
  }

  $("navIncidents").textContent = data.open_incidents;
  $("navApprovals").textContent = data.pending_approvals;
  $("incidentCount").textContent = data.recent_incidents.length;
  const fromInc = reasonerFromIncident(data.recent_incidents[0]);
  if (fromInc) setReasonerChip(fromInc);
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
        <span>Run analysis to collect telemetry and draft an RCA</span>
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
          <span class="risk ${escapeHtml(a.risk)}">${escapeHtml(a.risk)}</span>
          <span>${escapeHtml(a.title)}</span>
        </div>`
        )
        .join("");

      const reasoner = reasonerFromIncident(inc);
      const reasonerTag = reasoner
        ? `<span class="tag">${escapeHtml(reasoner === "bedrock" ? "Claude" : "rules")}</span>`
        : "";
      const writes = (inc.recommended_actions || []).filter((a) => a.risk === "write").length;

      return `
      <article class="incident-card ${isOpen ? "expanded" : ""}" data-id="${escapeHtml(inc.incident_id)}" style="animation-delay:${idx * 60}ms">
        <div class="incident-head" data-toggle="${escapeHtml(inc.incident_id)}" role="button" tabindex="0" aria-expanded="${isOpen}">
          <div class="sev-indicator ${escapeHtml(inc.severity)}"></div>
          <div class="incident-body">
            <h3>${escapeHtml(inc.title)}</h3>
            <p>${escapeHtml(inc.summary)}</p>
            <div class="incident-meta">
              ${sevTag(inc.severity)}
              <span class="tag">${escapeHtml(inc.status.replace(/_/g, " "))}</span>
              ${reasonerTag}
              <span class="tag">${inc.metric_anomalies?.length || 0} metric</span>
              <span class="tag">${inc.cost_anomalies?.length || 0} cost</span>
              ${writes ? `<span class="tag warning">${writes} write${writes === 1 ? "" : "s"}</span>` : ""}
            </div>
          </div>
          <svg class="chevron" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
        </div>
        <div class="incident-detail">
          <div class="incident-detail-inner">
            <div class="rca-block">
              <strong>Why this happened (RCA)</strong>
              ${escapeHtml(inc.root_cause_hypothesis || "—")}
            </div>
            ${actions ? `<div class="action-list">${actions}</div>` : ""}
          </div>
        </div>
      </article>`;
    })
    .join("");

  el.querySelectorAll("[data-toggle]").forEach((head) => {
    const toggle = () => {
      const id = head.dataset.toggle;
      expandedIncident = expandedIncident === id ? null : id;
      renderIncidents(incidents);
      if (expandedIncident && incidents.find((i) => i.incident_id === id)?.agent_trace) {
        renderTrace(incidents.find((i) => i.incident_id === id).agent_trace);
      }
    };
    head.addEventListener("click", toggle);
    head.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggle();
      }
    });
  });
}

/* ── Approvals ── */

function renderApprovals(approvals) {
  const el = $("approvalList");
  const pending = approvals.filter((a) => a.status === "pending");
  setAttentionBanner(pending.length);

  if (!pending.length) {
    el.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">✓</div>
        <p>Nothing waiting on you</p>
        <span>Write remediations land here. Until then, AWS is unchanged.</span>
      </div>`;
    return;
  }

  el.innerHTML = pending
    .map(
      (a, idx) => `
    <div class="approval-card" data-id="${escapeHtml(a.approval_id)}" style="animation-delay:${idx * 80}ms">
      <div class="approval-card-head">
        <h3>${escapeHtml(a.action.title)}</h3>
        <span class="risk ${escapeHtml(a.action.risk)}">${escapeHtml(a.action.risk)}</span>
      </div>
      <p>${escapeHtml(a.action.description)}</p>
      <dl class="approval-facts">
        <div class="approval-fact">
          <dt>If you approve</dt>
          <dd>${escapeHtml(a.action.estimated_impact || "Impact not specified")}</dd>
        </div>
        <div class="approval-fact">
          <dt>Rollback</dt>
          <dd>${escapeHtml(a.action.rollback_plan || "Not specified")}</dd>
        </div>
      </dl>
      <div class="approval-meta">tool: ${escapeHtml(a.action.tool_name)}</div>
      <div class="approval-actions">
        <button class="btn ok sm" data-decision="approved" data-id="${escapeHtml(a.approval_id)}">Approve & execute</button>
        <button class="btn danger sm" data-decision="rejected" data-id="${escapeHtml(a.approval_id)}">Reject</button>
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
      <span class="trace-phase">${escapeHtml(s.phase.replace(/_/g, " "))}</span>
      <span class="trace-summary">${escapeHtml(s.summary)}</span>
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
    setReasonerChip(result.reasoner);

    const reasonerLabel = result.reasoner === "bedrock" ? "Bedrock" : "rules engine";
    const pending = result.approval_requests.length;
    addFeed(`Reasoner: ${reasonerLabel}`, result.reasoner === "bedrock" ? "ok" : "info");
    addFeed(`Incident opened: ${result.incident.title}`, pending ? "warn" : "ok");
    addFeed(
      pending
        ? `${pending} write actions queued for approval`
        : "No write remediations queued",
      pending ? "info" : "muted"
    );

    const all = await api("/v1/incidents");
    renderIncidents([
      result.incident,
      ...all.filter((i) => i.incident_id !== result.incident.incident_id),
    ].slice(0, 8));
    renderTrace(result.incident.agent_trace);
    await loadDashboard();
    await loadApprovals();

    setStatus("live", "analysis complete");
    toast(
      pending
        ? `Incident created · ${reasonerLabel} · ${pending} approvals pending`
        : `Analysis complete · ${reasonerLabel} · no write actions`
    );
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
  $("attnGoto")?.addEventListener("click", () => scrollToSection("approvals"));
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
      health.runtime === "live-aws"
        ? "Live AWS · Bedrock"
        : health.environment === "local"
          ? "Demo · local"
          : "Demo · Render";
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
