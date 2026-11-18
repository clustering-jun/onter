// 해피콜: 관리소별 만족도, 주민이 말한 수요(전국), 수요·공급·추천 분포, 주민 의견
import { S, api, cached, $, esc, f, hbars, table, setComplex } from '../core.js';

let grp = {}, vq = '', vcat = null, vall = false;

export async function render(view, arg, alive) {
  const d = await cached('happycall', () => api('happycall'));
  if (!alive()) return;
  const s = d.summary, dist = d.distribution, cols = dist.length ? Object.keys(dist[0]).filter(k => k !== '수요 항목') : [];
  const dcolor = { '해피콜 수요': '#1c2430', '현재 공급': '#7b8696', '근거 추천': '#6ea6d6', '온터 추천(base=uniform)': '#3b7fbd', '온터 추천(기본)': '#1f6f8b' };
  view.innerHTML = `<div class="page">
    <div class="page-head"><div><h2>해피콜 만족도 조사(2025)</h2><p>주택관리공단 입주민 만족도 조사 결과입니다. 관리소 단위 점수와 전국 수준의 수요 응답으로 나뉩니다.</p></div></div>
    <div class="tiles"><div class="tile"><b class="num">${f.int(s.n_offices)}</b><span>조사 관리소</span><em>소표본 ${f.int(s.n_small)}곳</em></div><div class="tile"><b class="num">${f.n1(s.mean_overall)}</b><span>종합 만족도 평균</span></div>
      <div class="tile"><b class="num">${f.n1(s.mean_housing)}</b><span>주택관리 만족도 평균</span></div><div class="tile"><b class="num">${f.n1(s.mean_welfare)}</b><span>복지 만족도 평균</span><em>응답 있는 ${f.int(s.n_welfare)}곳</em></div></div>
    <div class="grid g2">${d.demand.map((p, i) => `<div class="panel"><h3>${esc(p.label)}가 바라는 지원 <small class="muted">${p.n}명, 복수 응답 %</small></h3>
        <div class="row" style="margin-bottom:6px"><select data-pop="${i}"><option value="">전체 응답자</option>${Object.entries(p.groups).map(([g, subs]) => `<optgroup label="${esc(g)}">${subs.map(sg => `<option value="${esc(g + '|' + sg.subgroup)}">${esc(g)}: ${esc(sg.subgroup)} (${sg.n}명)</option>`).join('')}</optgroup>`).join('')}</select></div>
        <div id="dem${i}"></div></div>`).join('')}</div>
    <div class="panel"><h3>수요와 공급, 추천의 분포 <small class="muted">주거생활지원 이용자 수요 8개 항목 기준, 전국 합계</small></h3>
      <div style="overflow:auto"><table class="tbl"><thead><tr><th>수요 항목</th>${cols.map(c => `<th class="r">${esc(c)}</th>`).join('')}</tr></thead><tbody>${dist.map(r => `<tr><td><b>${esc(r['수요 항목'])}</b></td>${cols.map(c => `<td class="r num"><div>${f.pct(r[c])}</div><div class="gauge" style="height:4px"><span style="width:${Math.min(100, r[c] * 250).toFixed(0)}%;background:${dcolor[c] || 'var(--accent)'}"></span></div></td>`).join('')}</tr>`).join('')}</tbody></table></div>
      <h4 style="margin-top:10px">수요 분포와 닮은 정도</h4>${hbars(d.alignment.map(a => ({ label: a.source, value: a.demand_align, tip: `95% 구간 ${a.lo}~${a.hi}` })), { max: 1, fmt: v => v.toFixed(3) })}</div>
    <div class="panel"><div class="row between"><h3>관리소별 만족도</h3><input id="hcQ" type="search" placeholder="관리소·지사 찾기"></div><div id="hcTable" style="margin-top:8px"></div></div>
    <div class="panel"><div class="row between"><h3>주민 의견 <small class="muted">분류 ${new Set(d.voc.map(v => v.category)).size}개 · 의견 ${d.voc.length}건</small></h3><input id="vocQ" type="search" placeholder="의견 찾기" value="${esc(vq)}"></div>
      <div class="voc"><div id="vocCats"></div><div id="vocBox"></div></div></div>
  </div>`;
  const drawDem = i => {
    const p = d.demand[i], key = grp[i] || '';
    let rows = p.overall.map(o => ({ label: o.metric, value: o.value }));
    if (key) { const [g, sg] = key.split('|'), x = (p.groups[g] || []).find(z => z.subgroup === sg); if (x) rows = p.overall.map(o => ({ label: o.metric, value: x.values[o.metric] ?? null, tip: `전체 ${o.value}%` })); }
    $('#dem' + i).innerHTML = hbars(rows, { max: 60, fmt: v => v.toFixed(1) + '%' });
  };
  d.demand.forEach((_, i) => drawDem(i));
  view.addEventListener('input', e => { const sel = e.target.closest('[data-pop]'); if (sel) { grp[sel.dataset.pop] = sel.value; drawDem(+sel.dataset.pop); } });
  const cols2 = [{ key: 'office', label: '관리소', html: r => `<b>${esc(r.office)}</b>${r.complex_ids.length > 1 ? ` <span class="chip" data-tip="${esc(r.complex_ids.map(i => S.byId[i]?.name).join(', '))}">통합 ${r.complex_ids.length}곳</span>` : r.complex_ids.length ? '' : ' <span class="chip">단지 연결 없음</span>'}${r.small ? ' <span class="chip warn">소표본</span>' : ''}` },
  { key: 'branch', label: '지사' }, { key: 'n', label: '응답', r: 1 }, { key: 'overall', label: '종합', r: 1, fmt: f.n1 }, { key: 'housing', label: '주택관리', r: 1, fmt: f.n1 }, { key: 'rental', label: '임대운영', r: 1, fmt: f.n1 },
  { key: 'welfare', label: '복지', r: 1, fmt: v => v == null ? '<span class="na">응답 없음</span>' : f.n1(v) }];
  const drawT = q => { const box = $('#hcTable'); box.innerHTML = ''; box.append(table(cols2, d.offices.filter(o => !q || o.office.includes(q) || o.branch.includes(q)), { sortKey: 'overall', onRow: r => { if (r.complex_ids.length) setComplex(r.complex_ids[0], 'complex'); } })); box.firstChild.style.maxHeight = '520px'; };
  drawT('');
  $('#hcQ').addEventListener('input', e => drawT(e.target.value.trim()));
  const cats = Object.values(d.voc.reduce((m, v) => { const c = m[v.category] = m[v.category] || { name: v.category, n: v.cat_n || 0, items: [] }; c.items.push(v); return m; }, {}))
    .map(c => ({ ...c, n: c.n || c.items.reduce((a, v) => a + (v.freq || 1), 0), items: c.items.sort((a, b) => (b.freq || 0) - (a.freq || 0)) })).sort((a, b) => b.n - a.n);
  if (!vcat) vcat = cats[0].name;
  const op = v => `<div class="vocitem"><p>${esc(v.text)}</p>${v.freq ? `<span class="chip">${v.freq}건</span>` : ''}</div>`;
  const drawV = () => {
    const max = cats[0].n, shown = vall ? cats : cats.slice(0, 12);
    $('#vocCats').innerHTML = `<h4>많이 나온 분류 <small class="muted">응답 수</small></h4>${shown.map(c => `<button class="voccat ${!vq && c.name === vcat ? 'on' : ''}" data-c="${esc(c.name)}"><span class="n">${esc(c.name)}</span><span class="bg"><i style="width:${(c.n / max * 100).toFixed(0)}%"></i></span><b class="num">${c.n}</b></button>`).join('')}
      ${cats.length > 12 ? `<button class="btn sm ghost" id="vocMore" style="margin-top:8px">${vall ? '접기' : `나머지 ${cats.length - 12}개 분류 보기`}</button>` : ''}`;
    if (vq) {
      const hits = d.voc.filter(v => v.text.includes(vq) || v.category.includes(vq));
      $('#vocBox').innerHTML = `<h4>'${esc(vq)}'이 들어간 의견 ${hits.length}건</h4>${hits.map(v => `<div class="vocitem"><p>${esc(v.text)}<small class="muted"> · ${esc(v.category)}</small></p>${v.freq ? `<span class="chip">${v.freq}건</span>` : ''}</div>`).join('') || '<div class="empty">찾는 의견이 없습니다</div>'}`;
    } else {
      const c = cats.find(x => x.name === vcat) || cats[0];
      $('#vocBox').innerHTML = `<h4>${esc(c.name)} <small class="muted">응답 ${c.n}건 · 대표 의견 ${c.items.length}개</small></h4>${c.items.map(op).join('')}`;
    }
  };
  $('#vocCats').addEventListener('click', e => {
    if (e.target.id === 'vocMore') { vall = !vall; drawV(); return; }
    const b = e.target.closest('.voccat'); if (b) { vcat = b.dataset.c; vq = ''; $('#vocQ').value = ''; drawV(); }
  });
  drawV(); $('#vocQ').addEventListener('input', e => { vq = e.target.value.trim(); drawV(); });
}
