// 프로그램 사전: 목록 화면(검색·분야·정렬, 카드) → 프로그램을 누르면 상세 화면(#/programs/ID)으로 넘어간다
import { S, api, cached, $, $$, esc, f, domChip, hbars, monthBars, debounce, NA, DOM } from '../core.js';

const st = { q: '', dom: '', sort: 'adoption' };
const SORTS = {
  adoption: ['운영한 단지가 많은 순', (a, b) => b.adoption - a.adoption], cost: ['1회 비용이 적은 순', (a, b) => (a.cost_session ?? 1e12) - (b.cost_session ?? 1e12)],
  easy: ['쉬운 순', (a, b) => a.difficulty - b.difficulty || b.adoption - a.adoption], name: ['이름순', (a, b) => a.name.localeCompare(b.name, 'ko')],
};
const won = v => v == null ? '-' : v < 10000 ? '거의 없음' : Math.round(v / 10000).toLocaleString() + '만 원';

const card = r => `<a class="pgcard" href="#/programs/${r.std_id}">
    <div class="row between">${domChip(r.domain, r.domain_label)}<span class="muted">${esc(r.family)}</span></div>
    <h4>${esc(r.name)}</h4>
    <div class="pgbar"><span style="width:${(r.adoption * 100).toFixed(0)}%;background:${DOM[r.domain] || 'var(--n0)'}"></span></div>
    <div class="pgmeta"><span>운영 단지 <b>${f.pct(r.adoption)}</b></span><span>1회 <b>${won(r.cost_session)}</b></span><span>난이도 <b>${r.difficulty}/5</b></span></div>
    ${r.needs_welfare_worker || r.n_cards || r.n_news ? `<div class="row" style="margin-top:10px">${r.needs_welfare_worker ? '<span class="chip warn">주거복지사 필요</span>' : ''}${r.n_cards ? `<span class="chip">사례집 ${r.n_cards}</span>` : ''}${r.n_news ? `<span class="chip">소식 ${r.n_news}</span>` : ''}</div>` : ''}
  </a>`;

async function list(view, all, alive) {
  view.innerHTML = `<div class="page">
    <div class="page-head"><div><h2>프로그램 사전</h2><p>표준 프로그램 ${all.length}종. 프로그램을 누르면 자세한 내용이 열립니다.</p></div></div>
    <div class="panel pgtool">
      <input id="pgQ" type="search" placeholder="이름이나 하고 싶은 일로 찾기 (예: 빨래, 어르신 안부, 스마트폰 교육)" value="${esc(st.q)}">
      <div class="row between"><div class="row" id="pgD"><button class="btn sm ${st.dom ? '' : 'pri'}" data-d="">전체</button>${S.meta.need_ids.map(d => `<button class="btn sm ${st.dom === d ? 'pri' : ''}" data-d="${d}">${esc(S.meta.needs[d])}</button>`).join('')}</div>
        <select id="pgS" aria-label="정렬">${Object.entries(SORTS).map(([k, [t]]) => `<option value="${k}" ${k === st.sort ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
    </div>
    <div id="pgHits"></div>
    <div class="muted" id="pgCount"></div>
    <div class="pggrid" id="pgGrid"></div></div>`;
  const draw = async () => {
    let rows = all.filter(r => !st.dom || r.domain === st.dom);
    if (st.q) {
      const hits = await api('search', { q: st.q });
      if (!alive() || !$('#pgGrid')) return;
      rows = hits.programs.map(h => all.find(r => r.std_id === h.std_id)).filter(r => r && (!st.dom || r.domain === st.dom));
      const extra = [hits.complexes.length ? `<div class="row"><span class="muted">단지</span>${hits.complexes.map(c => `<a class="chip" href="#/complex/${c.id}">${esc(c.name)}</a>`).join('')}</div>` : '',
      hits.cards.length ? `<div class="row"><span class="muted">사례집</span>${hits.cards.map(c => `<a class="chip" href="#/cases/${c.card_id}">${esc(c.headline.slice(0, 26))}…</a>`).join('')}</div>` : ''].filter(Boolean);
      $('#pgHits').innerHTML = extra.length ? `<div class="panel" style="display:grid;gap:8px">${extra.join('')}</div>` : '';
    } else { $('#pgHits').innerHTML = ''; rows = [...rows].sort(SORTS[st.sort][1]); }
    $('#pgCount').textContent = st.q ? `'${st.q}'에 가까운 순서 ${rows.length}종` : `${rows.length}종`;
    $('#pgGrid').innerHTML = rows.map(card).join('') || '<div class="panel empty">찾는 프로그램이 없습니다</div>';
    $('#pgS').disabled = !!st.q;
  };
  $('#pgQ').addEventListener('input', debounce(e => { st.q = e.target.value.trim(); draw(); }, 220));
  $('#pgD').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; st.dom = b.dataset.d; $$('#pgD button').forEach(x => x.classList.toggle('pri', x === b)); draw(); });
  $('#pgS').addEventListener('input', e => { st.sort = e.target.value; draw(); });
  await draw();
}

async function detail(view, sid, all, alive) {
  const d = await cached('prog:' + sid, () => api('program', { sid }));
  if (!alive()) return;
  const r = d.requirement, ex = r.basis === 'expert';
  const same = all.filter(x => x.domain === d.domain).sort(SORTS.adoption[1]), k = same.findIndex(x => x.std_id === sid), prev = same[k - 1], next = same[k + 1];
  view.innerHTML = `<div class="page">
    <div class="row between"><a class="btn" href="#/programs">← 프로그램 목록</a>
      <div class="row">${prev ? `<a class="btn sm ghost" href="#/programs/${prev.std_id}">← ${esc(prev.name)}</a>` : ''}${next ? `<a class="btn sm ghost" href="#/programs/${next.std_id}">${esc(next.name)} →</a>` : ''}</div></div>
    <div class="panel"><div class="row">${domChip(d.domain, d.domain_label)}<span class="chip">${esc(d.family)}</span>${r.needs_welfare_worker ? '<span class="chip warn">주거복지사 필요</span>' : ''}</div>
      <h2 style="font-size:1.6rem;margin:10px 0 6px">${esc(d.name)}</h2><p style="margin:0;color:var(--ink2)">${esc(d.definition)}</p>
      <div class="tiles" style="margin-top:18px"><div class="tile"><b class="num">${f.pct(d.adoption)}</b><span>운영한 단지</span><em>${f.int(d.n_complexes)}곳</em></div>
        <div class="tile"><b class="num">${f.int(d.n_records)}건</b><span>활동 기록</span><em>30개월</em></div>
        <div class="tile"><b class="num">${ex ? won(r.cost_session) : NA}</b><span>1회 비용</span><em>${ex ? r.payers.map(esc).join(' · ') : ''}</em></div>
        <div class="tile"><b class="num">${ex ? f.n1(r.hours_session) + '명×시간' : NA}</b><span>1회 인력</span><em>난이도 ${ex ? r.difficulty + '/5' : '-'}</em></div></div></div>
    <div class="grid g2">
      <div class="panel"><h3>실행 요건</h3><table class="info"><tbody>
        <tr><th>꼭 필요한 공간</th><td>${r.essential_places.map(esc).join(', ') || '-'}</td></tr>
        <tr><th>꼭 필요한 협력기관</th><td>${r.self_run ? '없이 자체 운영 가능' : r.essential_partners.map(esc).join(', ') || '-'}</td></tr>
        <tr><th>공단 쪽 연간 비용</th><td>${f.man(r.cost_year)} <span class="muted">(전체 ${f.man(r.cost_year_total)})</span></td></tr>
        <tr><th>연간 인력</th><td>${f.n1(r.hours_year)}명×시간 <span class="muted">(단지당 연 ${f.n1(r.recs_per_year)}회)</span></td></tr>
        <tr><th>주거복지사</th><td>${r.needs_welfare_worker ? '필요' : '없어도 가능'}${r.welfare_dependent_data ? ' · 배치 단지에서 더 많이 운영' : ''}</td></tr>
        <tr><th>통상 대상</th><td>${d.targets.map(esc).join(', ') || '-'}</td></tr>
        <tr><th>필요 자원</th><td>${d.resources.map(esc).join(', ') || '-'}</td></tr></tbody></table></div>
      <div class="panel"><h3>기록에서 본 운영 방식</h3>
        <h4 style="margin-bottom:8px">함께 한 기관</h4>${d.observed.partners.length ? hbars(d.observed.partners.map(p => ({ label: p.type, value: p.share })), { max: 1, fmt: f.pct }) : '<span class="muted">기록에 적힌 기관이 없습니다</span>'}
        <table class="info" style="margin-top:12px"><tbody>
          <tr><th>장소</th><td>${d.observed.places.map(p => `${esc(p.label)} ${Math.round(p.share * 100)}%`).join(', ') || '-'}</td></tr>
          <tr><th>참여 규모(중앙값)</th><td>${f.int(d.observed.participants_med)}명</td></tr>
          <tr><th>세대 방문 · 정기 운영</th><td>${f.pct(d.observed.household_visit)} · ${f.pct(d.observed.regular)}</td></tr></tbody></table></div>
      <div class="panel"><h3>언제 많이 하나</h3>
        <div class="months" style="height:90px">${d.month_share.map((v, m) => `<i style="height:${(v / Math.max(...d.month_share, 0.001) * 100).toFixed(0)}%" data-tip="${m + 1}월 ${Math.round(v * 100)}%"></i>`).join('')}</div>
        <div class="mlabels">${Array.from({ length: 12 }, (_, m) => `<span>${m + 1}월</span>`).join('')}</div>
        <h4 style="margin:18px 0 8px">월별 기록 추이</h4>${monthBars(d.trend.n, d.trend.months, { h: 90, title: '월별 기록 추이' })}</div>
      <div class="panel"><h3>어떤 단지가 운영했나</h3>
        ${hbars([...d.by_type.map(t => ({ label: t.label, value: t.rate })), ...d.by_deploy.map(t => ({ label: t.label, value: t.rate, color: '#7b8696' }))], { max: 1, fmt: f.pct })}
        <h4 style="margin:18px 0 8px">많이 운영한 단지</h4><div class="row">${d.top_complexes.map(c => `<a class="chip" href="#/complex/${c.id}">${esc(c.name)} ${c.n}건</a>`).join('') || '<span class="muted">없음</span>'}</div></div>
    </div>
    <div class="grid g2">
      <div class="panel"><h3>최근 기록 사례</h3>${d.examples.map(x => `<div class="case"><div class="t"><a href="#/complex/${x.complex_id}">${esc(x.complex)}</a> · ${f.ym(x.month)}</div><div>${esc(x.title)}</div>${x.content ? `<div class="m">${esc(x.content)}</div>` : ''}</div>`).join('') || '<div class="muted">기록 없음</div>'}</div>
      <div class="panel"><h3>사례집과 소식</h3>
        ${d.cards.map(c => `<div class="case"><span class="chip">사례집</span> <a href="#/cases/${c.card_id}">${esc(c.headline)}</a></div>`).join('')}
        ${d.news.slice(0, 6).map(n => `<div class="case"><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a><div class="m">${esc(n.outlet || '')} · ${esc(n.date || '')}</div></div>`).join('')}
        ${d.cards.length || d.news.length ? '' : '<div class="muted">연결된 사례집 사례나 소식이 없습니다</div>'}
        <h4 style="margin:18px 0 8px">비슷한 프로그램</h4><div class="row">${d.similar.map(s => `<a class="chip" href="#/programs/${s.std_id}">${esc(s.name)}</a>`).join('')}</div>
        ${d.aliases.length ? `<h4 style="margin:18px 0 8px">기록에 쓰인 이름</h4><div class="row">${d.aliases.map(a => `<span class="chip" data-tip="${esc(a.variants)}">${esc(a.title)}</span>`).join('')}</div>` : ''}
        <div class="row" style="margin-top:18px"><a class="btn sm" href="#/kg/program:${sid}">Knowledge Graph</a></div></div>
    </div></div>`;
}

export async function render(view, arg, alive) {
  const all = await cached('programs', () => api('programs'));
  if (!alive()) return;
  if (arg && all.some(x => x.std_id === arg)) return detail(view, arg, all, alive);
  return list(view, all, alive);
}
