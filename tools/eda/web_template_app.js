/* 온터 단지 복지 분석 — 페이지 동작(build_web.py가 web_template.html의 __APP__ 자리에 넣는다) */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
const SUPPLY = ["국민임대", "영구임대", "공공임대(50년)", "복합 공급", "행복주택"];
const SEQS = [[0, "#cfe0f7"], [0.5, "#4a8fe0"], [1, "#123a73"]];
const DIVS = [[0, "#184f95"], [0.25, "#6da7ec"], [0.5, "#eeeeea"], [0.75, "#ee8f8e"], [1, "#a82a29"]];
const shown = new Set();
const redraws = new Map();     // div id -> 다시 그리는 함수(테마 바뀔 때)
let current = null;
const CXI = new Map(D.cx.map((c, i) => [c.id, i]));
const VAR = Object.fromEntries(D.vars.map(v => [v.k, v]));
const BRANCHES = [...new Set(D.cx.map(c => c.br))].sort();
const store = { get(k, d) { try { const v = localStorage.getItem("onter." + k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("onter." + k, JSON.stringify(v)); } catch (e) {} } };

/* ── 수치 도우미 ── */
function fmtv(v, fmt, unit) {
  if (v == null || Number.isNaN(v)) return "자료 없음";
  const d = /\.(\d)f/.exec(fmt || ""); const n = d ? +d[1] : 0;
  const s = Number(v).toLocaleString("ko-KR", { minimumFractionDigits: n, maximumFractionDigits: n });
  return unit === "%" ? s + "%" : unit ? s + " " + unit : s;
}
const fv = (k, i) => fmtv(VAR[k].v[i], VAR[k].fmt, VAR[k].unit);
function median(a) { const b = a.filter(x => x != null && !Number.isNaN(x)).sort((x, y) => x - y); if (!b.length) return null; const m = b.length >> 1; return b.length % 2 ? b[m] : (b[m - 1] + b[m]) / 2; }
function pctRank(k, i) { const v = VAR[k].v[i]; if (v == null) return null; const a = VAR[k].v.filter(x => x != null); return a.filter(x => x < v).length / Math.max(1, a.length - 1); }
function ranks(a) { const idx = a.map((v, i) => [v, i]).sort((x, y) => x[0] - y[0]); const r = new Array(a.length); let i = 0;
  while (i < idx.length) { let j = i; while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++; const rr = (i + j) / 2 + 1; for (let k = i; k <= j; k++) r[idx[k][1]] = rr; i = j + 1; } return r; }
function spearman(x, y) { const p = x.map((v, i) => [v, y[i]]).filter(([a, b]) => a != null && b != null); if (p.length < 5) return null;
  const rx = ranks(p.map(q => q[0])), ry = ranks(p.map(q => q[1])); const n = p.length, mx = rx.reduce((a, b) => a + b) / n, my = ry.reduce((a, b) => a + b) / n;
  let sxy = 0, sx = 0, sy = 0; for (let i = 0; i < n; i++) { sxy += (rx[i] - mx) * (ry[i] - my); sx += (rx[i] - mx) ** 2; sy += (ry[i] - my) ** 2; }
  return { r: sxy / Math.sqrt(sx * sy), n }; }

/* ── 테마·Plotly ── */
function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function baseLayout() {
  const ink = tok("--ink"), muted = tok("--muted"), line = tok("--line"), surf = tok("--surface");
  const axis = { gridcolor: line, zerolinecolor: line, linecolor: line, tickfont: { color: muted }, title: { font: { color: muted, size: 12 } }, automargin: true };
  return { paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", colorway: CAT, font: { family: tok("--f-body"), color: ink, size: 12 }, margin: { l: 56, r: 16, t: 12, b: 50 },
    hoverlabel: { bgcolor: surf, bordercolor: line, font: { color: ink, family: tok("--f-body"), size: 12 } }, legend: { font: { color: muted } }, xaxis: axis, yaxis: axis, _ink: ink, _muted: muted };
}
function merge(a, b) { const o = Array.isArray(a) ? a.slice() : { ...a };
  for (const k in b) { if (b[k] && typeof b[k] === "object" && !Array.isArray(b[k]) && a && typeof a[k] === "object" && !Array.isArray(a[k])) o[k] = merge(a[k], b[k]); else o[k] = b[k]; } return o; }
function themed(layout) {
  const base = baseLayout(); const L = merge(base, layout || {});
  for (const k of Object.keys(L)) if (/^[xy]axis\d+$/.test(k)) L[k] = merge(base.xaxis, layout[k]);
  if (L.shapes) L.shapes = L.shapes.map(s => s.line && !s.line.color ? merge(s, { line: { color: base._muted } }) : s);
  if (L.annotations) L.annotations = L.annotations.map(a => { const o = merge({ font: { color: base._ink, size: 12 }, arrowcolor: base._muted }, a);
    if (o.bg) { o.bgcolor = tok("--surface"); o.bordercolor = tok("--line"); o.borderpad = 4; } delete o.bg; return o; });
  if (L.legend && L.legend.title) L.legend.title = merge({ font: { color: base._muted } }, L.legend.title);
  delete L._ink; delete L._muted; return L;
}
function themedData(data) { const ink = tok("--ink"), muted = tok("--muted");
  return data.map(t => { const c = { ...t };
    if (c.textfont == null && (c.text || c.mode?.includes("text"))) c.textfont = { color: ink }; else if (c.textfont && !c.textfont.color) c.textfont = { ...c.textfont, color: ink };
    if (c.line?.color === "#222") c.line = { ...c.line, color: ink };
    if (c.type === "heatmap" || c.marker?.colorbar) { const cb = merge({ tickfont: { color: muted }, title: { font: { color: muted } }, outlinewidth: 0 }, (c.type === "heatmap" ? c.colorbar : c.marker.colorbar) || {});
      if (c.type === "heatmap") c.colorbar = cb; else c.marker = { ...c.marker, colorbar: cb }; }
    return c; }); }
const PCFG = { responsive: true, displaylogo: false, displayModeBar: false };
function plot(div, dataFn, layoutFn, cfg) {   // dataFn/layoutFn은 테마가 바뀌면 다시 불린다
  if (typeof div === "string") div = document.getElementById(div);
  if (!div) return;
  const go = () => Plotly.react(div, themedData(dataFn()), themed(layoutFn()), { ...PCFG, ...(cfg || {}) });
  go(); redraws.set(div.id, go); return div;
}
function drawFig(div, key) { plot(div, () => D.figs[key].data, () => D.figs[key].layout); div.dataset.done = "1"; }
function retheme() { redraws.forEach(f => { try { f(); } catch (e) {} }); }
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", retheme);
new MutationObserver(retheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

/* ── 공통 입력 요소 ── */
function varOptions(sel) {
  const groups = [...new Set(D.vars.map(v => v.grp))];
  return groups.map(g => `<optgroup label="${esc(g)}">${D.vars.filter(v => v.grp === g).map(v => `<option value="${v.k}"${v.k === sel ? " selected" : ""}>${esc(v.label)}</option>`).join("")}</optgroup>`).join("");
}
const branchOptions = (sel) => `<option value="">전체 지사</option>` + BRANCHES.map(b => `<option${b === sel ? " selected" : ""}>${esc(b)}</option>`).join("");
const supplyOptions = (sel) => `<option value="">전체 공급유형</option>` + SUPPLY.map(b => `<option${b === sel ? " selected" : ""}>${esc(b)}</option>`).join("");
const cxDatalist = id => `<datalist id="${id}">${D.cx.map(c => `<option value="${esc(c.n)}">${esc(c.br)}</option>`).join("")}</datalist>`;
const findCx = name => D.cx.findIndex(c => c.n === String(name).trim());
const outlineTrace = (o) => ({ type: "scatter", mode: "lines", x: o[0], y: o[1], fill: "toself", fillcolor: tok("--land"), line: { color: tok("--landline"), width: 0.8 }, hoverinfo: "skip", showlegend: false });
const mapLayout = () => ({ margin: { l: 4, r: 4, t: 4, b: 4 }, dragmode: "pan", hovermode: "closest", showlegend: false,
  xaxis: { visible: false, range: [124.4, 131.1] }, yaxis: { visible: false, range: [33.0, 38.75], scaleanchor: "x", scaleratio: 1.24 } });
const MAPCFG = { scrollZoom: true, displayModeBar: true, modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "toImage"] };
const OUTLINE = D.sections.find(s => s.id === "explorer").outline;

/* ── 탭 구조 ── */
const tabs = $("#tabs"), main = $("#main");
const BUILDERS = { overview: buildOverview, explorer: buildExplorer, compare: buildCompare, varx: buildVarx, progdict: buildProgdict, voice: buildVoice, branch: buildBranch, table: buildTable };
const ONSHOW = {};
const TAGS = { "p-bg": "배경", "p-eld": "문제 1 · 근거", "p-hd": "문제 1 · 근거", "p-demand": "문제 1 · 근거", "p-explain": "문제 1 · 근거", "p-size": "문제 2 · 기준", "p-branch": "문제 2 · 기준",
  "p-need": "문제 2 · 기준", "p-unit": "문제 3 · 도달", "p-month": "문제 3 · 도달", "p-names": "문제 4 · 학습", "p-fields": "문제 4 · 학습", "p-sat": "문제 4 · 학습", "p-gap": "기회" };
function cardEl(c) {
  const cd = document.createElement("article"); cd.className = "card" + (c.wide ? " wide" : ""); cd.id = c.id;
  const tag = TAGS[c.id];
  cd.innerHTML = (tag ? `<div class="tag">${tag}</div>` : "") + `<h3>${esc(c.title)}</h3>` + (c.body ? `<p>${esc(c.body)}</p>` : "");
  if (c.figs && c.figs.length) { const fs = document.createElement("div"); fs.className = "figs";
    for (const k of c.figs) { const p = document.createElement("div"); p.className = "plot"; p.id = "plot-" + k; p.dataset.fig = k;
      p.style.height = (c.height || (c.figs.length > 1 ? 360 : 400)) + "px"; p.setAttribute("role", "img"); p.setAttribute("aria-label", c.title); fs.appendChild(p); }
    cd.appendChild(fs); }
  if (c.html) { const h = document.createElement("div"); h.innerHTML = c.html; cd.appendChild(h); }
  if (c.note) { const n = document.createElement("div"); n.className = "note"; n.textContent = c.note; cd.appendChild(n); }
  return cd;
}
function initPage() {
for (const s of D.sections) {
  const b = document.createElement("button"); b.textContent = s.label; b.role = "tab"; b.id = "tab-" + s.id; b.setAttribute("aria-controls", s.id);
  b.addEventListener("click", () => show(s.id, true)); tabs.appendChild(b);
  const el = document.createElement("section"); el.id = s.id; el.role = "tabpanel"; el.hidden = true; el.setAttribute("aria-labelledby", b.id);
  el.innerHTML = `<div class="sec-head"><h2>${esc(s.title)}</h2>${s.lead ? `<p>${esc(s.lead)}</p>` : ""}</div>`;
  if (BUILDERS[s.id]) el.appendChild(BUILDERS[s.id](s));
  else if (s.html) { const d = document.createElement("div"); d.innerHTML = s.html; el.appendChild(d); }
  if (s.id === "notes") el.appendChild(buildNotesExtra());
  if (s.cards && s.cards.length) { const g = document.createElement("div"); g.className = "grid"; for (const c of s.cards) g.appendChild(cardEl(c)); el.appendChild(g); }
  main.appendChild(el);
}
$("#foot").textContent = `자료 기준 ${D.built} · 차트에 마우스를 올리면 값이, 범례를 누르면 계열 켜고 끄기가 됩니다. 모든 관계는 상관이며 원인을 뜻하지 않습니다.`;
document.addEventListener("click", e => { const t = e.target.closest("[data-goto-cx]"); if (t) { e.preventDefault(); openCx(+t.dataset.gotoCx); } });
}

function show(id, push) {
  for (const s of D.sections) { document.getElementById(s.id).hidden = s.id !== id; document.getElementById("tab-" + s.id).setAttribute("aria-selected", String(s.id === id)); }
  const sec = document.getElementById(id);
  requestAnimationFrame(() => {
    sec.querySelectorAll(".plot[data-fig]").forEach(p => { if (!p.dataset.done) drawFig(p, p.dataset.fig); else Plotly.Plots.resize(p); });
    shown.add(id); if (ONSHOW[id]) ONSHOW[id]();
  });
  if (push) { try { history.replaceState(null, "", "#" + id); } catch (e) {} window.scrollTo({ top: 0 }); }
}
function openCx(i) { show("explorer", true); select(i); }

/* ═════ 한눈에 보기 ═════ */
function buildOverview(s) {
  const w = document.createElement("div");
  const quick = [["explorer", "단지 지도·탐색기", "단지 하나를 골라 추세·주민·접근성·검토 후보를 봅니다"], ["compare", "단지 비교", "최대 4곳을 나란히 놓고 비교합니다"],
    ["varx", "변수 탐색기", `${D.vars.length}개 지표 중 두 개를 골라 관계를 봅니다`], ["progdict", "프로그램 사전", `표준 프로그램 ${D.prog.length}종을 하나씩 살펴봅니다`],
    ["voice", "주민 목소리", "주민이 원한다고 답한 서비스와 실제 공급을 비교합니다"], ["branch", "지사 비교", "13개 지사를 같은 지표로 나란히 봅니다"]];
  w.innerHTML = `<div class="stats">${s.stats.map(t => `<div class="stat"><b>${esc(t.v)}<small>${esc(t.u)}</small></b><div>${esc(t.d)}</div></div>`).join("")}</div>
  <div class="probs">${s.problems.map(p => `<div class="prob"><div class="k">문제 ${p.k}</div><h3>${esc(p.name)}</h3><p class="q">${esc(p.q)}</p><p>${esc(p.a)}</p><button type="button" data-go="${p.go}">근거 차트 보기 →</button></div>`).join("")}</div>
  <div class="callout"><b>기회</b><p>${esc(s.opportunity)}</p><button type="button" data-tab="explorer">단지별로 보기</button></div>
  <h3 class="sub">직접 살펴보기</h3><div class="quick">${quick.map(q => `<button type="button" class="qk" data-tab="${q[0]}"><b>${esc(q[1])}</b><span>${esc(q[2])}</span></button>`).join("")}</div>`;
  w.addEventListener("click", e => {
    const go = e.target.closest("[data-go]"), tb = e.target.closest("[data-tab]");
    if (go) { show("problem", true); const c = document.getElementById(go.dataset.go); if (c) { setTimeout(() => c.scrollIntoView({ behavior: "smooth", block: "start" }), 60); c.classList.add("flash"); setTimeout(() => c.classList.remove("flash"), 1400); } }
    if (tb) show(tb.dataset.tab, true);
  });
  return w;
}

/* ═════ 단지 지도·탐색기 ═════ */
let PTAB = "sum";
function buildExplorer() {
  const w = document.createElement("div");
  w.innerHTML = `<div class="ex-controls">
      <label for="metric">지도 색으로 볼 지표<select id="metric">${varOptions("hd")}</select></label>
      <label for="mapBr">지사<select id="mapBr">${branchOptions("")}</select></label>
      <label for="mapSg">공급유형<select id="mapSg">${supplyOptions("")}</select></label>
      <label for="find">단지 찾기<input id="find" list="cxlist" placeholder="단지 이름 (예: 광주하남1)" autocomplete="off"></label>${cxDatalist("cxlist")}
    </div>
    <div class="ex-layout"><div><div id="map" role="img" aria-label="단지 위치 지도"></div><p class="hint" id="mapHint"></p></div><div class="profile" id="profile" aria-live="polite"></div></div>`;
  ["metric", "mapBr", "mapSg"].forEach(id => w.querySelector("#" + id).addEventListener("change", drawMap));
  const f = w.querySelector("#find");
  const go = () => { const i = findCx(f.value); if (i >= 0) select(i); };
  f.addEventListener("change", go); f.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  w.querySelector("#profile").addEventListener("click", e => {
    const b = e.target.closest("[data-cx]"); if (b) select(+b.dataset.cx);
    const t = e.target.closest("[data-ptab]"); if (t) { PTAB = t.dataset.ptab; renderProfile(); }
    const a = e.target.closest("[data-add]"); if (a) { addCompare(+a.dataset.add); a.textContent = "비교 목록에 추가됨"; }
    const pg = e.target.closest("[data-prog]"); if (pg) openProg(pg.dataset.prog);
  });
  ONSHOW.explorer = () => { if (current == null) select(CXI.get("KOH_211")); else drawMap(); };
  return w;
}
function mapFilter(i) { const br = $("#mapBr").value, sg = $("#mapSg").value; const c = D.cx[i]; return (!br || c.br === br) && (!sg || c.sg === sg); }
function drawMap() {
  const k = $("#metric").value, V = VAR[k];
  plot("map", () => {
    const idx = D.cx.map((c, i) => i).filter(i => D.cx[i].lat != null);
    const on = idx.filter(i => mapFilter(i) && V.v[i] != null), na = idx.filter(i => mapFilter(i) && V.v[i] == null), off = idx.filter(i => !mapFilter(i));
    const ok = V.v.filter(x => x != null).sort((a, b) => a - b), q = p => ok[Math.min(ok.length - 1, Math.floor(p * ok.length))];
    const sz = i => Math.max(6, Math.min(22, Math.sqrt(VAR.hh.v[i] || 100) / 2.4));
    const pt = (arr, extra) => ({ type: "scatter", mode: "markers", x: arr.map(i => D.cx[i].lon), y: arr.map(i => D.cx[i].lat), customdata: arr.map(i => [i, D.cx[i].n, D.cx[i].br, D.cx[i].sg, fmtv(V.v[i], V.fmt, V.unit)]), ...extra });
    const cur = current != null ? D.cx[current] : null;
    return [outlineTrace(OUTLINE),
      pt(off, { marker: { color: tok("--line"), size: 5 }, hovertemplate: "<b>%{customdata[1]}</b><br>%{customdata[2]} (필터 밖)<extra></extra>" }),
      pt(na, { marker: { color: tok("--muted"), size: 6, symbol: "circle-open" }, hovertemplate: "<b>%{customdata[1]}</b><br>%{customdata[2]}<br>이 지표 자료 없음<extra></extra>" }),
      pt(on, { marker: { color: on.map(i => V.v[i]), colorscale: SEQS, cmin: q(0.03), cmax: q(0.97), size: on.map(sz), line: { color: tok("--surface"), width: 0.8 }, opacity: 0.92,
        colorbar: { title: { text: V.label, side: "right", font: { size: 11 } }, thickness: 10, len: 0.6 } },
        hovertemplate: "<b>%{customdata[1]}</b><br>%{customdata[2]} · %{customdata[3]}<br>" + esc(V.label) + ": %{customdata[4]}<extra></extra>" }),
      { type: "scatter", mode: "markers", x: cur ? [cur.lon] : [], y: cur ? [cur.lat] : [], marker: { size: 26, color: "rgba(0,0,0,0)", line: { color: tok("--alert"), width: 3 } }, hoverinfo: "skip" }];
  }, mapLayout, MAPCFG);
  const div = $("#map");
  if (!div._bound) { div.on("plotly_click", ev => { const p = ev.points.find(p => p.customdata && p.customdata[0] != null); if (p) select(p.customdata[0]); }); div._bound = true; }
  const n = D.cx.filter((c, i) => mapFilter(i)).length;
  $("#mapHint").textContent = `${n}개 단지 표시 · ${V.label}${V.note ? " (" + V.note + ")" : ""} · 점 크기는 세대수 · 휠로 확대, 끌어서 이동`;
}
function select(i) { current = i; $("#find").value = D.cx[i].n; renderProfile(); if (shown.has("explorer")) drawMap(); }
const TILEK = ["hh", "age", "p60", "hd", "comm", "rich", "months", "gap", "sat", "satw"];
function tiles(i, keys) {
  return keys.map(k => { const V = VAR[k], pr = pctRank(k, i);
    return `<div class="tile"><div class="l">${esc(V.label)}</div><div class="v">${esc(fv(k, i))}</div>${pr != null ? `<div class="bar"><i style="width:${(pr * 100).toFixed(0)}%"></i><em style="left:50%"></em></div><div class="pr">전체 중 백분위 ${(pr * 100).toFixed(0)} · 중앙값 ${esc(fmtv(median(V.v), V.fmt, V.unit))}</div>` : ""}</div>`; }).join("");
}
function renderProfile() {
  const i = current, c = D.cx[i];
  const ptabs = [["sum", "요약"], ["trend", "추세"], ["pop", "주민"], ["acc", "생활 접근성"], ["prog", "프로그램"], ["cand", "검토 후보"]];
  let body = "";
  if (PTAB === "sum") body = `<div class="tiles">${tiles(i, TILEK)}</div>
      <h4>운영 현황 <small>2025년</small></h4><div class="tiles">${tiles(i, ["gov", "tbm", "mou", "job"])}</div>
      <h4>필요·공급 위치</h4><p class="small">필요 지수 백분위 ${esc(fv("need", i))}, 공급 지수 백분위 ${esc(fv("supply", i))}. ${VAR.need.v[i] >= 66.7 && VAR.supply.v[i] <= 33.3 ? "<b class='alert'>필요 상위·공급 하위 단지입니다.</b>" : ""}</p>`;
  if (PTAB === "trend") body = `<h4>홈닥터 지원 강도 <small>100세대당 월, 회색은 전체 단지 중앙값</small></h4><div class="plot sm" id="pf-hd"></div>
      <h4>주민 대상 프로그램 기록 <small>월별 건수, 회색 선은 전체 중앙값</small></h4><div class="plot sm" id="pf-cm"></div>`;
  if (PTAB === "pop") body = D.pyr.v[i] ? `<h4>연령·성별 주민 수 <small>LH 단지별 연령대별 성별 정보</small></h4><div class="plot" id="pf-pyr" style="height:380px"></div><div class="tiles">${tiles(i, ["pop", "p60", "p80", "p20", "pf"])}</div>` : `<p class="empty">인구 자료가 없습니다.</p>`;
  if (PTAB === "acc") body = `<h4>가장 가까운 시설까지 거리 <small>점: 이 단지, 막대: 전체 단지 사분위(중앙값 표시)</small></h4><div class="plot" id="pf-acc" style="height:520px"></div>`;
  if (PTAB === "prog") { const maxTop = Math.max(1, ...c.top.map(t => t[1]));
    body = `<h4>이 단지가 운영한 프로그램 <small>상위 ${c.top.length}개 / 전체 ${c.ntypes}종, 누르면 사전으로</small></h4>` + (c.top.length ? `<ul class="plist">${c.top.map(t => `<li><button type="button" class="lnk" data-prog="${esc(t[0])}">${esc(t[0])}</button><span><span class="pb"><i style="width:${(t[1] / maxTop * 100).toFixed(0)}%"></i></span><span class="pv">${t[1]}건</span></span></li>`).join("")}</ul>` : `<p class="empty">커뮤니티 활동 기록이 없습니다.</p>`)
      + `<div class="tiles" style="margin-top:14px">${tiles(i, ["eld", "part", "partner", "repeat", "fam_F04", "fam_F10", "fam_F07", "fam_F02"])}</div>`; }
  if (PTAB === "cand") { const cs = D.cand[i] || []; const pn = id => (D.prog.find(p => p.id === id) || {}).name || id;
    body = `<p class="small">아직 운영하지 않은 프로그램을 세 가지 이웃 신호(주민 구성이 비슷한 단지 10곳, 같은 공급유형·규모 단지, 프로그램 구성이 비슷한 단지 8곳의 운영 비율)의 평균으로 줄 세웠습니다. <b>시연용 규칙 점수</b>이며 현장 확인이 필요합니다.</p>`
      + (cs.length ? `<ol class="cand">${cs.map(r => `<li><div class="ch"><button type="button" class="lnk" data-prog="${esc(pn(r[0]))}">${esc(pn(r[0]))}</button><span class="sc">${(r[1] * 100).toFixed(0)}점</span></div>
        <div class="why">${r[2] != null ? `<span>주민 구성 비슷한 단지 ${(r[2] * 10).toFixed(0)}/10곳</span>` : ""}<span>같은 유형·규모 ${(r[3] * 100).toFixed(0)}%</span><span>프로그램 구성 비슷한 단지 ${(r[4] * 100).toFixed(0)}%</span>
        ${(D.prog.find(q => q.id === r[0]) || {}).cases?.length ? `<span class="hl">사례집에 실행 사례 있음</span>` : ""}${r[5] ? `<span class="hl">부족한 영역 채움: ${esc(r[6])}</span>` : ""}${r[7] >= 0.12 ? `<span class="hl">다음 달에 많이 운영됨</span>` : ""}${r[8] != null ? `<span>비용 이 단지 중앙값의 ${r[8].toFixed(1)}배</span>` : ""}</div></li>`).join("")}</ol>` : `<p class="empty">후보가 없습니다(기록이 부족하거나 이미 대부분 운영).</p>`)
      + (c.nb.length ? `<h4>주민 구성이 비슷한 단지 10곳 <small>누르면 이동</small></h4><div class="chips">${c.nb.map(n => { const j = findCx(n); return `<button type="button" data-cx="${j}">${esc(n)}</button>`; }).join("")}</div>` : ""); }
  $("#profile").innerHTML = `<div class="ph"><div><h3>${esc(c.n)}</h3><div class="meta">${esc(c.br)} · ${esc(c.st)}${c.cl ? ` · 여건 유형 ${c.cl}` : ""}<br><span class="small">${esc(c.addr || "")}</span></div></div>
      <button type="button" class="btn ghost" data-add="${i}">${compareList.includes(i) ? "비교 목록에 있음" : "+ 비교에 추가"}</button></div>
    <div class="seg" role="tablist">${ptabs.map(t => `<button type="button" role="tab" data-ptab="${t[0]}" aria-selected="${PTAB === t[0]}">${t[1]}</button>`).join("")}</div>${body}`;
  if (PTAB === "trend") drawTrend(i);
  if (PTAB === "pop" && D.pyr.v[i]) drawPyr(i);
  if (PTAB === "acc") drawAcc(i);
}
function drawTrend(i) {
  plot("pf-hd", () => [{ type: "scatter", mode: "lines", x: D.ts.months, y: D.ts.hd_med, name: "전체 중앙값", line: { color: tok("--muted"), width: 1.5, dash: "dot" }, hovertemplate: "%{x} 중앙값 %{y:.1f}건<extra></extra>" },
    { type: "scatter", mode: "lines+markers", x: D.ts.months, y: D.ts.hd[i], name: D.cx[i].n, line: { color: CAT[0], width: 2.4 }, marker: { size: 4 }, connectgaps: false, hovertemplate: "%{x}<br>100세대당 %{y:.1f}건<extra></extra>" }],
    () => ({ margin: { l: 44, r: 8, t: 8, b: 30 }, showlegend: false, yaxis: { rangemode: "tozero" } }));
  plot("pf-cm", () => [{ type: "bar", x: D.ts.cmonths, y: D.ts.comm[i], marker: { color: CAT[1] }, hovertemplate: "%{x}<br>%{y}건<extra></extra>" },
    { type: "scatter", mode: "lines", x: D.ts.cmonths, y: D.ts.comm_med, line: { color: tok("--muted"), width: 1.5, dash: "dot" }, hovertemplate: "%{x} 중앙값 %{y:.1f}건<extra></extra>" }],
    () => ({ margin: { l: 44, r: 8, t: 8, b: 30 }, showlegend: false }));
}
function drawPyr(i) {
  const [m, f] = D.pyr.v[i];
  plot("pf-pyr", () => [{ type: "bar", orientation: "h", y: D.pyr.ages, x: m.map(v => -v), name: "남자", marker: { color: CAT[0] }, customdata: m, hovertemplate: "%{y} 남자 %{customdata}명<extra></extra>" },
    { type: "bar", orientation: "h", y: D.pyr.ages, x: f, name: "여자", marker: { color: CAT[1] }, hovertemplate: "%{y} 여자 %{x}명<extra></extra>" }],
    () => { const mx = Math.max(...m, ...f) * 1.1; return { barmode: "overlay", bargap: 0.15, margin: { l: 50, r: 10, t: 8, b: 40 }, legend: { orientation: "h", y: -0.12 },
      xaxis: { range: [-mx, mx], tickvals: [-mx * 0.9, -mx * 0.45, 0, mx * 0.45, mx * 0.9].map(Math.round), ticktext: [mx * 0.9, mx * 0.45, 0, mx * 0.45, mx * 0.9].map(v => Math.round(v)), title: { text: "주민 수(명)" } } }; });
}
function drawAcc(i) {
  const ks = D.vars.filter(v => v.k.startsWith("acc_")).map(v => v.k);
  plot("pf-acc", () => [{ type: "box", orientation: "h", y: ks.flatMap(k => VAR[k].v.filter(x => x != null).map(() => VAR[k].label.replace("까지 거리", ""))), x: ks.flatMap(k => VAR[k].v.filter(x => x != null)),
      marker: { color: tok("--muted") }, line: { color: tok("--muted"), width: 1 }, fillcolor: "rgba(127,127,127,.15)", boxpoints: false, hoverinfo: "skip", name: "전체 단지" },
    { type: "scatter", mode: "markers", y: ks.map(k => VAR[k].label.replace("까지 거리", "")), x: ks.map(k => VAR[k].v[i]), marker: { color: CAT[7], size: 11, line: { color: tok("--surface"), width: 1.5 } },
      customdata: ks.map(k => (pctRank(k, i) ?? 0) * 100), hovertemplate: "%{y}까지 %{x:.2f}km<br>전체 중 백분위 %{customdata:.0f} (높을수록 멂)<extra>" + esc(D.cx[i].n) + "</extra>", name: D.cx[i].n }],
    () => ({ margin: { l: 110, r: 10, t: 8, b: 40 }, showlegend: false, xaxis: { type: "log", title: { text: "거리(km, 로그)" } }, yaxis: { autorange: "reversed" } }));
}

/* ═════ 단지 비교 ═════ */
let compareList = store.get("compare", []).map(id => CXI.get(id)).filter(i => i != null);
if (!compareList.length) compareList = ["KOH_211", "KOH_212", "KOH_291", "KOH_91"].map(id => CXI.get(id)).filter(i => i != null);
function addCompare(i) { if (!compareList.includes(i)) { compareList.push(i); if (compareList.length > 4) compareList.shift(); } store.set("compare", compareList.map(j => D.cx[j].id)); if (shown.has("compare")) renderCompare(); }
const CMPK = ["hh", "age", "p60", "p80", "p20", "hd", "hd_의료지원", "hd_경제지원", "comm", "rich", "part", "eld", "months", "gap", "gov", "mou", "sat", "satw", "need", "supply", "acc_병원", "acc_노인복지관"];
function buildCompare() {
  const w = document.createElement("div");
  w.innerHTML = `<div class="ex-controls"><label for="cmpFind">단지 추가<input id="cmpFind" list="cxlist2" placeholder="단지 이름을 입력하고 Enter" autocomplete="off"></label>${cxDatalist("cxlist2")}
    <button type="button" class="btn ghost" id="cmpClear">모두 지우기</button></div><div id="cmpChips" class="chips big"></div><div id="cmpBody"></div>`;
  const f = w.querySelector("#cmpFind");
  const add = () => { const i = findCx(f.value); if (i >= 0) { addCompare(i); f.value = ""; } };
  f.addEventListener("change", add); f.addEventListener("keydown", e => { if (e.key === "Enter") add(); });
  w.querySelector("#cmpClear").addEventListener("click", () => { compareList = []; store.set("compare", []); renderCompare(); });
  w.addEventListener("click", e => { const r = e.target.closest("[data-rm]"); if (r) { compareList = compareList.filter(j => j !== +r.dataset.rm); store.set("compare", compareList.map(j => D.cx[j].id)); renderCompare(); } });
  ONSHOW.compare = renderCompare;
  return w;
}
function progSets() { if (progSets.c) return progSets.c; const s = D.cx.map(() => new Set()); D.prog.forEach((p, pi) => p.cx.forEach(([ci]) => s[ci].add(pi))); return (progSets.c = s); }
function renderCompare() {
  const L = compareList;
  $("#cmpChips").innerHTML = L.map((i, j) => `<span class="chip" style="--c:${CAT[j]}"><i></i>${esc(D.cx[i].n)}<button type="button" data-rm="${i}" aria-label="${esc(D.cx[i].n)} 빼기">×</button></span>`).join("") || `<span class="empty">비교할 단지를 추가하세요.</span>`;
  if (!L.length) { $("#cmpBody").innerHTML = ""; return; }
  const rows = CMPK.map(k => { const V = VAR[k], vals = L.map(i => V.v[i]), mx = Math.max(...vals.filter(v => v != null).map(Math.abs), 1e-9);
    return `<tr><th>${esc(V.label)}</th>${L.map((i, j) => `<td class="n"><div class="cv"><span>${esc(fv(k, i))}</span>${V.v[i] != null ? `<span class="mb"><i style="width:${(Math.abs(V.v[i]) / mx * 100).toFixed(0)}%;background:${CAT[j]}"></i></span>` : ""}</div></td>`).join("")}<td class="n muted">${esc(fmtv(median(V.v), V.fmt, V.unit))}</td></tr>`; }).join("");
  const sets = progSets(), common = [...sets[L[0]]].filter(p => L.every(i => sets[i].has(p)));
  const uniq = L.map(i => [...sets[i]].filter(p => L.every(j => j === i || !sets[j].has(p))));
  $("#cmpBody").innerHTML = `<div class="grid"><article class="card wide"><h3>지표 비교</h3><p>막대 길이는 선택한 단지끼리의 상대 크기입니다. 마지막 열은 전체 단지 중앙값입니다.</p>
    <div class="tbl"><table class="cmp"><thead><tr><th>지표</th>${L.map((i, j) => `<th class="n"><button type="button" class="lnk" data-goto-cx="${i}" style="color:${CAT[j]}">${esc(D.cx[i].n)}</button><br><small>${esc(D.cx[i].br)} · ${esc(D.cx[i].sg)}</small></th>`).join("")}<th class="n">전체 중앙값</th></tr></thead><tbody>${rows}</tbody></table></div></article>
    <article class="card"><h3>홈닥터 지원 강도 추세</h3><p>100세대당 월 지원 건수(2022~2026)</p><div class="plot" id="cmp-hd" style="height:340px"></div></article>
    <article class="card"><h3>주민 대상 프로그램 기록 추세</h3><p>월별 건수(2024~2026 상반기), 3개월 이동평균</p><div class="plot" id="cmp-cm" style="height:340px"></div></article>
    <article class="card wide"><h3>프로그램 겹침</h3><p>선택한 단지가 모두 운영한 프로그램 ${common.length}종과, 한 단지만 운영한 프로그램입니다. 누르면 프로그램 사전으로 갑니다.</p>
    <div class="ovl"><div><h4>모두 운영</h4>${common.length ? `<div class="chips">${common.map(p => `<button type="button" data-prog="${esc(D.prog[p].name)}">${esc(D.prog[p].name)}</button>`).join("")}</div>` : `<p class="empty">없음</p>`}</div>
    ${L.map((i, j) => `<div><h4 style="color:${CAT[j]}">${esc(D.cx[i].n)}만</h4>${uniq[j].length ? `<div class="chips">${uniq[j].map(p => `<button type="button" data-prog="${esc(D.prog[p].name)}">${esc(D.prog[p].name)}</button>`).join("")}</div>` : `<p class="empty">없음</p>`}</div>`).join("")}</div></article></div>`;
  $("#cmpBody").onclick = e => { const pg = e.target.closest("[data-prog]"); if (pg) openProg(pg.dataset.prog); };
  const ma = a => a.map((v, k) => { const w_ = a.slice(Math.max(0, k - 2), k + 1).filter(x => x != null); return w_.length ? w_.reduce((x, y) => x + y) / w_.length : null; });
  plot("cmp-hd", () => L.map((i, j) => ({ type: "scatter", mode: "lines", x: D.ts.months, y: D.ts.hd[i], name: D.cx[i].n, line: { color: CAT[j], width: 2 }, connectgaps: false, hovertemplate: "%{x} %{y:.1f}건<extra>" + esc(D.cx[i].n) + "</extra>" })),
    () => ({ legend: { orientation: "h", y: -0.18 }, margin: { l: 44, r: 8, t: 8, b: 40 } }));
  plot("cmp-cm", () => L.map((i, j) => ({ type: "scatter", mode: "lines", x: D.ts.cmonths, y: ma(D.ts.comm[i]), name: D.cx[i].n, line: { color: CAT[j], width: 2 }, hovertemplate: "%{x} %{y:.1f}건(3개월 평균)<extra>" + esc(D.cx[i].n) + "</extra>" })),
    () => ({ legend: { orientation: "h", y: -0.18 }, margin: { l: 44, r: 8, t: 8, b: 40 } }));
}

/* ═════ 변수 탐색기 ═════ */
function buildVarx() {
  const w = document.createElement("div");
  w.innerHTML = `<div class="ex-controls">
    <label for="vx">가로축<select id="vx">${varOptions("p60")}</select></label><label for="vy">세로축<select id="vy">${varOptions("eld")}</select></label>
    <label for="vc">색 / 묶음<select id="vc"><option value="sg">공급유형</option><option value="br">지사</option><option value="cl">여건 유형</option><option value="">없음</option></select></label>
    <label for="vbr">지사<select id="vbr">${branchOptions("")}</select></label><label for="vsg">공급유형<select id="vsg">${supplyOptions("")}</select></label>
    <label for="vmode">보기<select id="vmode"><option value="scatter">산점도</option><option value="box">묶음별 분포(세로축)</option></select></label>
    <label class="cb"><input type="checkbox" id="vlogx">가로 로그</label><label class="cb"><input type="checkbox" id="vlogy">세로 로그</label></div>
    <div class="presets"><span>예시:</span>${[["p60", "eld", "고령 비율과 어르신 프로그램"], ["hh", "comm", "규모와 세대당 프로그램"], ["hd_의료지원", "fam_F04", "의료지원과 건강 프로그램"], ["comm", "satw", "활동량과 복지 만족도"], ["age", "p60", "연식과 고령화"], ["acc_노인복지관", "rich", "복지관 거리와 프로그램 종류"]]
      .map(p => `<button type="button" data-px="${p[0]}" data-py="${p[1]}">${p[2]}</button>`).join("")}</div>
    <div class="card"><div class="stat-line" id="vstat"></div><div class="plot" id="vplot" style="height:560px"></div><div class="note" id="vnote"></div></div>`;
  w.addEventListener("change", e => { if (e.target.closest(".ex-controls")) drawVarx(); });
  w.addEventListener("click", e => { const p = e.target.closest("[data-px]"); if (p) { $("#vx").value = p.dataset.px; $("#vy").value = p.dataset.py; $("#vmode").value = "scatter"; drawVarx(); } });
  ONSHOW.varx = drawVarx;
  return w;
}
function groupOf(i, by) { const c = D.cx[i]; return by === "sg" ? c.sg : by === "br" ? c.br : by === "cl" ? (c.cl ? "유형 " + c.cl : "미분류") : "전체"; }
function drawVarx() {
  const kx = $("#vx").value, ky = $("#vy").value, by = $("#vc").value, br = $("#vbr").value, sg = $("#vsg").value, mode = $("#vmode").value;
  const X = VAR[kx], Y = VAR[ky];
  const idx = D.cx.map((c, i) => i).filter(i => (!br || D.cx[i].br === br) && (!sg || D.cx[i].sg === sg) && Y.v[i] != null && (mode === "box" || X.v[i] != null));
  const groups = [...new Set(idx.map(i => groupOf(i, by)))].sort((a, b) => by === "sg" ? SUPPLY.indexOf(a) - SUPPLY.indexOf(b) : a.localeCompare(b, "ko"));
  const col = g => by === "br" ? `hsl(${(BRANCHES.indexOf(g) * 360 / BRANCHES.length) | 0} 55% 50%)` : CAT[groups.indexOf(g) % 8];
  const s = spearman(idx.map(i => X.v[i]), idx.map(i => Y.v[i]));
  plot("vplot", () => {
    if (mode === "box") {
      const ord = groups.map(g => [g, median(idx.filter(i => groupOf(i, by) === g).map(i => Y.v[i]))]).sort((a, b) => a[1] - b[1]).map(x => x[0]);
      return ord.map(g => { const ii = idx.filter(i => groupOf(i, by) === g);
        return { type: "box", name: `${g}(${ii.length})`, y: ii.map(i => Y.v[i]), boxpoints: "all", jitter: 0.4, pointpos: 0, marker: { color: col(g), size: 5, opacity: 0.7 }, line: { width: 1.3 },
          customdata: ii.map(i => [i, D.cx[i].n, D.cx[i].br]), hovertemplate: "<b>%{customdata[1]}</b><br>%{customdata[2]}<br>" + esc(Y.label) + " %{y}<extra></extra>" }; });
    }
    return groups.map(g => { const ii = idx.filter(i => groupOf(i, by) === g);
      return { type: "scatter", mode: "markers", name: `${g}(${ii.length})`, x: ii.map(i => X.v[i]), y: ii.map(i => Y.v[i]),
        marker: { color: col(g), size: ii.map(i => Math.max(6, Math.min(18, Math.sqrt(VAR.hh.v[i] || 100) / 3))), opacity: 0.78, line: { color: tok("--surface"), width: 0.6 } },
        customdata: ii.map(i => [i, D.cx[i].n, D.cx[i].br, fv(kx, i), fv(ky, i)]),
        hovertemplate: "<b>%{customdata[1]}</b><br>%{customdata[2]}<br>" + esc(X.label) + ": %{customdata[3]}<br>" + esc(Y.label) + ": %{customdata[4]}<extra></extra>" }; });
  }, () => ({ xaxis: mode === "box" ? { tickangle: -30 } : { title: { text: X.label + (X.unit && X.unit !== "%" ? ` (${X.unit})` : X.unit === "%" ? " (%)" : "") }, type: $("#vlogx").checked ? "log" : "linear" },
    yaxis: { title: { text: Y.label + (Y.unit === "%" ? " (%)" : Y.unit ? ` (${Y.unit})` : "") }, type: $("#vlogy").checked ? "log" : "linear" },
    legend: { orientation: "h", y: -0.2 }, showlegend: mode !== "box", margin: { l: 60, r: 16, t: 10, b: 60 } }));
  const div = $("#vplot");
  if (!div._bound) { div.on("plotly_click", ev => { const p = ev.points.find(p => p.customdata); if (p) openCx(p.customdata[0]); }); div._bound = true; }
  const lab = r => Math.abs(r) < 0.1 ? "거의 없음" : Math.abs(r) < 0.3 ? "약함" : Math.abs(r) < 0.5 ? "보통" : "강함";
  $("#vstat").innerHTML = mode === "box" ? `<b>${idx.length}</b>개 단지 · 묶음별 중앙값 순으로 정렬` :
    s ? `<b>${idx.length}</b>개 단지 · 순위상관 <b>ρ = ${s.r >= 0 ? "+" : ""}${s.r.toFixed(2)}</b> (${lab(s.r)}, ${s.r >= 0 ? "같은 방향" : "반대 방향"})` : "단지 수가 적어 상관을 계산하지 않았습니다.";
  $("#vnote").textContent = [X.note, Y.note].filter(Boolean).join(" / ") + (X.note || Y.note ? " · " : "") + "상관은 원인을 뜻하지 않습니다. 점을 누르면 그 단지의 탐색기로 갑니다.";
}

/* ═════ 프로그램 사전 ═════ */
let curProg = 0;
const FAMS = [...new Set(D.prog.map(p => p.fam))];
function openProg(name) { const j = D.prog.findIndex(p => p.name === name); if (j < 0) return; show("progdict", true); curProg = j; renderProgList(); renderProg(); }
function buildProgdict() {
  const w = document.createElement("div");
  w.innerHTML = `<div class="ex-controls"><label for="pq">이름으로 찾기<input id="pq" placeholder="예: 금연, 공연, 반찬" autocomplete="off"></label>
    <label for="pf">영역<select id="pf"><option value="">전체 영역</option>${FAMS.map(f => `<option>${esc(f)}</option>`).join("")}</select></label>
    <label for="ps">정렬<select id="ps"><option value="n">기록 많은 순</option><option value="adopt">운영 단지 많은 순</option><option value="titles">이름 많은 순</option><option value="name">가나다순</option></select></label></div>
    <div class="pd-layout"><div class="plistbox" id="plist" role="listbox" aria-label="표준 프로그램 목록"></div><div id="pdetail" class="profile"></div></div>`;
  ["pq", "pf", "ps"].forEach(id => w.querySelector("#" + id).addEventListener("input", renderProgList));
  w.querySelector("#plist").addEventListener("click", e => { const b = e.target.closest("[data-pi]"); if (b) { curProg = +b.dataset.pi; renderProgList(); renderProg(); } });
  w.querySelector("#pdetail").addEventListener("click", e => { const b = e.target.closest("[data-prog]"); if (b) openProg(b.dataset.prog); });
  ONSHOW.progdict = () => { renderProgList(); renderProg(); };
  return w;
}
function renderProgList() {
  const q = $("#pq").value.trim(), f = $("#pf").value, s = $("#ps").value;
  let L = D.prog.map((p, i) => i).filter(i => (!f || D.prog[i].fam === f) && (!q || D.prog[i].name.includes(q) || D.prog[i].aliases.some(a => a.includes(q))));
  L.sort((a, b) => s === "name" ? D.prog[a].name.localeCompare(D.prog[b].name, "ko") : D.prog[b][s] - D.prog[a][s]);
  $("#plist").innerHTML = `<div class="cnt">${L.length}종</div>` + L.map(i => `<button type="button" role="option" data-pi="${i}" aria-selected="${i === curProg}"><span>${esc(D.prog[i].name)}</span><small>${esc(D.prog[i].fam)} · ${D.prog[i].n.toLocaleString()}건 · ${D.prog[i].ncx}곳</small></button>`).join("");
}
function renderProg() {
  const p = D.prog[curProg]; const won = n => n == null ? "자료 없음" : (n >= 10000 ? (n / 10000).toFixed(0) + "만 원" : Math.round(n).toLocaleString() + "원");
  const SG = Object.entries(p.by_sg).filter(([k, v]) => v != null);
  $("#pdetail").innerHTML = `<div class="tag">${esc(p.fam)}${p.rec ? "" : " · 추천 대상 아님"}</div><h3>${esc(p.name)}</h3><p class="small">${esc(p.definition)}</p>
    <div class="tiles four"><div class="tile"><div class="l">기록</div><div class="v">${p.n.toLocaleString()}건</div><div class="pr">2024 ${p.n24} · 2025 ${p.n25} · 2026 상반기 ${p.n26}</div></div>
      <div class="tile"><div class="l">운영 단지</div><div class="v">${p.ncx}곳</div><div class="pr">기록 있는 단지의 ${(p.adopt * 100).toFixed(0)}%</div></div>
      <div class="tile"><div class="l">한 번에 참여(중앙값)</div><div class="v">${p.part != null ? Math.round(p.part) + "명" : "자료 없음"}</div><div class="pr">기록된 인원 합계 기준</div></div>
      <div class="tile"><div class="l">회당 비용(추정 중앙값)</div><div class="v">${won(p.cost)}</div><div class="pr">모델 추정치, 집행액 아님</div></div></div>
    <div class="grid2"><div><h4>어느 단지가 운영했나 <small>점 크기 = 기록 수</small></h4><div class="plot" id="pd-map" style="height:420px"></div></div>
      <div><h4>언제 몰리나 <small>월별 기록 비중</small></h4><div class="plot sm" id="pd-month"></div>
      <h4>공급유형별 운영 단지 비율</h4><div class="plot sm" id="pd-sg"></div></div></div>
    <div class="grid2"><div><h4>이렇게 기록됐다 <small>서로 다른 제목 ${p.titles}가지 중 예시(건수)</small></h4><ul class="small aliases">${p.aliases.map(a => `<li>${esc(a)}</li>`).join("")}</ul>
      ${p.partners.length ? `<h4>주로 함께한 기관</h4><div class="chips static">${p.partners.map(x => `<span>${esc(x)}</span>`).join("")}</div>` : ""}
      ${p.targets.length ? `<h4>기록에 적힌 대상</h4><div class="chips static">${p.targets.map(x => `<span>${esc(x)}</span>`).join("")}</div>` : ""}
      <p class="small">운영 방식: 행사형 ${(p.evt * 100).toFixed(0)}% · 정기형 ${(p.reg * 100).toFixed(0)}%</p></div>
      <div><h4>함께 운영되는 프로그램 <small>향상도(1보다 크면 같은 단지에서 함께 나타나는 경향)</small></h4>
      <ul class="plist">${p.pairs.map(q => `<li><button type="button" class="lnk" data-prog="${esc(q[0])}">${esc(q[0])}</button><span><span class="pb"><i style="width:${Math.min(100, q[1] / 3 * 100).toFixed(0)}%"></i></span><span class="pv">${q[1].toFixed(2)} · ${q[2]}곳</span></span></li>`).join("")}</ul></div></div>
    ${(p.cases || []).length ? `<h4>비슷한 단지는 이렇게 했다 <small>주거복지사 활동 사례집(주택관리공단, 2025) ${p.cases.length}건</small></h4>${p.cases.map(c => `<div class="casecard">
      <div class="cc-h"><b>${esc(c.name)}</b> <span class="small">${esc(c.region)}</span></div>
      <dl>${[["필요", c.need], ["대상", c.target], ["협력", c.partners], ["운영", c.operation], ["성과", c.outcomes], ["시작할 때 부딪힌 문제 → 해결", c.obstacles]].filter(x => x[1]).map(x => `<dt>${x[0]}</dt><dd>${esc(x[1])}</dd>`).join("")}</dl></div>`).join("")}
      <p class="small">사례집은 우수 사례 모음이며 일부 각색이 있습니다. 그대로 옮기기보다 단지 여건에 맞춰 검토하는 참고 자료입니다.</p>` : ""}`;
  const cxs = p.cx, mx = Math.max(...cxs.map(x => x[1]));
  plot("pd-map", () => { const on = new Set(cxs.map(x => x[0])); const off = D.cx.map((c, i) => i).filter(i => !on.has(i) && D.cx[i].lat != null);
    return [outlineTrace(OUTLINE), { type: "scatter", mode: "markers", x: off.map(i => D.cx[i].lon), y: off.map(i => D.cx[i].lat), marker: { color: tok("--line"), size: 5 }, customdata: off.map(i => [i, D.cx[i].n]), hovertemplate: "%{customdata[1]}: 운영 기록 없음<extra></extra>" },
      { type: "scatter", mode: "markers", x: cxs.map(x => D.cx[x[0]].lon), y: cxs.map(x => D.cx[x[0]].lat), customdata: cxs.map(x => [x[0], D.cx[x[0]].n, x[1], D.cx[x[0]].br]),
        marker: { color: CAT[0], opacity: 0.85, size: cxs.map(x => 6 + 14 * Math.sqrt(x[1] / mx)), line: { color: tok("--surface"), width: 0.8 } }, hovertemplate: "<b>%{customdata[1]}</b><br>%{customdata[3]}<br>%{customdata[2]}건<extra></extra>" }]; }, mapLayout, MAPCFG);
  const pm = $("#pd-map"); if (!pm._bound) { pm.on("plotly_click", ev => { const q = ev.points.find(q => q.customdata); if (q) openCx(q.customdata[0]); }); pm._bound = true; }
  plot("pd-month", () => [{ type: "bar", x: [...Array(12)].map((_, k) => k + 1 + "월"), y: p.months.map(v => v * 100), marker: { color: p.months.map(v => v > 1 / 12 * 1.5 ? CAT[1] : CAT[0]) }, hovertemplate: "%{x} %{y:.1f}%<extra></extra>" }],
    () => ({ margin: { l: 40, r: 8, t: 8, b: 30 }, showlegend: false, yaxis: { title: { text: "%" } } }));
  plot("pd-sg", () => [{ type: "bar", orientation: "h", y: SG.map(x => x[0]), x: SG.map(x => x[1] * 100), marker: { color: SG.map(x => CAT[SUPPLY.indexOf(x[0]) % 8]) }, hovertemplate: "%{y} %{x:.0f}%<extra></extra>" }],
    () => ({ margin: { l: 90, r: 8, t: 8, b: 30 }, showlegend: false, xaxis: { range: [0, 100], title: { text: "운영 단지 비율(%)" } } }));
}

/* ═════ 주민 목소리 ═════ */
function buildVoice() {
  const w = document.createElement("div"); const P = D.dem.pops;
  w.innerHTML = `<div class="grid">
    <article class="card wide"><h3>주민이 원한다고 답한 것 vs 실제 프로그램</h3><p>${esc(D.sections.find(s => s.id === "problem").cards.find(c => c.id === "p-demand")?.body || "")}</p><div class="plot" id="vo-vs" style="height:420px"></div></article>
    <article class="card wide"><h3>응답자 특성별로 원하는 서비스</h3><p>해피콜 서비스 이용자 조사에서 '필요한 서비스'로 고른 비율(%, 복수 응답)입니다. 조사 대상과 묶음 기준을 바꿔 보세요.</p>
      <div class="ex-controls"><label for="vpop">조사 대상<select id="vpop">${Object.entries(P).map(([k, v]) => `<option value="${k}">${esc(v.label)} (n=${v.n})</option>`).join("")}</select></label>
      <label for="vgrp">묶음 기준<select id="vgrp"></select></label></div><div class="plot" id="vo-heat" style="height:420px"></div>
      <div class="note">자료: 2025 주택관리공단 고객만족도(해피콜) 보고서. 전국 응답으로, 공단 관리 외 단지가 포함될 수 있고 단지별 값이 아닙니다.</div></article>
    <article class="card wide"><h3>주민 의견(VOC) 범주</h3><p>해피콜 자유 응답을 보고서가 묶은 범주와 응답 수입니다. 칭찬과 요청이 섞여 있습니다.</p><div class="plot" id="vo-voc" style="height:${Math.max(380, D.voc.length * 22)}px"></div></article></div>`;
  const fillGroups = () => { const g = Object.keys(P[$("#vpop").value].groups); $("#vgrp").innerHTML = g.map(x => `<option${x === "연령" ? " selected" : ""}>${esc(x)}</option>`).join(""); };
  w.querySelector("#vpop").addEventListener("change", () => { fillGroups(); drawHeat(); });
  w.querySelector("#vgrp").addEventListener("change", drawHeat);
  ONSHOW.voice = () => { if (!$("#vgrp").options.length) fillGroups(); drawFig($("#vo-vs"), "p03c"); drawHeat();
    plot("vo-voc", () => { const v = D.voc.slice().reverse(); return [{ type: "bar", orientation: "h", y: v.map(x => x.cat.length > 34 ? x.cat.slice(0, 33) + "…" : x.cat), x: v.map(x => x.n), marker: { color: CAT[0] },
      customdata: v.map(x => [x.cat, x.tags.join(", ") || "-"]), hovertemplate: "%{customdata[0]}<br>응답 %{x}건<br>필요 태그: %{customdata[1]}<extra></extra>" }]; },
      () => ({ margin: { l: 250, r: 10, t: 8, b: 40 }, showlegend: false, xaxis: { title: { text: "응답 수" } }, yaxis: { tickfont: { size: 11 } } })); };
  return w;
}
function drawHeat() {
  const pk = $("#vpop").value, P = D.dem.pops[pk], g = P.groups[$("#vgrp").value]; if (!g) return;
  plot("vo-heat", () => [{ type: "heatmap", z: [P.overall, ...g.v], x: P.metrics, y: ["전체", ...g.subs.map((s, k) => `${s} (n=${g.n[k] ?? "-"})`)], colorscale: SEQS, zmin: 0,
    text: [P.overall, ...g.v].map(r => r.map(v => v == null ? "" : v.toFixed(0))), texttemplate: "%{text}", hovertemplate: "%{y}<br>%{x}: %{z:.1f}%<extra></extra>", colorbar: { title: { text: "%" } } }],
    () => ({ margin: { l: 130, r: 10, t: 8, b: 60 }, yaxis: { autorange: "reversed" } }));
}

/* ═════ 지사 비교 ═════ */
function buildBranch() {
  const w = document.createElement("div");
  w.innerHTML = `<div class="ex-controls"><label for="bk">지표<select id="bk">${varOptions("comm")}</select></label><label for="bsg">공급유형<select id="bsg">${supplyOptions("")}</select></label></div>
    <div class="card"><div class="plot" id="br-box" style="height:560px"></div><div class="note">지사를 중앙값 순으로 정렬. 점 하나가 단지 하나이며, 누르면 탐색기로 갑니다. 회색 점선은 전체 중앙값.</div></div>
    <div class="card" style="margin-top:18px"><h3>지사 요약</h3><div class="tbl" id="br-tbl"></div></div>`;
  w.addEventListener("change", drawBranch); ONSHOW.branch = drawBranch; return w;
}
function drawBranch() {
  const k = $("#bk").value, sg = $("#bsg").value, V = VAR[k];
  const idx = D.cx.map((c, i) => i).filter(i => V.v[i] != null && (!sg || D.cx[i].sg === sg));
  const ord = BRANCHES.map(b => [b, median(idx.filter(i => D.cx[i].br === b).map(i => V.v[i]))]).filter(x => x[1] != null).sort((a, b) => a[1] - b[1]);
  const all = median(idx.map(i => V.v[i]));
  plot("br-box", () => ord.map(([b]) => { const ii = idx.filter(i => D.cx[i].br === b);
    return { type: "box", name: b, x: ii.map(i => V.v[i]), boxpoints: "all", jitter: 0.5, pointpos: 0, orientation: "h", marker: { color: CAT[0], size: 5, opacity: 0.6 }, line: { color: CAT[0], width: 1.2 }, fillcolor: "rgba(42,120,214,.12)",
      customdata: ii.map(i => [i, D.cx[i].n, D.cx[i].sg]), hovertemplate: "<b>%{customdata[1]}</b><br>%{customdata[2]}<br>" + esc(V.label) + " %{x}<extra>" + b + "</extra>" }; }),
    () => ({ showlegend: false, margin: { l: 100, r: 16, t: 8, b: 50 }, xaxis: { title: { text: V.label + (V.unit ? ` (${V.unit})` : "") } },
      shapes: all != null ? [{ type: "line", x0: all, x1: all, y0: 0, y1: 1, yref: "paper", line: { dash: "dot", width: 1.5 } }] : [] }));
  const div = $("#br-box"); if (!div._bound) { div.on("plotly_click", ev => { const p = ev.points.find(p => p.customdata); if (p) openCx(p.customdata[0]); }); div._bound = true; }
  const cols = [["hh", "세대수 중앙값"], ["p60", "60세+ 중앙값"], ["hd", "홈닥터 중앙값"], ["comm", "프로그램 중앙값"], ["rich", "종류 중앙값"], ["sat", "만족도 중앙값"]];
  const rows = BRANCHES.map(b => { const ii = D.cx.map((c, i) => i).filter(i => D.cx[i].br === b && (!sg || D.cx[i].sg === sg));
    return [b, ii.length, ii.reduce((a, i) => a + (VAR.hh.v[i] || 0), 0), ...cols.map(([kk]) => median(ii.map(i => VAR[kk].v[i])))]; }).filter(r => r[1] > 0);
  $("#br-tbl").innerHTML = `<table class="sortable"><thead><tr><th>지사</th><th class="n">단지</th><th class="n">세대 합계</th>${cols.map(c => `<th class="n">${c[1]}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr><td>${esc(r[0])}</td><td class="n">${r[1]}</td><td class="n">${r[2].toLocaleString()}</td>${cols.map(([kk], j) => `<td class="n">${esc(fmtv(r[3 + j], VAR[kk].fmt, VAR[kk].unit))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

/* ═════ 단지 목록 ═════ */
const TCOLS = ["hh", "age", "p60", "hd", "comm", "rich", "months", "gap", "sat", "need", "supply"];
const TLAB = { hh: "세대수", age: "경과 연수", p60: "60세+ %", hd: "홈닥터/100세대", comm: "프로그램/1,000세대", rich: "프로그램 종류", months: "기록 있는 달", gap: "빠진 후보", sat: "종합만족도", need: "필요 지수", supply: "공급 지수" };
let tsort = { k: "hh", d: -1 };
function buildTable() {
  const w = document.createElement("div");
  w.innerHTML = `<div class="ex-controls"><label for="tq">이름·주소 검색<input id="tq" placeholder="예: 부산, 하남" autocomplete="off"></label><label for="tbr">지사<select id="tbr">${branchOptions("")}</select></label>
    <label for="tsg">공급유형<select id="tsg">${supplyOptions("")}</select></label><label class="cb"><input type="checkbox" id="tmis">필요 상위·공급 하위만</label></div>
    <div class="stat-line" id="tcount"></div><div class="tbl tall"><table id="cxt" class="sortable"></table></div>`;
  w.addEventListener("input", renderTable);
  w.querySelector("#cxt").addEventListener("click", e => { const h = e.target.closest("[data-sort]"); if (h) { const k = h.dataset.sort; tsort = { k, d: tsort.k === k ? -tsort.d : -1 }; renderTable(); return; }
    const r = e.target.closest("[data-row]"); if (r) openCx(+r.dataset.row); });
  ONSHOW.table = renderTable; return w;
}
function renderTable() {
  const q = $("#tq").value.trim(), br = $("#tbr").value, sg = $("#tsg").value, mis = $("#tmis").checked;
  let L = D.cx.map((c, i) => i).filter(i => { const c = D.cx[i]; return (!q || c.n.includes(q) || (c.addr || "").includes(q)) && (!br || c.br === br) && (!sg || c.sg === sg) && (!mis || (VAR.need.v[i] >= 66.7 && VAR.supply.v[i] <= 33.3)); });
  const val = i => tsort.k === "n" ? D.cx[i].n : tsort.k === "br" ? D.cx[i].br : VAR[tsort.k].v[i];
  L.sort((a, b) => { const x = val(a), y = val(b); if (x == null) return 1; if (y == null) return -1; return (typeof x === "string" ? x.localeCompare(y, "ko") : x - y) * tsort.d; });
  const arrow = k => tsort.k === k ? (tsort.d > 0 ? " ▲" : " ▼") : "";
  $("#tcount").innerHTML = `<b>${L.length}</b>개 단지 · 행을 누르면 탐색기로 이동`;
  $("#cxt").innerHTML = `<thead><tr><th><button type="button" data-sort="n">단지${arrow("n")}</button></th><th><button type="button" data-sort="br">지사${arrow("br")}</button></th><th>공급유형</th>${TCOLS.map(k => `<th class="n"><button type="button" data-sort="${k}" title="${esc(VAR[k].label)}">${esc(TLAB[k])}${arrow(k)}</button></th>`).join("")}</tr></thead>
    <tbody>${L.map(i => `<tr data-row="${i}" tabindex="0"><td>${esc(D.cx[i].n)}</td><td>${esc(D.cx[i].br)}</td><td>${esc(D.cx[i].sg)}</td>${TCOLS.map(k => `<td class="n">${VAR[k].v[i] == null ? "–" : esc(fmtv(VAR[k].v[i], VAR[k].fmt, ""))}</td>`).join("")}</tr>`).join("")}</tbody>`;
}

/* ═════ 자료·방법 추가 ═════ */
function buildNotesExtra() {
  const w = document.createElement("div"); w.className = "grid"; w.style.marginTop = "18px";
  w.innerHTML = `<article class="card wide"><h3>사용한 자료 목록</h3><p>이 페이지가 읽은 처리 자료와 원자료입니다.</p><div class="tbl"><table><thead><tr><th>자료</th><th>설명</th><th class="n">행</th><th class="n">열</th><th>경로</th></tr></thead>
    <tbody>${D.catalog.items.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(x.desc)}</td><td class="n">${x.rows.toLocaleString()}</td><td class="n">${x.cols ?? "–"}</td><td><code>${esc(x.path)}</code></td></tr>`).join("")}</tbody></table></div>
    <h4>원자료(공공데이터 CSV) ${D.catalog.raw.length}종</h4><ul class="small">${D.catalog.raw.map(r => `<li>${esc(r)}</li>`).join("")}</ul></article>
    <article class="card wide"><h3>현장 소식</h3><p>공단 관련 주거복지 기사 ${D.news.length}건(같은 사건 중복 보도는 1건으로)입니다. 제목은 원문 기사로, 프로그램·단지 이름은 이 페이지의 사전·탐색기로 갑니다.</p>
    <ul class="news">${D.news.map(n => `<li><time>${esc(n.date)}</time><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a><small>${esc(n.host)}${n.prog ? ` · <button type="button" class="lnk" data-prog="${esc(n.prog)}">${esc(n.prog)}</button>` : ""}${n.cx.filter(id => CXI.has(id)).map(id => ` · <button type="button" class="lnk" data-goto-cx="${CXI.get(id)}">${esc(D.cx[CXI.get(id)].n)}</button>`).join("")}</small></li>`).join("")}</ul></article>`;
  w.addEventListener("click", e => { const pg = e.target.closest("[data-prog]"); if (pg) openProg(pg.dataset.prog); });
  return w;
}

initPage();
const start = (location.hash || "").slice(1);
show(D.sections.some(s => s.id === start) ? start : "overview");
requestAnimationFrame(() => window.scrollTo(0, 0));
