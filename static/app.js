(() => {
  const formatMoney = (invoice) => {
    if (!invoice.amount) return "—";
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: invoice.amount.currency,
      }).format(invoice.amount.value);
    } catch {
      return `${invoice.amount.currency} ${invoice.amount.value.toFixed(2)}`;
    }
  };

  const formatDate = (value) => {
    if (!value) return "—";
    const date = new Date(`${value}T00:00:00Z`);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    }).format(date);
  };

  const isOverdue = (dueDate) => {
    if (!dueDate) return false;
    const due = new Date(`${dueDate}T00:00:00Z`);
    const today = new Date();
    const todayUtc = new Date(
      Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()),
    );
    return due < todayUtc;
  };

  let status = {
    connected: false,
    email: null,
    hasLlm: false,
    llmProvider: null,
    llmModel: null,
    googleConfigured: false,
  };
  let result = null;
  let error = null;
  let isScanning = false;
  const authError = window.__INITIAL_AUTH_ERROR__ || null;

  const el = (id) => document.getElementById(id);

  const setAlert = () => {
    const alert = el("alert");
    const msg = authError || error;
    if (!msg) {
      alert.hidden = true;
      alert.textContent = "";
      return;
    }
    alert.hidden = false;
    alert.textContent = msg;
  };

  const renderActions = () => {
    const line = el("status-line");
    if (!status.hasLlm) {
      line.textContent =
        "LLM not configured — add OPENAI_API_KEY to .env.local";
    } else if (status.connected) {
      line.textContent = `Connected as ${status.email || "Gmail account"}`;
    } else if (status.googleConfigured) {
      line.textContent = "Gmail not connected";
    } else {
      line.textContent = "Google OAuth not configured — use Demo";
    }

    const actions = el("actions");
    actions.innerHTML = "";

    if (status.connected) {
      const disconnect = document.createElement("button");
      disconnect.type = "button";
      disconnect.className = "btn-ghost";
      disconnect.textContent = "Disconnect";
      disconnect.onclick = () => void handleDisconnect();
      actions.appendChild(disconnect);
    } else {
      const connect = document.createElement("button");
      connect.type = "button";
      connect.className = "btn-primary";
      connect.textContent = "Connect Gmail (read-only)";
      connect.disabled = !status.googleConfigured;
      connect.onclick = () => {
        window.location.href = "/api/auth/google";
      };
      actions.appendChild(connect);
    }

    const scan = document.createElement("button");
    scan.type = "button";
    scan.className = "btn-accent";
    scan.disabled = isScanning || !status.hasLlm;
    scan.textContent = isScanning
      ? "LLM scanning…"
      : status.connected
        ? "Scan inbox"
        : "Run demo scan";
    scan.onclick = () =>
      void handleScan(status.connected ? "gmail" : "demo");
    actions.appendChild(scan);

    if (status.connected) {
      const demo = document.createElement("button");
      demo.type = "button";
      demo.className = "btn-outline";
      demo.disabled = isScanning || !status.hasLlm;
      demo.textContent = "Demo";
      demo.onclick = () => void handleScan("demo");
      actions.appendChild(demo);
    }
  };

  const renderStats = () => {
    const invoices = result?.invoices || [];
    el("stat-scanned").textContent = result ? String(result.scanned) : "—";
    el("stat-invoices").textContent = result ? String(invoices.length) : "—";
    if (!result) {
      el("stat-total").textContent = "—";
      return;
    }
    const totalDue = invoices.reduce(
      (sum, invoice) => sum + (invoice.amount?.value || 0),
      0,
    );
    const currency = invoices[0]?.amount?.currency || "USD";
    try {
      el("stat-total").textContent = new Intl.NumberFormat(undefined, {
        style: "currency",
        currency,
      }).format(totalDue);
    } catch {
      el("stat-total").textContent = `${currency} ${totalDue.toFixed(2)}`;
    }
  };

  const PRIORITY_LABELS = {
    pay_now: "Pay now",
    schedule: "Schedule",
    hold: "Hold",
  };

  const priorityBadge = (priority) => {
    if (!priority) return "—";
    const label = PRIORITY_LABELS[priority] || priority;
    return `<span class="badge ${escapeHtml(priority)}">${escapeHtml(label)}</span>`;
  };

  const renderPlan = () => {
    const box = el("plan");
    const plan = result?.plan;

    if (!result) {
      box.innerHTML = `<p class="empty">The planner agent runs after each scan.</p>`;
      return;
    }
    if (!plan || plan.items.length === 0) {
      box.innerHTML = `<p class="empty">${escapeHtml(plan?.summary || "No payment plan for this scan.")}</p>`;
      return;
    }

    const totals = plan.totals
      .map((total) => {
        try {
          return new Intl.NumberFormat(undefined, {
            style: "currency",
            currency: total.currency,
          }).format(total.value);
        } catch {
          return `${total.currency} ${total.value.toFixed(2)}`;
        }
      })
      .join(" · ");

    const flags = plan.riskFlags.length
      ? `<ul class="flags">${plan.riskFlags
          .map((flag) => `<li>${escapeHtml(flag)}</li>`)
          .join("")}</ul>`
      : "";

    const byId = new Map((result.invoices || []).map((inv) => [inv.id, inv]));
    const rows = plan.items
      .map((item) => {
        const invoice = byId.get(item.invoiceId);
        return `<tr>
          <td>${priorityBadge(item.priority)}</td>
          <td><p class="vendor">${escapeHtml(item.vendor)}</p></td>
          <td class="amount">${escapeHtml(invoice ? formatMoney(invoice) : "—")}</td>
          <td>${escapeHtml(formatDate(item.payBy))}</td>
          <td>${escapeHtml(item.reason)}</td>
        </tr>`;
      })
      .join("");

    box.innerHTML = `<div class="plan-card">
      <p class="plan-summary">${escapeHtml(plan.summary)}</p>
      <p class="meta">Total extracted: ${escapeHtml(totals || "—")}</p>
      ${flags}
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Priority</th>
            <th scope="col">Vendor</th>
            <th scope="col">Amount</th>
            <th scope="col">Pay by</th>
            <th scope="col">Why</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  };

  const renderResults = () => {
    const pill = el("llm-pill");
    if (status.hasLlm) {
      pill.className = "llm-pill";
      pill.textContent = `LLM: ${status.llmProvider}/${status.llmModel}`;
    } else {
      pill.className = "llm-pill warn";
      pill.textContent = "Set OPENAI_API_KEY or OLLAMA_BASE_URL";
    }

    const box = el("results");
    const invoices = result?.invoices || [];

    if (!status.hasLlm) {
      box.innerHTML = `<p class="empty warn">This app is LLM-only. Add <code>OPENAI_API_KEY</code> (or <code>OLLAMA_BASE_URL</code>) to <code>.env.local</code>, restart the server, then scan.</p>`;
      return;
    }
    if (!result) {
      box.innerHTML = `<p class="empty">Connect Gmail and scan, or run a demo scan. Every email is classified by the LLM.</p>`;
      return;
    }
    if (invoices.length === 0) {
      box.innerHTML = `<p class="empty">No invoice emails found in the scanned set.</p>`;
      return;
    }

    const rows = invoices
      .map((invoice) => {
        const overdue = isOverdue(invoice.dueDate);
        const link =
          invoice.source === "gmail"
            ? `<p class="meta"><a href="${invoice.gmailUrl}" target="_blank" rel="noopener noreferrer">Open in Gmail</a></p>`
            : `<p class="meta">Demo sample</p>`;
        return `<tr>
          <td>
            <p class="vendor">${escapeHtml(invoice.vendor)}</p>
            <p class="subject">${escapeHtml(invoice.subject)}</p>
            ${link}
          </td>
          <td class="amount">${escapeHtml(formatMoney(invoice))}</td>
          <td>
            <span class="${overdue ? "overdue" : ""}">${escapeHtml(formatDate(invoice.dueDate))}</span>
            ${overdue ? '<span class="overdue-label">Overdue</span>' : ""}
          </td>
          <td>${escapeHtml(invoice.invoiceNumber || "—")}</td>
          <td>${Math.round(invoice.confidence * 100)}%</td>
        </tr>`;
      })
      .join("");

    box.innerHTML = `<div class="table-wrap">
      <table>
        <caption class="sr-only" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)">Invoice emails with amount and due date</caption>
        <thead>
          <tr>
            <th scope="col">Vendor / email</th>
            <th scope="col">Amount</th>
            <th scope="col">Due date</th>
            <th scope="col">Invoice #</th>
            <th scope="col">Confidence</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  };

  const escapeHtml = (value) =>
    String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  const render = () => {
    setAlert();
    renderActions();
    renderStats();
    renderPlan();
    renderResults();
  };

  const refreshStatus = async () => {
    const response = await fetch("/api/auth/status");
    status = await response.json();
    render();
  };

  const handleDisconnect = async () => {
    error = null;
    await fetch("/api/auth/logout", { method: "POST" });
    result = null;
    await refreshStatus();
  };

  const handleScan = async (mode) => {
    isScanning = true;
    error = null;
    render();
    try {
      const response = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      const data = await response.json();
      if (!response.ok) {
        error = data.error || "Scan failed";
        return;
      }
      result = data;
    } catch {
      error = "Could not reach the local agent.";
    } finally {
      isScanning = false;
      render();
    }
  };

  void refreshStatus();
})();
