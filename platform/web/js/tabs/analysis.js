// 분석: 변수 탐색기(산점도), 전국 수요·공급, 실험 표 조회
import { S, api, cached, $, esc, f, hbars, setComplex, TYPE_COLOR, DOM } from '../core.js';

const st = { x: 'age60', y: 'n_records', color: 'type', table: 'e3_ranking_models' };

function rank(a) { const idx = a.map((v, i) => [v, i]).sort((p, q) => p[0] - q[0]); const r = Array(a.length); idx.forEach(([, i], k) => (r[i] = k)); return r; }
function spearman(xs, ys) {
  const n = xs.length; if (n < 5) return null;
  const rx = rank(xs), ry = rank(ys), m = (n - 1) / 2; let sxy = 0, sx = 0, sy = 0;
  for (let i = 0; i < n; i++) { sxy += (rx[i] - m) * (ry[i] - m); sx += (rx[i] - m) ** 2; sy += (ry[i] - m) ** 2; }
  return sxy / Math.sqrt(sx * sy);
}

function scatter(d) {
  const cx = d.columns.find(c => c.key === st.x), cy = d.columns.find(c => c.key === st.y);
  const pts = d.rows.filter(r => r[st.x] != null && r[st.y] != null), miss = d.rows.length - pts.length;
  const W = 900, H = 440, P = { l: 56, r: 14, t: 12, b: 40 };
  const ext = k => { const v = pts.map(r => r[k]); const a = Math.min(...v), b = Math.max(...v), pad = (b - a) * 0.04 || 1; return [a - pad, b + pad]; };
  const [x0, x1] = ext(st.x), [y0, y1] = ext(st.y);
  const X = v => P.l + (v - x0) / (x1 - x0) * (W - P.l - P.r), Y = v => H - P.b - (v - y0) / (y1 - y0) * (H - P.t - P.b);
  const ticks = (a, b) => { const step = Math.pow(10, Math.floor(Math.log10((b - a) / 5))), s = [1, 2, 5, 10].map(m => m * step).find(s => (b - a) / s <= 6); const out = []; for (let v = Math.ceil(a / s) * s; v <= b; v += s) out.push(+v.toFixed(6)); return out; };
  const col = r => st.color === 'type' ? TYPE_COLOR[r.type] : st.color === 'deployed' ? (r.deployed ? '#1e7a46' : '#c9521f') : '#3b7fbd';
  const rho = spearman(pts.map(r => r[st.x]), pts.map(r => r[st.y]));
  const legend = st.color === 'type' ? Object.entries(d.type_labels).map(([k, v]) => [TYPE_COLOR[k], v]) : st.color === 'deployed' ? [['#1e7a46', '주거복지사 배치'], ['#c9521f', '미배치']] : [];
  return `<svg class="sc" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(cx.label)}와 ${esc(cy.label)}의 산점도">
    ${ticks(x0, x1).map(v => `<line x1="${X(v)}" x2="${X(v)}" y1="${P.t}" y2="${H - P.b}" stroke="#eef0f3"/><text x="${X(v)}" y="${H - P.b + 15}" text-anchor="middle">${v.toLocaleString()}</text>`).join('')}
    ${ticks(y0, y1).map(v => `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="#eef0f3"/><text x="${P.l - 6}" y="${Y(v) + 4}" text-anchor="end">${v.toLocaleString()}</text>`).join('')}
    <text x="${(W + P.l) / 2}" y="${H - 6}" text-anchor="middle">${esc(cx.label)} (${esc(cx.unit)})</text>
    <text x="14" y="${H / 2}" text-anchor="middle" transform="rotate(-90 14 ${H / 2})">${esc(cy.label)} (${esc(cy.unit)})</text>
    ${pts.map(r => `<circle cx="${X(r[st.x]).toFixed(1)}" cy="${Y(r[st.y]).toFixed(1)}" r="${r.id === S.cid ? 7 : 4}" fill="${col(r)}" fill-opacity="${r.id === S.cid ? 1 : 0.6}" stroke="${r.id === S.cid ? '#111' : '#fff'}" stroke-width="${r.id === S.cid ? 2 : 0.6}" data-id="${r.id}"><title>${esc(r.name)} (${esc(r.branch)})\n${esc(cx.label)}: ${r[st.x].toLocaleString(undefined, { maximumFractionDigits: 2 })}\n${esc(cy.label)}: ${r[st.y].toLocaleString(undefined, { maximumFractionDigits: 2 })}</title></circle>`).join('')}
  </svg>
  <div class="row between" style="font-size:0.867rem"><div class="row">${legend.map(([c, t]) => `<span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${c};margin-right:4px"></i>${esc(t)}</span>`).join('')}</div>
    <span class="muted">단지 ${pts.length}곳${miss ? ` · 값이 없어 빠진 단지 ${miss}곳` : ''} · 순위상관 ${rho == null ? '-' : rho.toFixed(2)} · 점을 누르면 그 단지를 고릅니다</span></div>`;
}

export async function render(view, arg, alive) {
  const d = await cached('analytics', () => api('analytics'));
  if (!alive()) return;
  const groups = {}; d.columns.forEach(c => (groups[c.group] = groups[c.group] || []).push(c));
  const opts = sel => Object.entries(groups).map(([g, cs]) => `<optgroup label="${esc(g)}">${cs.map(c => `<option value="${c.key}" ${c.key === sel ? 'selected' : ''}>${esc(c.label)}</option>`).join('')}</optgroup>`).join('');
  const n = d.counts;
  view.innerHTML = `<div class="page">
    <div class="page-head"><div><h2>분석</h2><p>단지 자료와 실험 결과를 직접 살펴봅니다. 기간 ${esc(n.months)}.</p></div></div>
    <div class="tiles"><div class="tile"><b class="num">${f.int(n.complexes)}</b><span>단지</span><em>활동 기록 있음 ${f.int(n.with_records)}곳</em></div><div class="tile"><b class="num">${f.int(n.records)}</b><span>활동 기록</span><em>주민 대상</em></div>
      <div class="tile"><b class="num">${f.int(n.programs)}</b><span>추천 대상 프로그램</span></div><div class="tile"><b class="num">${f.int(n.deployed)}</b><span>주거복지사 배치 단지</span></div></div>
    <div class="panel"><h3>변수 탐색기</h3>
      <div class="row" style="margin-bottom:8px"><label>가로 <select id="ax">${opts(st.x)}</select></label><label>세로 <select id="ay">${opts(st.y)}</select></label>
        <label>색 <select id="ac"><option value="type" ${st.color === 'type' ? 'selected' : ''}>단지 유형</option><option value="deployed" ${st.color === 'deployed' ? 'selected' : ''}>주거복지사 배치</option><option value="" ${st.color === '' ? 'selected' : ''}>없음</option></select></label>
        <button class="btn sm" id="aswap">가로·세로 바꾸기</button></div>
      <div id="scBox"></div>
      <div class="muted" style="font-size:0.867rem;margin-top:6px">순위상관은 관계의 방향과 세기만 보여 줍니다. 원인을 뜻하지 않습니다. 값이 없는 단지는 0으로 놓지 않고 뺍니다.</div></div>
    <div class="grid g2">
      <div class="panel"><h3>분야별 수요와 공급 <small class="muted">전국</small></h3>
        ${S.meta.need_ids.map(k => `<div style="margin-bottom:8px"><div class="row between"><b>${esc(S.meta.needs[k])}</b><span class="muted num" style="font-size:0.867rem">주민 수요 ${f.pct(d.national_demand[k])} · 현재 공급 ${f.pct(d.national_supply[k])}</span></div>
          <div class="gauge" data-tip="주민 수요(해피콜 응답을 분야로 바꾼 비중)"><span style="width:${(d.national_demand[k] * 250).toFixed(0)}%;background:${DOM[k]}"></span></div>
          <div class="gauge" style="margin-top:2px" data-tip="현재 공급(활동 기록의 분야 비중)"><span style="width:${(d.national_supply[k] * 250).toFixed(0)}%;background:#7b8696"></span></div></div>`).join('')}
        <div class="muted" style="font-size:0.867rem">위 막대는 주민 수요, 아래 회색 막대는 현재 공급입니다. 수요는 해피콜 응답자 집계이고 단지별 값이 아닙니다.</div></div>
      <div class="panel"><h3>필요와 공급이 어긋난 단지 <small class="muted">필요 상위 1/3이면서 공급 하위 1/3</small></h3>
        ${hbars(S.meta.need_ids.map(k => ({ label: S.meta.needs[k], value: d.rows.filter(r => r['need_' + k] >= 2 / 3 && r['supply_pct_' + k] != null && r['supply_pct_' + k] <= 1 / 3).length, color: DOM[k] })), { fmt: v => v + '곳' })}
        <div class="muted" style="font-size:0.867rem;margin-top:6px">활동 기록이 있는 단지 ${f.int(n.with_records)}곳 기준입니다. <a href="#/map">지도</a>에서 '우선 검토 분야 수'로 색을 바꾸면 위치를 볼 수 있습니다.</div></div>
    </div>
  </div>`;
  const drawS = () => ($('#scBox').innerHTML = scatter(d));
  $('#ax').addEventListener('input', e => { st.x = e.target.value; drawS(); }); $('#ay').addEventListener('input', e => { st.y = e.target.value; drawS(); });
  $('#ac').addEventListener('input', e => { st.color = e.target.value; drawS(); });
  $('#aswap').addEventListener('click', () => { [st.x, st.y] = [st.y, st.x]; $('#ax').value = st.x; $('#ay').value = st.y; drawS(); });
  $('#scBox').addEventListener('click', e => { const c = e.target.closest('circle'); if (c) { setComplex(c.dataset.id); drawS(); } });
  drawS();
}
