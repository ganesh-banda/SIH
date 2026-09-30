(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = {api: localStorage.getItem("tracepoint-api") || "http://127.0.0.1:8000",
    alerts: [], offset: 0, limit: 40, filter: "all", search: "", selected: null,
    more: true, request: 0, caseRequest: 0};
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const num = (value, digits=0) => Number.isFinite(Number(value))
    ? Number(value).toLocaleString(undefined,{minimumFractionDigits:digits,maximumFractionDigits:digits}) : "—";
  const pct = (value, digits=1) => value == null ? "—" : `${num(100*Number(value),digits)}%`;
  const short = (text, count=12) => String(text ?? "").length>count*2
    ? String(text).slice(0,count)+"…"+String(text).slice(-count) : String(text ?? "");
  const showToast = (message) => {const el=$("toast");el.textContent=message;el.classList.add("visible");
    clearTimeout(showToast.timer);showToast.timer=setTimeout(()=>el.classList.remove("visible"),2600)};
  async function get(path) {
    const controller = new AbortController();
    const timer = setTimeout(()=>controller.abort(),12000);
    try {
      const response=await fetch(state.api+path,{signal:controller.signal});
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return await response.json();
    } finally { clearTimeout(timer); }
  }
  function connection(online) {
    const el=$("connection");el.className="pill "+(online?"pill-online":"pill-offline");
    el.innerHTML='<span class="status-dot"></span>'+(online?"API CONNECTED":"API OFFLINE");
  }
  async function loadOverview() {
    try {
      const [summary,health,geo,model]=await Promise.all([
        get("/dataset/summary"),get("/health"),get("/geo/status"),get("/model/summary")]);
      $("metricTransactions").textContent=num(summary.transactions);
      $("metricWallets").textContent=num(summary.wallets);
      $("metricAlerts").textContent=num(summary.alerts);
      $("metricPrAuc").textContent=num(model.test.pr_auc,3);
      $("methodPrecision").textContent=pct(model.test.precision);
      $("methodRecall").textContent=pct(model.test.recall);
      $("geoSideStatus").textContent=geo.data_source==="synthetic_fixture"
        ? "Synthetic City / ASN fixtures" : (health.components.geolite_city.ok?"Local GeoLite MMDB":"GeoLite unavailable");
      $("queueCount").textContent=num(summary.alerts);
      connection(true);
    } catch (error) {
      connection(false);
      $("geoSideStatus").textContent="Connect backend to inspect";
      $("alertList").innerHTML='<div class="queue-placeholder">The API is unavailable. Start FastAPI on port 8000, then use ⚙ to check the URL.</div>';
      showToast("Backend connection failed");
      throw error;
    }
  }
  function filterParams() {
    const params=new URLSearchParams({limit:String(state.limit),offset:String(state.offset)});
    if (state.filter==="patterns") params.set("has_pattern","true");
    if (state.filter==="seed") params.set("seed_linked","true");
    if (state.search.trim()) params.set("search",state.search.trim());
    return params;
  }
  async function loadAlerts(reset=false) {
    if (reset) {state.offset=0;state.alerts=[];state.more=true;}
    if (!state.more) return;
    const request=++state.request;
    $("alertList").innerHTML=reset?'<div class="queue-placeholder">Finding alerts…</div>':$("alertList").innerHTML;
    try {
      const batch=await get("/alerts?"+filterParams());
      if (request!==state.request) return;
      state.alerts.push(...batch);state.offset+=batch.length;
      state.more=batch.length===state.limit;
      renderAlertList();
    } catch (error) {
      $("alertList").innerHTML='<div class="queue-placeholder">Could not load the alert queue. Check the backend connection.</div>';
      showToast("Alert request failed");
    }
  }
  function renderAlertList() {
    const list=$("alertList");
    if (!state.alerts.length) {
      list.innerHTML='<div class="queue-placeholder">No alerts match this filter. Try another search or open the featured case.</div>';
    } else {
      list.innerHTML=state.alerts.map((a)=>`<button class="alert-item ${state.selected?.alert_id===a.alert_id?"selected":""}"
        type="button" data-alert="${esc(a.alert_id)}" aria-label="Open alert ${esc(a.alert_id)}">
        <span class="alert-score">${num(a.risk_score)}</span><span class="alert-info">
        <strong>${esc(short(a.wallet_id,13))}</strong>
        <small>${esc(a.alert_id)} · ${a.patterns?.length?"Pattern evidence":"Model evidence"}${a.graph_risk!=null?" · Seed context":""}</small>
        </span><span class="alert-chevron">›</span></button>`).join("");
    }
    $("queuePageLabel").textContent=state.search
      ? `${num(state.alerts.length)} matching alert${state.alerts.length===1?"":"s"} loaded`
      : `${num(state.alerts.length)} loaded · sorted by review score`;
    $("loadMoreButton").disabled=!state.more;
  }
  async function openAlert(id) {
    $("caseEmpty").hidden=true;$("caseContent").hidden=false;
    $("caseExplanation").textContent="Loading evidence…";
    const request=++state.caseRequest;
    try {
      const alert=await get("/alerts/"+encodeURIComponent(id));
      const [graph,transactions]=await Promise.all([
        get("/wallets/"+encodeURIComponent(alert.wallet_id)+"/graph?limit=40"),
        get("/wallets/"+encodeURIComponent(alert.wallet_id)+"/transactions?limit=20")]);
      if (request!==state.caseRequest) return;
      state.selected=alert;renderAlertList();
      renderCase(alert,graph,transactions);
      const first=alert.related_transactions?.[0];
      if (first) await openTransaction(first);
      location.hash="investigation";
    } catch (error) {
      $("caseExplanation").textContent="This case could not be loaded. Check the API and try again.";
      showToast("Case request failed");
    }
  }
  function renderCase(alert,graph,transactions) {
    $("caseCategory").textContent=alert.risk_category+" REVIEW";
    $("caseAlertId").textContent=alert.alert_id;
    $("copyAddress").textContent=alert.wallet_id+"  ↗";
    $("scoreValue").textContent=num(alert.risk_score);
    document.querySelector(".score-dial").style.setProperty("--progress",`${Math.max(0,Math.min(100,alert.risk_score))}%`);
    $("modelSignal").textContent=pct(alert.classification_probability);
    $("anomalySignal").textContent=num(alert.anomaly_score,3);
    $("graphSignal").textContent=alert.graph_risk==null?"No nearby seed":num(alert.graph_risk,2);
    $("caseExplanation").textContent=alert.explanation || "No explanation available.";
    renderShap(alert.model_evidence||[]);
    renderPatterns(alert.patterns||[]);
    renderGraph(graph,alert.wallet_id);
    const rel=alert.related_transactions||[];
    $("transactionList").innerHTML=rel.slice(0,8).map((txid,i)=>`<button class="transaction-row" type="button"
       data-tx="${esc(txid)}"><span class="mono">${esc(short(txid,15))}</span><small>${i===0?"TOP SIGNAL":"VIEW DETAILS"} ↗</small></button>`).join("")
       +'<div id="txDetail" class="tx-detail"><p>Choose a transaction to inspect its observed contents.</p></div>';
    $("graphMeta").textContent=`${num(graph.nodes?.length||0)} nodes · ${num(graph.edges?.length||0)} edges in bounded view`;
    $("networkContext").innerHTML='<p class="muted-copy">Loading observation metadata…</p>';
  }
  function renderShap(evidence) {
    if (!evidence.length) {$("shapList").innerHTML='<p class="muted-copy">No model contributions were saved for this case.</p>';return;}
    const max=Math.max(...evidence.map(e=>Math.abs(Number(e.shap_log_odds)||0)),.001);
    $("shapList").innerHTML=evidence.map((e)=>`<div class="shap-row" title="Observed value: ${esc(e.value)}">
      <span class="shap-name">${esc(e.feature)}</span>
      <span class="shap-track"><span class="shap-fill ${Number(e.shap_log_odds)<0?"negative":""}" style="display:block;width:${Math.max(3,Math.abs(Number(e.shap_log_odds))/max*100)}%"></span></span>
      <span class="shap-value">${Number(e.shap_log_odds)>=0?"+":""}${num(e.shap_log_odds,3)}</span></div>`).join("");
  }
  function renderPatterns(patterns) {
    if (!patterns.length) {$("patternList").innerHTML='<p class="muted-copy">No configured structural pattern was detected for the highest-scored transaction.</p>';return;}
    $("patternList").innerHTML=patterns.map((p)=>{
      if (p.pattern==="equal_value_outputs") return `<div class="evidence-chip"><strong>Equal-value outputs</strong><br>${num(p.output_count)} outputs of ${num(p.amount_sats)} satoshis.</div>`;
      if (p.pattern==="unusual_fan_out") return `<div class="evidence-chip"><strong>Unusual fan-out</strong><br>${num(p.output_count)} outputs; training 99th percentile was ${num(p.training_p99)}.</div>`;
      if (p.pattern==="unusual_fan_in") return `<div class="evidence-chip"><strong>Unusual fan-in</strong><br>${num(p.input_count)} inputs; training 99th percentile was ${num(p.training_p99)}.</div>`;
      return `<div class="evidence-chip">${esc(p.pattern)}</div>`;
    }).join("")+'<p class="muted-copy">A pattern is context, not proof of illicit activity.</p>';
  }
  async function openTransaction(txid) {
    const holder=$("txDetail");if (!holder) return;
    holder.innerHTML='<p>Loading transaction…</p>';
    try {
      const tx=await get("/transactions/"+encodeURIComponent(txid));
      holder.innerHTML=`<div class="tx-detail-grid">
        <div><span>TOTAL OUTPUT</span><strong>${num(tx.total_output)} sats</strong></div>
        <div><span>INPUTS / OUTPUTS</span><strong>${num(tx.input_count)} / ${num(tx.output_count)}</strong></div>
        <div><span>FEE</span><strong>${num(tx.fee)} sats</strong></div>
        </div><p class="mono">${esc(tx.txid)}</p>`;
      $("networkContext").innerHTML=`<div class="network-row"><span>Observed source IP</span><strong class="mono">${esc(tx.src_ip||"—")}</strong></div>
        <div class="network-row"><span>Dataset country</span><strong>${esc(tx.dataset_geo_country||"—")}</strong></div>
        <div class="network-row"><span>ASN organization</span><strong>${esc(tx.src_ip_geo_asn_org||"Unavailable")}</strong></div>
        <div class="network-row"><span>Geo source</span><strong>${esc(tx.src_ip_geo_data_source||"Unavailable")}</strong></div>
        <p class="muted-copy" style="margin-top:9px">This is a network observation. The IP is not attributed to the spending address.</p>`;
    } catch (error) {holder.innerHTML='<p>Transaction details are unavailable.</p>';}
  }
  function svgElement(name,attrs={}) {
    const el=document.createElementNS("http://www.w3.org/2000/svg",name);
    for (const [key,value] of Object.entries(attrs)) el.setAttribute(key,String(value));
    return el;
  }
  function renderGraph(graph,focusWallet) {
    const svg=$("graphSvg");svg.replaceChildren();
    const defs=svgElement("defs"),marker=svgElement("marker",{id:"arrow",viewBox:"0 0 10 10",refX:"9",refY:"5",markerWidth:"5",markerHeight:"5",orient:"auto-start-reverse"});
    marker.append(svgElement("path",{d:"M 0 0 L 10 5 L 0 10 z",fill:"#638895"}));defs.append(marker);svg.append(defs);
    const focusId="wallet:"+focusWallet;
    const relevantTx=[...new Set((graph.edges||[]).filter(e=>e.source===focusId||e.target===focusId)
      .map(e=>e.source.startsWith("tx:")?e.source:e.target))].slice(0,8);
    const relatedWallet=[...new Set((graph.edges||[]).filter(e=>relevantTx.includes(e.source)||relevantTx.includes(e.target))
      .map(e=>e.source.startsWith("wallet:")?e.source:e.target))].filter(n=>n!==focusId).slice(0,18);
    const positions=new Map([[focusId,{x:115,y:165}]]);
    relevantTx.forEach((id,i)=>positions.set(id,{x:348,y:165+(i-(relevantTx.length-1)/2)*Math.min(48,260/Math.max(1,relevantTx.length))}));
    relatedWallet.forEach((id,i)=>positions.set(id,{x:600+((i%3)-1)*32,y:42+i*246/Math.max(1,relatedWallet.length-1)}));
    for (const edge of graph.edges||[]) {
      const a=positions.get(edge.source),b=positions.get(edge.target);if (!a||!b) continue;
      svg.append(svgElement("line",{x1:a.x,y1:a.y,x2:b.x,y2:b.y,class:"graph-edge","marker-end":"url(#arrow)"}));
    }
    for (const [id,pos] of positions) {
      const wallet=id.startsWith("wallet:"),focus=id===focusId;
      const shape=wallet?svgElement("circle",{cx:pos.x,cy:pos.y,r:focus?19:8,class:"graph-node-wallet"+(focus?" focus":"")}):
        svgElement("rect",{x:pos.x-9,y:pos.y-9,width:18,height:18,rx:4,class:"graph-node-tx",transform:`rotate(45 ${pos.x} ${pos.y})`});
      const title=svgElement("title");title.textContent=id;shape.append(title);svg.append(shape);
      if (focus||(!wallet&&relevantTx.length<5)) {
        const label=svgElement("text",{x:pos.x,y:pos.y+(focus?37:25),"text-anchor":"middle",class:focus?"graph-center-label":"graph-label"});
        label.textContent=focus?"SELECTED ADDRESS":short(id.slice(3),6);svg.append(label);
      }
    }
    if (!positions.size||relevantTx.length===0) {
      const label=svgElement("text",{x:380,y:170,"text-anchor":"middle",class:"graph-label"});
      label.textContent="No observed transaction neighbors";svg.append(label);
    }
  }
  async function start() {
    $("apiUrl").value=state.api;
    try {await loadOverview();await loadAlerts(true);} catch (error) { /* Visible connection state is rendered above. */ }
  }
  $("alertList").addEventListener("click",(event)=>{
    const item=event.target.closest("[data-alert]");if(item) openAlert(item.dataset.alert);
  });
  $("transactionList").addEventListener("click",(event)=>{
    const item=event.target.closest("[data-tx]");if(item) openTransaction(item.dataset.tx);
  });
  document.querySelector(".filter-row").addEventListener("click",(event)=>{
    const button=event.target.closest("[data-filter]");if(!button) return;
    document.querySelectorAll(".filter").forEach(el=>el.classList.toggle("active",el===button));
    state.filter=button.dataset.filter;loadAlerts(true);
  });
  let debounce;
  $("searchInput").addEventListener("input",(event)=>{
    clearTimeout(debounce);debounce=setTimeout(()=>{state.search=event.target.value;loadAlerts(true)},250);
  });
  $("loadMoreButton").addEventListener("click",()=>loadAlerts(false));
  $("featuredButton").addEventListener("click",()=>openAlert("alert_00335"));
  $("copyAddress").addEventListener("click",async()=>{
    if (!state.selected) return;
    try {await navigator.clipboard.writeText(state.selected.wallet_id);showToast("Address copied");}
    catch {showToast("Clipboard unavailable");}
  });
  $("settingsButton").addEventListener("click",()=>$("settingsDialog").showModal());
  $("saveApi").addEventListener("click",()=>{
    const value=$("apiUrl").value.trim().replace(/\/+$/,"");
    if (!/^https?:\/\//i.test(value)) {showToast("Enter an http(s) URL");return;}
    state.api=value;localStorage.setItem("tracepoint-api",value);$("settingsDialog").close();start();
  });
  document.querySelectorAll(".side-link").forEach(link=>link.addEventListener("click",()=>{
    document.querySelectorAll(".side-link").forEach(el=>el.classList.toggle("active",el===link));
  }));
  start();
})();
