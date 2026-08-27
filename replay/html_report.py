"""Self-contained Plotly pipeline report for deterministic replay runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plotly.offline import get_plotlyjs


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>MarketStream Real Historical Replay</title>
  <style>
    :root { --ink:#172033; --muted:#667085; --line:#e4e7ec; --panel:#ffffff; --bg:#f6f8fb; --blue:#3568c0; --blue-open:#dce8fa; --gold:#b88916; --orange:#d76b27; --olive:#6e7f35; --pink:#b04d78; --critical:#9c2f3f; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    header { background:#fff; border-bottom:1px solid var(--line); padding:24px max(24px, calc((100vw - 1500px)/2)); }
    h1 { margin:0 0 5px; font-size:26px; letter-spacing:-.02em; }
    h2 { margin:0 0 14px; font-size:18px; }
    h3 { margin:0 0 8px; font-size:14px; }
    .subtitle,.muted { color:var(--muted); }
    .badge { display:inline-flex; align-items:center; border:1px solid #9bb5df; background:var(--blue-open); color:#244c8e; border-radius:999px; padding:4px 9px; font-weight:650; margin-right:7px; }
    .warning { border-color:#d7ad61; background:#fff6dd; color:#76530e; }
    main { max-width:1500px; margin:0 auto; padding:22px; }
    .grid { display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; }
    .card { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:16px; box-shadow:0 1px 2px rgba(16,24,40,.03); }
    .kpi { grid-column:span 2; min-height:95px; }
    .kpi .value { font:700 26px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace; margin-top:7px; }
    .span-12 { grid-column:span 12; } .span-8 { grid-column:span 8; } .span-4 { grid-column:span 4; }
    .controls { display:flex; flex-wrap:wrap; gap:10px; align-items:end; }
    label { display:flex; flex-direction:column; gap:4px; color:var(--muted); font-size:12px; }
    select,button,input[type=range] { border:1px solid #cfd4dc; border-radius:7px; background:#fff; color:var(--ink); padding:7px 9px; }
    button { cursor:pointer; font-weight:600; }
    input[type=range] { flex:1; min-width:260px; padding:5px; }
    #timeline { width:100%; height:720px; }
    .stepbar { display:flex; align-items:center; gap:9px; margin-bottom:14px; }
    .stepmeta { min-width:275px; font-family:ui-monospace, SFMono-Regular, Menlo, monospace; font-size:12px; }
    .pipeline { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:9px; }
    .stage { border:1px solid var(--line); border-top:3px solid var(--blue); border-radius:9px; padding:11px; min-height:210px; overflow:auto; }
    .stage:nth-child(2){border-top-color:var(--gold)} .stage:nth-child(3){border-top-color:var(--orange)} .stage:nth-child(4){border-top-color:var(--olive)} .stage:nth-child(5){border-top-color:var(--pink)}
    pre { margin:0; white-space:pre-wrap; overflow-wrap:anywhere; font:11px/1.38 ui-monospace,SFMono-Regular,Menlo,monospace; color:#344054; }
    table { width:100%; border-collapse:collapse; font-size:12px; }
    th,td { padding:8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
    th { color:var(--muted); font-weight:650; position:sticky; top:0; background:#fff; }
    .tablewrap { max-height:420px; overflow:auto; }
    .status { font-weight:750; } .TP { color:#245c9f; } .FP { color:#a4541f; } .FN { color:var(--critical); }
    .footnote { margin-top:15px; color:var(--muted); font-size:12px; }
    @media (max-width:1000px) { .kpi{grid-column:span 4}.span-8,.span-4{grid-column:span 12}.pipeline{grid-template-columns:1fr}.stage{min-height:unset} }
    @media (max-width:650px) { .kpi{grid-column:span 6} main{padding:10px} header{padding:18px 14px} }
  </style>
  <script>__PLOTLY_JS__</script>
</head>
<body data-report-version="marketstream-real-replay-html-v1">
<header>
  <div><span class="badge">REAL HISTORICAL REPLAY</span><span class="badge warning">IEX ONLY · NOT CONSOLIDATED SIP</span></div>
  <h1>MarketStream Pipeline Replay</h1>
  <div class="subtitle" id="provenance"></div>
</header>
<main>
  <section class="grid" id="kpis"></section>
  <section class="card span-12" style="margin-top:14px">
    <div class="controls">
      <label>Ticker<select id="tickerFilter"></select></label>
      <label>Cadence<select id="cadenceFilter"></select></label>
      <label>Outcome<select id="outcomeFilter"><option value="all">All</option><option value="tp">TP</option><option value="fp">FP</option><option value="fn_context">FN context</option><option value="none">No alert</option></select></label>
      <label>Interval<select id="intervalFilter"></select></label>
      <button id="resetFilters">Reset filters</button>
    </div>
  </section>
  <section class="card span-12" style="margin-top:14px">
    <h2>Market, factors, CEP score, and input volume</h2>
    <div class="muted">Window-time trend. Price uses the window summary; factor panel uses robust z-score. Alert markers are distinguished by TP/FP status.</div>
    <div id="timeline"></div>
  </section>
  <section class="card span-12" style="margin-top:14px">
    <h2>Window-by-window pipeline</h2>
    <div class="stepbar"><button id="prevStep">Previous</button><input id="stepSlider" type="range" min="0" max="0" value="0"><button id="nextStep">Next</button><div class="stepmeta" id="stepMeta"></div></div>
    <div class="pipeline">
      <div class="stage"><h3>1 · Input events</h3><pre id="stageInput"></pre></div>
      <div class="stage"><h3>2 · Quality gate</h3><pre id="stageQuality"></pre></div>
      <div class="stage"><h3>3 · Eight factors</h3><pre id="stageFactors"></pre></div>
      <div class="stage"><h3>4 · CEP state</h3><pre id="stageCep"></pre></div>
      <div class="stage"><h3>5 · Alert decision</h3><pre id="stageAlert"></pre></div>
    </div>
  </section>
  <section class="grid" style="margin-top:14px">
    <div class="card span-8"><h2>Event-level evaluation</h2><div class="tablewrap"><table><thead><tr><th>Status</th><th>Interval / event</th><th>Ticker</th><th>Expected</th><th>Detected</th><th>Direction</th><th>Detection time</th><th>Delay</th></tr></thead><tbody id="eventRows"></tbody></table></div></div>
    <div class="card span-4"><h2>Evidence and limitations</h2><pre id="evidence"></pre></div>
  </section>
  <div class="footnote">Accuracy is intentionally not reported. Precision/recall include only frozen, fully reviewed intervals. Alerts on context tickers are visible in the trace but excluded from the primary ticker's metric denominator.</div>
</main>
<script>
const report = __REPORT_JSON__;
const allSteps = __STEPS_JSON__;
const groupColors = {price:'#3568c0',activity:'#b88916',liquidity:'#d76b27',market_context:'#6e7f35',news:'#b04d78'};
const factorDash = {return_surprise:'solid',volatility_burst:'dot',relative_volume:'solid',spread_stress:'solid',quote_imbalance:'dot',signed_trade_imbalance:'dash',market_residual:'solid',news_shock:'solid'};
let visibleSteps = [];
let stepIndex = 0;
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = value => JSON.stringify(value, null, 2);
const pct = value => `${(Number(value||0)*100).toFixed(1)}%`;
function addOptions(select, values, allLabel='All') { select.innerHTML = `<option value="all">${allLabel}</option>` + values.map(v => `<option value="${esc(v)}">${esc(v)}</option>`).join(''); }
function initialize() {
  $('provenance').textContent = `Run ${report.run_id} · dataset ${report.dataset_id} · labels ${report.labels_sha256.slice(0,12)} · baseline ${report.baseline_sha256.slice(0,12)}`;
  const m=report.metrics, ci=report.bootstrap_95_ci, a=report.auxiliary;
  const cards=[['Precision',pct(m.precision),`95% CI ${pct(ci.precision[0])}–${pct(ci.precision[1])}`],['Recall',pct(m.recall),`95% CI ${pct(ci.recall[0])}–${pct(ci.recall[1])}`],['F1',pct(m.f1),`95% CI ${pct(ci.f1[0])}–${pct(ci.f1[1])}`],['TP / FP / FN',`${m.true_positives} / ${m.false_positives} / ${m.false_negatives}`,'event-level counts'],['False alerts/hour',Number(a.false_alerts_per_reviewed_ticker_hour).toFixed(3),`${a.reviewed_ticker_hours.toFixed(1)} reviewed ticker-hours`],['Traceability',pct(a.traceability_rate),`${report.counts.snapshots.toLocaleString()} factor windows`]];
  $('kpis').innerHTML=cards.map(c=>`<div class="card kpi"><div class="muted">${c[0]}</div><div class="value">${c[1]}</div><div class="muted">${c[2]}</div></div>`).join('');
  addOptions($('tickerFilter'),[...new Set(allSteps.map(s=>s.ticker))].sort());
  addOptions($('cadenceFilter'),[...new Set(allSteps.map(s=>s.cadence))].sort());
  addOptions($('intervalFilter'),[...new Set(allSteps.map(s=>s.interval_id))].sort());
  ['tickerFilter','cadenceFilter','outcomeFilter','intervalFilter'].forEach(id=>$(id).addEventListener('change',applyFilters));
  $('resetFilters').onclick=()=>{['tickerFilter','cadenceFilter','outcomeFilter','intervalFilter'].forEach(id=>$(id).value='all');applyFilters();};
  $('stepSlider').oninput=e=>{stepIndex=Number(e.target.value);renderStep();};
  $('prevStep').onclick=()=>{stepIndex=Math.max(0,stepIndex-1);$('stepSlider').value=stepIndex;renderStep();};
  $('nextStep').onclick=()=>{stepIndex=Math.min(visibleSteps.length-1,stepIndex+1);$('stepSlider').value=stepIndex;renderStep();};
  renderEventTable();
  $('evidence').textContent=pretty({data_kind:report.data_kind,coverage:report.coverage,detector_version:report.detector_version,reviewed_intervals:report.counts.reviewed_intervals,quality_good_rate:report.auxiliary.quality_good_rate,pattern_agreement:report.auxiliary.pattern_agreement,accuracy_reported:false});
  applyFilters();
}
function applyFilters(){
  const t=$('tickerFilter').value,c=$('cadenceFilter').value,o=$('outcomeFilter').value,i=$('intervalFilter').value;
  visibleSteps=allSteps.filter(s=>(t==='all'||s.ticker===t)&&(c==='all'||s.cadence===c)&&(o==='all'||s.match_status===o)&&(i==='all'||s.interval_id===i));
  stepIndex=0;$('stepSlider').max=Math.max(0,visibleSteps.length-1);$('stepSlider').value=0;
  renderTimeline();renderStep();
}
function renderTimeline(){
  const x=visibleSteps.map(s=>s.event_time);
  const price=visibleSteps.map(s=>s.legacy_features?.avg_close ?? s.input_summary?.last_price ?? null);
  const bid=visibleSteps.map(s=>s.input_summary?.bid_price ?? null), ask=visibleSteps.map(s=>s.input_summary?.ask_price ?? null);
  const volume=visibleSteps.map(s=>(s.input_summary?.trade_volume||0)+(s.input_summary?.bar_volume||0));
  const score=visibleSteps.map(s=>s.detection.score);
  const traces=[
    {x,y:price,name:'Window price',mode:'lines',line:{color:'#172033',width:1.7},yaxis:'y'},
    {x,y:bid,name:'Bid',mode:'lines',line:{color:'#3568c0',width:1,dash:'dot'},yaxis:'y'},
    {x,y:ask,name:'Ask',mode:'lines',line:{color:'#d76b27',width:1,dash:'dot'},yaxis:'y'},
    {x,y:volume,name:'Input volume',type:'bar',marker:{color:'#dce8fa',line:{color:'#3568c0',width:.5}},yaxis:'y4'},
    {x,y:score,name:'CEP score',mode:'lines',line:{color:'#b04d78',width:1.5},yaxis:'y3'}
  ];
  const factors=['return_surprise','volatility_burst','relative_volume','spread_stress','quote_imbalance','signed_trade_imbalance','market_residual','news_shock'];
  factors.forEach(name=>{const first=visibleSteps.find(s=>s.factor_states?.[name]);const group=first?.factor_states?.[name]?.group||'price';traces.push({x,y:visibleSteps.map(s=>s.factor_states?.[name]?.robust_z ?? null),name,mode:'lines',line:{color:groupColors[group],width:1.2,dash:factorDash[name]},yaxis:'y2',visible:'legendonly'});});
  const alerts=visibleSteps.filter(s=>s.detection.is_alert);
  traces.push({x:alerts.map(s=>s.event_time),y:alerts.map(s=>s.legacy_features?.avg_close ?? s.input_summary?.last_price ?? null),name:'Alerts',mode:'markers',marker:{size:9,color:alerts.map(s=>s.match_status==='tp'?'#3568c0':'#d76b27'),symbol:alerts.map(s=>s.match_status==='tp'?'diamond':'x')},text:alerts.map(s=>`${s.match_status.toUpperCase()} · ${s.detection.patterns.filter(p=>p.status==='completed').map(p=>p.name).join(', ')}`),hovertemplate:'%{x}<br>%{text}<extra></extra>',yaxis:'y'});
  const news=visibleSteps.filter(s=>(s.input_summary?.news_count||0)>0);
  traces.push({x:news.map(s=>s.event_time),y:news.map(s=>s.legacy_features?.avg_close ?? s.input_summary?.last_price ?? null),name:'News',mode:'markers',marker:{size:10,color:'#6e7f35',symbol:'triangle-up'},text:news.map(s=>(s.input_summary?.news_headlines||[]).join('<br>')),hovertemplate:'%{x}<br>%{text}<extra></extra>',yaxis:'y'});
  const visibleIntervalIds=new Set(visibleSteps.map(s=>s.interval_id));
  const shapes=report.intervals.filter(i=>visibleIntervalIds.has(i.interval_id)).map(i=>({type:'rect',xref:'x',yref:'paper',x0:i.started_at,x1:i.ended_at,y0:0,y1:1,fillcolor:i.kind==='anomaly'?'rgba(53,104,192,.08)':'rgba(102,112,133,.05)',line:{color:i.kind==='anomaly'?'rgba(53,104,192,.28)':'rgba(102,112,133,.18)',width:1},layer:'below',label:{text:i.kind==='anomaly'?'Ground truth':'Normal control',font:{size:9,color:'#667085'}}}));
  const layout={height:720,margin:{l:58,r:35,t:18,b:45},paper_bgcolor:'#fff',plot_bgcolor:'#fff',hovermode:'x unified',legend:{orientation:'h',y:1.08},shapes,xaxis:{gridcolor:'#eef0f3'},yaxis:{domain:[.74,1],title:'Price',gridcolor:'#eef0f3'},yaxis2:{domain:[.40,.68],title:'Robust z',gridcolor:'#eef0f3'},yaxis3:{domain:[.20,.34],title:'CEP score',gridcolor:'#eef0f3'},yaxis4:{domain:[0,.14],title:'Volume',gridcolor:'#eef0f3'},bargap:.1};
  Plotly.react('timeline',traces,layout,{responsive:true,displaylogo:false});
}
function renderStep(){
  if(!visibleSteps.length){$('stepMeta').textContent='No windows match the filters';['stageInput','stageQuality','stageFactors','stageCep','stageAlert'].forEach(id=>$(id).textContent='—');return;}
  const s=visibleSteps[Math.min(stepIndex,visibleSteps.length-1)],d=s.detection;
  $('stepMeta').textContent=`${stepIndex+1}/${visibleSteps.length} · ${s.event_time} · ${s.ticker} ${s.cadence}`;
  $('stageInput').textContent=pretty({...s.input_summary,source_event_ids:s.source_event_ids.slice(0,12),source_ids_shown:Math.min(12,s.source_event_ids.length)});
  $('stageQuality').textContent=pretty({warmup_status:s.warmup_status,baseline_version:s.baseline_version,data_quality:s.data_quality});
  const factorRows={};Object.keys(s.factor_values).forEach(name=>factorRows[name]={value:s.factor_values[name],state:s.factor_states[name]?.state,robust_z:s.factor_states[name]?.robust_z,threshold:s.factor_states[name]?.threshold,extreme_threshold:s.factor_states[name]?.extreme_threshold});$('stageFactors').textContent=pretty(factorRows);
  $('stageCep').textContent=pretty({atomic_events:d.atomic_events,patterns:d.patterns,factor_evidence:d.factor_evidence});
  $('stageAlert').textContent=pretty({is_alert:d.is_alert,score:d.score,severity:d.severity,direction:d.direction,match_status:s.match_status,explanation:d.explanation,dedupe_key:d.dedupe_key});
}
function renderEventTable(){
  $('eventRows').innerHTML=report.events.map(e=>`<tr><td class="status ${e.status}">${esc(e.status)}</td><td>${esc(e.interval_id||'')}<br><span class="muted">${esc(e.event_id||'')}</span></td><td>${esc(e.ticker)}</td><td>${esc(e.expected_pattern||'—')}</td><td>${esc(e.detected_pattern||'—')}</td><td>${esc(e.direction||'—')}</td><td>${esc(e.detected_at||'—')}</td><td>${e.delay_seconds==null?'—':esc(Number(e.delay_seconds).toFixed(1)+'s')}</td></tr>`).join('');
}
initialize(); window.__MARKETSTREAM_REPORT_READY__=true;
</script>
</body></html>"""


def _safe_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str).replace("</", "<\\/")


def write_replay_html(path: Path, report: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    html = (
        HTML_TEMPLATE.replace("__PLOTLY_JS__", get_plotlyjs())
        .replace("__REPORT_JSON__", _safe_json(report))
        .replace("__STEPS_JSON__", _safe_json(steps))
    )
    path.write_text(html)
