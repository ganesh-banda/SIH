(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const base = window.TRACEPOINT_API_BASE_URL || "http://127.0.0.1:8000";
  const state = {
    api: localStorage.getItem("tracepoint-api") || base,
    alerts: [], offset: 0, limit: 40, more: true, filter: "all", search: "", sort: "risk_desc",
    alertRequest: 0, caseRequest: 0, transactionRequest: 0,
    wallet: null, graph: null, graphScale: 1, graphX: 0, graphY: 0, drag: null
  };
  const number = (value, digits = 0) => value == null || !Number.isFinite(Number(value))
    ? "—" : Number(value).toLocaleString(undefined, {minimumFractionDigits: digits, maximumFractionDigits: digits});
  const percent = (value, digits = 1) => value == null ? "—" : number(Number(value) * 100, digits) + "%";
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const shorten = (value, n = 15) => {
    const s = String(value ?? "");
    return s.length > n * 2 ? s.slice(0, n) + "…" + s.slice(-n) : s;
  };
  const toast = (message) => {
    const el = $("toast");
    el.textContent = message;
    el.classList.add("visible");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => el.classList.remove("visible"), 2800);
  };

  async function api(path) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(state.api + path, {signal: controller.signal});
      if (!response.ok) {
        let detail = "";
        try { detail = (await response.json()).detail || ""; } catch (_) { /* The status remains useful. */ }
        const error = new Error(detail || response.statusText || "API request failed");
        error.status = response.status;
        throw error;
      }
      return response.json();
    } finally {
      clearTimeout(timer);
    }
  }
  function errorMessage(error, kind) {
    if (error.status === 404) return kind + " was not found in the saved synthetic dataset.";
    if (error.status === 422) return "That identifier could not be accepted by the API.";
    if (error.status >= 500) return "The backend could not complete this request. Check its terminal output.";
    if (error.name === "AbortError") return "The backend took too long to respond.";
    return "Could not reach the backend at " + state.api + ". Check API settings.";
  }
  function connection(online) {
    const el = $("connection");
    el.className = "connection " + (online ? "online" : "offline");
    el.innerHTML = "<i></i>" + (online ? "api connected" : "api offline");
  }
  function showTab(name, scroll = false) {
    const investigation = name === "investigation";
    $("alertsView").hidden = investigation;
    $("investigationView").hidden = !investigation;
    $("tabAlerts").classList.toggle("active", !investigation);
    $("tabInvestigation").classList.toggle("active", investigation);
    $("tabAlerts").setAttribute("aria-selected", String(!investigation));
    $("tabInvestigation").setAttribute("aria-selected", String(investigation));
    if (scroll) $("workspace").scrollIntoView({behavior: "smooth"});
  }
  async function loadOverview() {
    try {
      const [summary, model, geo, health] = await Promise.all([
        api("/dataset/summary"), api("/model/summary"), api("/geo/status"), api("/health")
      ]);
      if (!health.components?.duckdb?.ok) {
        const error = new Error("Analysis database unavailable");
        error.status = 503;
        throw error;
      }
      $("metricTransactions").textContent = number(summary.transactions);
      $("metricWallets").textContent = number(summary.wallets);
      $("metricAlerts").textContent = number(summary.alerts);
      $("queueCount").textContent = number(summary.alerts);
      $("metricPrAuc").textContent = number(model.test.pr_auc, 3);
      $("methodPrecision").textContent = percent(model.test.precision);
      $("methodRecall").textContent = percent(model.test.recall);
      $("geoSideStatus").textContent = geo.data_source === "synthetic_fixture"
        ? "SYNTHETIC CITY + ASN FIXTURES" : "LOCAL GEO SOURCE";
      connection(true);
    } catch (error) {
      connection(false);
      $("geoSideStatus").textContent = "BACKEND UNAVAILABLE";
      $("lookupMessage").textContent = errorMessage(error, "Overview");
      $("lookupMessage").classList.add("error");
    }
  }
  function alertParams() {
    const p = new URLSearchParams({limit: String(state.limit), offset: String(state.offset), sort: state.sort});
    if (state.filter === "patterns") p.set("has_pattern", "true");
    if (state.filter === "seed") p.set("seed_linked", "true");
    if (state.search.trim()) p.set("search", state.search.trim());
    return p.toString();
  }
  async function loadAlerts(reset = false) {
    if (reset) {
      state.offset = 0; state.alerts = []; state.more = true;
      $("alertList").innerHTML = '<tr><td colspan="7" class="table-message">Finding alerts…</td></tr>';
    }
    if (!state.more) return;
    const request = ++state.alertRequest;
    try {
      const batch = await api("/alerts?" + alertParams());
      if (request !== state.alertRequest) return;
      state.alerts.push(...batch);
      state.offset += batch.length;
      state.more = batch.length === state.limit;
      renderAlerts();
      connection(true);
    } catch (error) {
      if (request !== state.alertRequest) return;
      $("alertList").innerHTML = '<tr><td colspan="7" class="table-message">' + escapeHtml(errorMessage(error, "Alerts")) + "</td></tr>";
      connection(false);
    }
  }
  function renderAlerts() {
    const rows = state.alerts.map((alert) => {
      const evidence = alert.patterns?.length ? "pattern" : (alert.graph_risk != null ? "seed context" : "model");
      return '<tr data-alert="' + escapeHtml(alert.alert_id) + '" tabindex="0" aria-label="Open alert ' +
        escapeHtml(alert.alert_id) + '"><td title="' + escapeHtml(alert.wallet_id) + '">' +
        escapeHtml(shorten(alert.wallet_id, 15)) + '</td><td class="score-high">' + number(alert.risk_score, 1) +
        '</td><td class="level">' + escapeHtml(alert.risk_category) + '</td><td>' +
        percent(alert.classification_probability) + '</td><td>' + number(alert.anomaly_score, 3) +
        '</td><td>' + escapeHtml(evidence) + '</td><td class="open-cell">↗</td></tr>';
    }).join("");
    $("alertList").innerHTML = rows || '<tr><td colspan="7" class="table-message">No alerts match. Change the filter or search.</td></tr>';
    $("queuePageLabel").textContent = number(state.alerts.length) + " alerts loaded · " +
      $("sortAlerts").selectedOptions[0].textContent;
    $("loadMoreButton").disabled = !state.more;
    if (state.alerts.length) $("previewProbability").textContent = percent(state.alerts[0].classification_probability);
  }
  function setLookupMessage(message, error = false) {
    $("lookupMessage").textContent = message;
    $("lookupMessage").classList.toggle("error", error);
  }
  async function lookup(query) {
    const value = query.trim();
    if (!value) { setLookupMessage("Enter an address or TXID.", true); return; }
    if (value.length > 128 || /\s/.test(value)) {
      setLookupMessage("Use one address or TXID without spaces.", true); return;
    }
    $("lookupButton").disabled = true;
    setLookupMessage("Checking the saved analysis…");
    try {
      if (/^[a-f0-9]{64}$/i.test(value)) {
        await openTransaction(value, true);
        setLookupMessage("Transaction found.");
      } else {
        await openWallet(value);
        setLookupMessage("Address found.");
      }
    } catch (error) {
      setLookupMessage(errorMessage(error, /^[a-f0-9]{64}$/i.test(value) ? "Transaction" : "Address"), true);
    } finally {
      $("lookupButton").disabled = false;
    }
  }
  async function openAlert(id) {
    try {
      const alert = await api("/alerts/" + encodeURIComponent(id));
      await openWallet(alert.wallet_id, alert);
    } catch (error) {
      toast(errorMessage(error, "Alert"));
    }
  }
  async function openWallet(walletId, knownAlert = null) {
    const request = ++state.caseRequest;
    showTab("investigation", true);
    $("caseEmpty").hidden = false;
    $("caseEmpty").querySelector("h3").textContent = "loading the address.";
    $("caseEmpty").querySelector("p").textContent = "Reading risk, evidence, graph, and history from the backend…";
    $("caseContent").hidden = true;
    $("txStandalone").hidden = true;
    try {
      const wallet = await api("/wallets/" + encodeURIComponent(walletId));
      const [explanation, graph, transactions] = await Promise.all([
        knownAlert ? Promise.resolve(knownAlert) : api("/explanation/" + encodeURIComponent(walletId)),
        api("/wallets/" + encodeURIComponent(walletId) + "/graph?limit=40"),
        api("/wallets/" + encodeURIComponent(walletId) + "/transactions?limit=40")
      ]);
      if (request !== state.caseRequest) return;
      state.wallet = wallet;
      state.graph = graph;
      renderWallet(wallet, explanation, graph, transactions);
      $("caseEmpty").hidden = true;
      $("caseContent").hidden = false;
      location.hash = "workspace";
      if (transactions.length) {
        await openTransaction(transactions[0].txid, false, true).catch(() => {
          // Transaction error is rendered inside the detail panel; keep the wallet open.
        });
      }
      return wallet;
    } catch (error) {
      if (request === state.caseRequest) {
        $("caseEmpty").querySelector("h3").textContent = "address unavailable.";
        $("caseEmpty").querySelector("p").textContent = errorMessage(error, "Address");
      }
      throw error;
    }
  }
  function renderWallet(wallet, evidence, graph, transactions) {
    $("caseAlertId").textContent = evidence.alert_id ? " / " + evidence.alert_id : "";
    $("copyAddress").textContent = wallet.wallet_id + " ↗";
    $("caseCategory").textContent = wallet.risk_category || "UNRATED";
    $("scoreValue").textContent = number(wallet.risk_score, 1);
    $("caseExplanation").textContent = evidence.explanation || "No backend explanation is available for this address.";
    $("modelSignal").textContent = percent(wallet.classification_probability);
    $("anomalySignal").textContent = number(wallet.anomaly_score, 3);
    $("graphSignal").textContent = wallet.graph_risk == null ? "none saved" : number(wallet.graph_risk, 3);
    renderShap(evidence.model_evidence || []);
    renderPatterns(evidence.patterns || []);
    renderGraph(graph, wallet.wallet_id);
    renderTransactions(transactions);
    renderRelated(graph, wallet.wallet_id);
    $("networkContext").innerHTML = '<p class="muted-copy">Select a transaction to inspect its observed network metadata.</p>';
    $("transactionDetail").hidden = true;
  }
  function renderShap(items) {
    if (!items.length) {
      $("shapList").innerHTML = '<p class="muted-copy">No model contributions were saved for this address.</p>';
      return;
    }
    const max = Math.max(.001, ...items.map((item) => Math.abs(Number(item.shap_log_odds) || 0)));
    $("shapList").innerHTML = items.map((item) => {
      const value = Number(item.shap_log_odds) || 0;
      return '<div class="shap-row" title="Observed value: ' + escapeHtml(item.value) + '"><span class="shap-name">' +
        escapeHtml(item.feature) + '</span><span class="shap-track"><span class="shap-fill ' +
        (value < 0 ? "negative" : "") + '" style="width:' + Math.max(3, Math.abs(value) / max * 100) +
        '%"></span></span><span class="shap-value">' + (value >= 0 ? "+" : "") + number(value, 3) + "</span></div>";
    }).join("");
  }
  function renderPatterns(patterns) {
    if (!patterns.length) {
      $("patternList").innerHTML = '<p class="muted-copy">No configured structural pattern was detected for the highest-scored transaction.</p>';
      return;
    }
    $("patternList").innerHTML = patterns.map((pattern) => {
      let detail = "";
      if (pattern.pattern === "equal_value_outputs") detail = number(pattern.output_count) + " outputs of " + number(pattern.amount_sats) + " satoshis.";
      else if (pattern.pattern === "unusual_fan_out") detail = number(pattern.output_count) + " outputs; training 99th percentile: " + number(pattern.training_p99) + ".";
      else if (pattern.pattern === "unusual_fan_in") detail = number(pattern.input_count) + " inputs; training 99th percentile: " + number(pattern.training_p99) + ".";
      return '<div class="pattern-item"><strong>' + escapeHtml(pattern.pattern.replaceAll("_", " ")) +
        "</strong>" + escapeHtml(detail || "Measured by the backend.") + "</div>";
    }).join("") + '<p class="fine-print">A pattern is context, not proof of illicit activity.</p>';
  }
  function renderTransactions(items) {
    $("transactionList").innerHTML = items.length ? items.map((item) =>
      '<button class="transaction-row" type="button" data-tx="' + escapeHtml(item.txid) +
      '"><span class="mono" title="' + escapeHtml(item.txid) + '">' + escapeHtml(shorten(item.txid, 14)) +
      '</span><small>' + escapeHtml(item.direction) + " · " + percent(item.classification_probability) +
      " ↗</small></button>").join("") : '<p class="muted-copy">No observed transactions were saved.</p>';
  }
  function renderRelated(graph, focus) {
    const related = (graph.nodes || []).filter((node) => node.type === "wallet" && node.id !== "wallet:" + focus).slice(0, 12);
    $("relatedWallets").innerHTML = related.length ? related.map((node) => {
      const id = node.id.slice(7);
      return '<button class="related-row" type="button" data-wallet="' + escapeHtml(id) +
        '"><span class="mono" title="' + escapeHtml(id) + '">' + escapeHtml(shorten(id, 14)) +
        '</span><small>inspect ↗</small></button>';
    }).join("") : '<p class="muted-copy">No related addresses appear in this bounded view.</p>';
  }
  function transactionMarkup(tx) {
    return '<p class="tx-detail-id">' + escapeHtml(tx.txid) + '</p><div class="tx-detail-grid">' +
      '<div><span>OBSERVED AT</span><strong>' + escapeHtml(tx.timestamp || "—") + '</strong></div>' +
      '<div><span>TOTAL OUTPUT</span><strong>' + number(tx.total_output) + ' sats</strong></div>' +
      '<div><span>INPUTS / OUTPUTS</span><strong>' + number(tx.input_count) + ' / ' + number(tx.output_count) + '</strong></div>' +
      '<div><span>FEE</span><strong>' + number(tx.fee) + ' sats</strong></div>' +
      '<div><span>MODEL PROBABILITY</span><strong>' + percent(tx.classification_probability) + '</strong></div>' +
      '<div><span>ANOMALY SCORE</span><strong>' + number(tx.anomaly_score, 3) + '</strong></div></div>';
  }
  function renderNetwork(tx) {
    const rows = [
      ["Observed source IP", tx.src_ip || "Unavailable"],
      ["Dataset country", tx.dataset_geo_country || "Unavailable"],
      ["ASN organization", tx.src_ip_geo_asn_org || "Unavailable"],
      ["Geo data source", tx.src_ip_geo_data_source || "Unavailable"]
    ];
    $("networkContext").innerHTML = rows.map((row) => '<div class="network-row"><span>' +
      escapeHtml(row[0]) + "</span><strong>" + escapeHtml(row[1]) + "</strong></div>").join("") +
      '<p class="fine-print">An IP is a network observation, not an attribution to the spending address. City and ASN fixtures are synthetic.</p>';
  }
  async function openTransaction(txid, standalone = false, quiet = false) {
    const request = ++state.transactionRequest;
    if (standalone) {
      showTab("investigation", true);
      $("caseEmpty").hidden = true;
      $("caseContent").hidden = true;
      $("txStandalone").hidden = false;
      $("standaloneTransactionContent").innerHTML = '<p class="muted-copy">Loading transaction…</p>';
    } else {
      $("transactionDetail").hidden = false;
      $("transactionContent").innerHTML = '<p class="muted-copy">Loading transaction…</p>';
    }
    try {
      const tx = await api("/transactions/" + encodeURIComponent(txid));
      if (request !== state.transactionRequest) return;
      const target = standalone ? $("standaloneTransactionContent") : $("transactionContent");
      target.innerHTML = transactionMarkup(tx);
      if (!standalone) renderNetwork(tx);
      if (!quiet) target.scrollIntoView({behavior: "smooth", block: "nearest"});
      return tx;
    } catch (error) {
      if (request === state.transactionRequest) {
        const target = standalone ? $("standaloneTransactionContent") : $("transactionContent");
        target.innerHTML = '<p class="muted-copy">' + escapeHtml(errorMessage(error, "Transaction")) + "</p>";
      }
      throw error;
    }
  }
  function svgEl(name, attrs = {}) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, String(value)));
    return el;
  }
  function setGraphTransform() {
    $("graphViewport").setAttribute("transform", "translate(" + state.graphX + " " + state.graphY +
      ") scale(" + state.graphScale + ")");
  }
  function changeZoom(factor) {
    state.graphScale = Math.max(.55, Math.min(2.8, state.graphScale * factor));
    setGraphTransform();
  }
  function renderGraph(graph, focusWallet) {
    const svg = $("graphSvg"), viewport = $("graphViewport");
    svg.querySelectorAll("defs").forEach((node) => node.remove());
    viewport.replaceChildren();
    state.graphScale = 1; state.graphX = 0; state.graphY = 0;
    setGraphTransform();
    const defs = svgEl("defs"), marker = svgEl("marker", {id:"flowArrow",viewBox:"0 0 10 10",refX:9,refY:5,markerWidth:5,markerHeight:5,orient:"auto"});
    marker.append(svgEl("path", {d:"M 0 0 L 10 5 L 0 10 z",fill:"#86ab70"})); defs.append(marker); svg.prepend(defs);
    const focus = "wallet:" + focusWallet;
    const focusEdges = (graph.edges || []).filter((edge) => edge.source === focus || edge.target === focus);
    const txids = [...new Set(focusEdges.map((edge) => edge.source.startsWith("tx:") ? edge.source : edge.target))].slice(0, 9);
    const wallets = [...new Set((graph.edges || []).filter((edge) => txids.includes(edge.source) || txids.includes(edge.target))
      .map((edge) => edge.source.startsWith("wallet:") ? edge.source : edge.target))].filter((id) => id !== focus).slice(0, 20);
    const positions = new Map([[focus, {x:130,y:220}]]);
    txids.forEach((id, i) => positions.set(id, {x:400,y:60 + i * 320 / Math.max(1, txids.length - 1)}));
    wallets.forEach((id, i) => positions.set(id, {x:700 + ((i % 3) - 1) * 38,y:50 + i * 340 / Math.max(1, wallets.length - 1)}));
    (graph.edges || []).forEach((edge) => {
      const a = positions.get(edge.source), b = positions.get(edge.target);
      if (a && b) viewport.append(svgEl("line", {x1:a.x,y1:a.y,x2:b.x,y2:b.y,class:"graph-edge","marker-end":"url(#flowArrow)"}));
    });
    positions.forEach((pos, id) => {
      const wallet = id.startsWith("wallet:"), selected = id === focus;
      const shape = wallet ? svgEl("circle", {cx:pos.x,cy:pos.y,r:selected?20:10,class:"graph-node-wallet graph-node-click" + (selected?" focus":"")}) :
        svgEl("rect", {x:pos.x-10,y:pos.y-10,width:20,height:20,rx:3,transform:"rotate(45 " + pos.x + " " + pos.y + ")",class:"graph-node-tx graph-node-click"});
      shape.dataset.node = id;
      shape.setAttribute("tabindex", "0");
      shape.setAttribute("role", "button");
      shape.setAttribute("aria-label", (wallet ? "Investigate address " : "Inspect transaction ") + id.split(":")[1]);
      const title = svgEl("title"); title.textContent = id; shape.append(title); viewport.append(shape);
      if (selected || (!wallet && txids.length < 5)) {
        const label = svgEl("text", {x:pos.x,y:pos.y+(selected?39:30),"text-anchor":"middle",class:"graph-label"});
        label.textContent = selected ? "SELECTED ADDRESS" : shorten(id.slice(3), 6);
        viewport.append(label);
      }
    });
    if (!txids.length) {
      const label = svgEl("text", {x:450,y:220,"text-anchor":"middle",class:"graph-label"});
      label.textContent = "No transaction neighbors in this bounded view"; viewport.append(label);
    }
    $("graphMeta").textContent = number(graph.nodes?.length || 0) + " nodes · " + number(graph.edges?.length || 0) + " edges";
    $("graphSelection").textContent = "Select a node to inspect it.";
  }
  async function start() {
    $("apiUrl").value = state.api;
    await loadOverview();
    await loadAlerts(true);
  }
  $("lookupForm").addEventListener("submit", (event) => {event.preventDefault();lookup($("lookupInput").value);});
  $("featuredButton").addEventListener("click", () => openAlert("alert_00335"));
  $("tabAlerts").addEventListener("click", () => showTab("alerts"));
  $("tabInvestigation").addEventListener("click", () => showTab("investigation"));
  document.querySelector(".workspace-tabs").addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const next = event.target === $("tabAlerts") ? $("tabInvestigation") : $("tabAlerts");
    next.focus();
    next.click();
  });
  $("alertList").addEventListener("click", (event) => {
    const row = event.target.closest("[data-alert]");
    if (row) openAlert(row.dataset.alert);
  });
  $("alertList").addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      const row = event.target.closest("[data-alert]");
      if (row) {event.preventDefault();openAlert(row.dataset.alert);}
    }
  });
  document.querySelector(".filter-row").addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (!button) return;
    document.querySelectorAll(".filter").forEach((el) => el.classList.toggle("active", el === button));
    state.filter = button.dataset.filter; loadAlerts(true);
  });
  let debounce;
  $("searchInput").addEventListener("input", (event) => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {state.search = event.target.value;loadAlerts(true);}, 250);
  });
  $("sortAlerts").addEventListener("change", (event) => {
    state.sort = event.target.value;
    loadAlerts(true);
  });
  $("loadMoreButton").addEventListener("click", () => loadAlerts());
  $("transactionList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-tx]");
    if (button) openTransaction(button.dataset.tx).catch((error) => toast(errorMessage(error, "Transaction")));
  });
  $("relatedWallets").addEventListener("click", (event) => {
    const button = event.target.closest("[data-wallet]");
    if (button) openWallet(button.dataset.wallet).catch((error) => toast(errorMessage(error, "Address")));
  });
  function selectGraphNode(node) {
    if (!node) return;
    const id = node.dataset.node;
    $("graphSelection").textContent = id;
    if (id.startsWith("wallet:")) openWallet(id.slice(7)).catch((error) => toast(errorMessage(error, "Address")));
    if (id.startsWith("tx:")) openTransaction(id.slice(3)).catch((error) => toast(errorMessage(error, "Transaction")));
  }
  $("graphSvg").addEventListener("click", (event) => {
    const node = event.target.closest("[data-node]");
    if (!state.drag?.moved) selectGraphNode(node);
  });
  $("graphSvg").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const node = event.target.closest("[data-node]");
    if (node) {event.preventDefault();selectGraphNode(node);}
  });
  $("graphSvg").addEventListener("pointerdown", (event) => {
    state.drag = {x:event.clientX,y:event.clientY,baseX:state.graphX,baseY:state.graphY,moved:false};
    $("graphSvg").setPointerCapture(event.pointerId);
  });
  $("graphSvg").addEventListener("pointermove", (event) => {
    if (!state.drag) return;
    const dx = event.clientX-state.drag.x, dy = event.clientY-state.drag.y;
    if (Math.abs(dx)+Math.abs(dy)>5) state.drag.moved=true;
    if (state.drag.moved) {
      const box=$("graphSvg").getBoundingClientRect();
      state.graphX=state.drag.baseX+dx*900/box.width;
      state.graphY=state.drag.baseY+dy*440/box.height;
      setGraphTransform();
    }
  });
  $("graphSvg").addEventListener("pointerup", () => {setTimeout(() => {state.drag=null;}, 0);});
  $("graphSvg").addEventListener("wheel", (event) => {event.preventDefault();changeZoom(event.deltaY<0?1.12:1/1.12);}, {passive:false});
  $("zoomIn").addEventListener("click", () => changeZoom(1.2));
  $("zoomOut").addEventListener("click", () => changeZoom(1/1.2));
  $("zoomReset").addEventListener("click", () => {state.graphScale=1;state.graphX=0;state.graphY=0;setGraphTransform();});
  $("closeTransaction").addEventListener("click", () => {$("transactionDetail").hidden=true;});
  $("copyAddress").addEventListener("click", async () => {
    if (!state.wallet) return;
    try {await navigator.clipboard.writeText(state.wallet.wallet_id);toast("Address copied");}
    catch (_) {toast("Clipboard unavailable");}
  });
  $("settingsButton").addEventListener("click", () => $("settingsDialog").showModal());
  $("saveApi").addEventListener("click", () => {
    const value = $("apiUrl").value.trim().replace(/\/+$/, "");
    if (!/^https?:\/\//i.test(value)) {toast("Enter an http(s) URL");return;}
    state.api=value;localStorage.setItem("tracepoint-api",value);
    $("settingsDialog").close();start();
  });
  const hero = document.querySelector(".hero");
  let pointerFrame = 0;
  hero.addEventListener("pointermove", (event) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (pointerFrame) cancelAnimationFrame(pointerFrame);
    const x = event.clientX, y = event.clientY;
    pointerFrame = requestAnimationFrame(() => {
      const box = hero.getBoundingClientRect();
      hero.style.setProperty("--pointer-x", (100 * (x - box.left) / box.width).toFixed(1) + "%");
      hero.style.setProperty("--pointer-y", (100 * (y - box.top) / box.height).toFixed(1) + "%");
      pointerFrame = 0;
    });
  });
  start();
})();
