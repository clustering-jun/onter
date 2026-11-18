// 프로그램 추천: 한 화면에 세 칸(조절 | 후보 목록 | 고른 후보의 상세). 쪽 전체를 스크롤하지 않고 칸 안에서만 움직인다.
// 목록은 '순위'와 '분야별'로 바꿔 볼 수 있고, 후보를 누르면 오른쪽에 근거·사례·걸림돌·점검표·요건이 열린다. 설명과 점검표는 열릴 때 자동으로 만든다.
import { STATIC, S, api, post, cached, $, $$, esc, f, needPick, domChip, stChip, stack, domLegend, debounce, toast, cx, pos } from '../core.js';

let sel = null, mode = 'rank', tab = 'why', lastReq = 0, last = null;
document.addEventListener('click', e => { if (!e.target.closest('.menu')) $$('.menu-pop').forEach(x => (x.hidden = true)); });
const MONTH = m => m.join('·') + '월';

function row(x) {
  const h = x.hidden;
  const tip = `순위 점수(평소에는 감춰 둡니다)\n종합 ${h.score == null ? '-' : h.score.toFixed(2)} = 근거 ${h.evidence_pct == null ? '-' : h.evidence_pct.toFixed(2)} × ${(1 - S.knobs.w).toFixed(2)} + 필요 적합 ${h.need_fit_pct == null ? '-' : h.need_fit_pct.toFixed(2)} × ${S.knobs.w.toFixed(2)}\n점수는 줄을 세우는 데만 씁니다.`;
  const flag = x.tag === 'resume' ? '<span class="chip acc">재개 검토</span>' : x.tag === 'resurfaced' ? `<span class="chip warn">다시 제안</span>` : '';
  return `<button class="rrow ${x.std_id === sel ? 'on' : ''}" data-sid="${x.std_id}">
    <span class="rk" data-tip="${esc(tip)}">${x.rank}</span>
    <span class="body"><b>${esc(x.name)}</b>
      <span class="meta">${domChip(x.domain, x.domain_label)}${flag}${x.welfare_gap ? '<span class="chip warn">미배치 주의</span>' : ''}</span>
      <span class="sub">비슷한 단지 ${x.peer_k}곳 중 ${x.peer_n}곳 · 전체 ${Math.round(x.pop * 100)}%${x.need_confirmed ? ' · 확인된 필요' : x.need_pct >= 0.6 ? ' · 필요 ' + pos(x.need_pct) : ''}</span></span>
  </button>`;
}
const domRow = (i, d) => `<button class="rrow ${i.std_id === sel ? 'on' : ''}" data-sid="${i.std_id}"><span class="rk dom ${d.domain}">${d.items.indexOf(i) + 1}</span>
    <span class="body"><b>${esc(i.name)}</b><span class="meta">${stChip(i.status, i.status_label)}</span></span></button>`;

function evidenceHtml(d) {
  const cases = d.more_cases.length ? d.more_cases.map(c => `<div class="case"><div class="row between"><span class="t"><a href="#/complex/${c.complex_id}">${esc(c.complex)}</a> · ${f.ym(c.month)}</span><span class="m" data-tip="이 단지와의 유사도(구성·운영·거리)">유사도 ${c.similarity.toFixed(2)}</span></div>
      <div>${esc(c.title)}</div>${c.content ? `<div class="m">${esc(c.content)}</div>` : ''}
      <div class="m">${[c.participants != null ? '참여 ' + c.participants + '명' : '', c.place ? '장소 ' + esc(c.place) : '', c.partners.length ? '함께 ' + c.partners.map(esc).join(', ') : ''].filter(Boolean).join(' · ')}</div></div>`).join('')
    : '<div class="note">비슷한 단지에서 이 프로그램을 운영한 기록이 없습니다.</div>';
  const cards = d.evidence.casebook.map(c => `<div class="case"><div class="row between"><span class="t">${esc(c.headline)}</span><span class="chip">${esc(c.relation)}</span></div>
      ${c.need ? `<div class="m"><b>배경</b> ${esc(c.need)}</div>` : ''}${c.how ? `<div class="m"><b>운영</b> ${esc(c.how)}</div>` : ''}
      <div class="m"><a href="#/cases/${c.card_id}">사례 카드 전체 보기</a></div></div>`).join('');
  const news = d.evidence.news.map(n => `<div class="case"><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a><div class="m">${esc(n.outlet || '')} · ${esc(n.date || '')}</div></div>`).join('');
  return `${cases}${cards ? `<h4 style="margin:18px 0 8px">사례집</h4>${cards}` : ''}${news ? `<h4 style="margin:18px 0 8px">관련 소식</h4>${news}` : ''}`;
}
function obstacleHtml(d) {
  const ob = d.obstacles.length ? `<h4 style="margin-bottom:8px">사례집에 적힌 걸림돌과 해결 <small class="muted">${esc(d.obstacles[0].relation)} ${d.obstacles.length}건</small></h4>
    <table class="tbl obtbl2"><thead><tr><th>유형</th><th>부딪힌 문제</th><th>해결 방식</th><th>어떻게 풀었나</th></tr></thead><tbody>
    ${d.obstacles.map(o => `<tr><td><span class="chip warn">${esc(o.category)}</span></td><td>${esc(o.obstacle)}</td>
      <td>${o.strategy ? `<span class="chip ok">${esc(o.strategy)}</span>` : '<span class="muted">-</span>'}</td>
      <td>${o.solution ? esc(o.solution) : '<span class="muted">사례집에 적혀 있지 않습니다</span>'}</td></tr>`).join('')}</tbody></table>` : '';
  const tips = d.check.obstacles.length ? `<h4 style="margin:${ob ? 22 : 0}px 0 8px">이런 프로그램에서 자주 나오는 걸림돌</h4>
    <table class="tbl obtbl2 tips"><thead><tr><th>유형</th><th>사례집에서 많이 쓴 해결 방식</th><th class="r">사례</th></tr></thead><tbody>
    ${d.check.obstacles.map(o => `<tr><td><span class="chip warn">${esc(o.obstacle)}</span></td><td><span class="chip ok">${esc(o.strategy)}</span></td><td class="r num">${o.n}건</td></tr>`).join('')}</tbody></table>` : '';
  return ob + tips || '<div class="muted">사례집에 적힌 걸림돌이 없습니다</div>';
}
const clHtml = secs => `<div class="cl">${secs.map(s => s.items.length ? `<h4>${esc(s.section)}</h4><ul>${s.items.map(i => `<li>${esc(i)}</li>`).join('')}</ul>` : '').join('')}</div>`;
function reqHtml(d) {
  const c = d.check, ex = c.basis === 'expert';
  return `<table class="info"><tbody>
    ${ex ? `<tr><th>1회 비용</th><td>${f.man(c.cost_session)} <span class="muted">(부담 ${c.payers.map(esc).join(' · ')})</span></td></tr>
      <tr><th>1회 인력</th><td>${f.n1(c.staff_hours_session)}명×시간 · 난이도 5단계 중 ${c.difficulty}</td></tr>
      <tr><th>꼭 필요한 공간</th><td>${c.essential_places.map(esc).join(', ') || '-'}</td></tr>
      <tr><th>꼭 필요한 협력기관</th><td>${c.self_run ? '없이 자체 운영 가능' : c.essential_partners.map(p => `${esc(p.type)} <span class="chip ${p.status.startsWith('협력') ? 'ok' : p.status.startsWith('가까운') ? '' : 'warn'}">${esc(p.status)}</span>`).join('<br>') || '-'}</td></tr>
      <tr><th>주거복지사</th><td>${c.needs_welfare_worker ? '필요' : '없어도 가능'}</td></tr>` : ''}
    <tr><th>공단 쪽 연간 비용</th><td>${f.man(c.cost_year_est)}</td></tr>
    <tr><th>필요 자원</th><td>${c.resources.map(esc).join(', ') || '-'}</td></tr>
    <tr><th>기록에 나온 협력기관</th><td>${c.partners.map(p => `${esc(p.type)} ${Math.round(p.share * 100)}%`).join(', ') || '-'}</td></tr>
    <tr><th>참여 규모(중앙값)</th><td>${f.int(c.participants_med)}명</td></tr>
    <tr><th>많이 여는 달</th><td>${c.peak_months.replaceAll('|', '·')}월</td></tr></tbody></table>`;
}

async function drawDetail(cid, reload) {
  const box = $('#recDetail'); if (!box || !sel) { if (box) box.innerHTML = '<div class="empty">후보를 고르세요</div>'; return; }
  const sid = sel;
  box.innerHTML = '<div class="empty"><span class="spin"></span></div>';
  const d = await cached(`cand:${cid}:${sid}:${S.stateVer || 0}`, () => api('candidate', { id: cid, sid }));
  if (sel !== sid || !$('#recDetail')) return;
  const c = d.check, fx = d.facts, item = last && last.items.find(x => x.std_id === sid), canEx = ['not_run', 'no_record', 'snoozed'].includes(d.status);
  const body = () => tab === 'why' ? `<div class="answer" id="expl">${d._expl ? esc(d._expl.text) : '<span class="muted"><span class="spin"></span> 설명을 쓰는 중</span>'}</div>
      <ul class="factlist">
        <li><span>분야</span><span>${domChip(d.domain, d.domain_label)}${fx.need_pct >= 60 ? ` 이 단지의 필요 지표가 전체 단지 중 상위 ${Math.max(1, 100 - fx.need_pct)}%` : ''}</span></li>
        <li><span>비슷한 단지</span><span>${fx.peer_k}곳 가운데 <b>${fx.peer_n}곳</b>이 운영</span></li>
        <li><span>전체 단지</span><span><b>${fx.adopt_pct}%</b>가 운영한 적이 있음</span></li>
        ${fx.partners.length ? `<li><span>주로 함께 한 기관</span><span>${fx.partners.map(esc).join(', ')}</span></li>` : ''}
        <li><span>참고할 사례</span><span>비슷한 단지 기록 ${fx.n_cases}건${fx.n_cards ? ', 사례집 카드 ' + fx.n_cards + '장' : ''}</span></li>
      </ul>`
    : tab === 'cases' ? evidenceHtml(d) : tab === 'obst' ? obstacleHtml(d)
      : tab === 'check' ? `<div id="clBox">${d._cl ? clHtml(d._cl.sections) : '<div class="muted"><span class="spin"></span> 이 단지에 맞춘 점검표를 만드는 중(5~10초)</div>'}</div>` : reqHtml(d);
  const draw = () => {
    box.innerHTML = `<div class="dhead">
        <div class="row between"><div class="row">${item ? `<span class="rkbig">${item.rank}</span>` : ''}${domChip(d.domain, d.domain_label)}${stChip(d.status, d.status_label)}</div>
          <div class="row">${canEx ? `<span class="menu"><button class="btn sm" data-menu>제외 ▾</button><div class="menu-pop" hidden>
              <button data-ex="not_now">지금은 아님<small class="muted">후보가 모자랄 때 ${S.meta.max_resurface}번까지 다시 나올 수 있음</small></button>
              <button data-ex="infeasible">운영 불가능<small class="muted">다시 추천하지 않음</small></button>
              <button data-ex="already">이미 운영 중<small class="muted">기록이 없는 것으로 표시</small></button></div></span>` : ''}
            <a class="btn sm" href="#/programs/${sid}">복지 프로그램 사전</a><a class="btn sm" href="#/kg/program:${sid}">Knowledge Graph</a></div></div>
        <h2>${esc(d.name)}</h2>
        <div class="dfacts"><span>공단 쪽 연간 비용 <b>${f.man(c.cost_year_est)}</b></span><span>난이도 <b>${c.staff_tier}/5</b></span><span>많이 여는 달 <b>${c.peak_months.replaceAll('|', '·')}월</b></span></div>
        ${c.welfare_gap ? '<div class="note warn" style="margin-top:10px">주거복지사가 있어야 하는 프로그램인데 이 단지는 미배치입니다.</div>' : ''}
      </div>
      <div class="subtabs">${[['why', '추천 근거'], ['cases', `운영 사례 ${d.more_cases.length}`], ['obst', '걸림돌·해결'], ['check', '실행 점검표'], ['req', '실행 요건']].map(([k, t]) => `<button data-t="${k}" class="${k === tab ? 'on' : ''}">${t}</button>`).join('')}</div>
      <div class="dbody">${body()}</div>`;
    if (tab === 'why' && !d._expl) post('llm/explain', { id: cid, sid }).then(r => { d._expl = r; if (sel === sid && tab === 'why' && $('#expl')) $('#expl').textContent = r.text; }).catch(() => { if ($('#expl')) $('#expl').textContent = d.explanation.template; });
    if (tab === 'check' && !d._cl) post('llm/checklist', { id: cid, sid }).then(r => { d._cl = r; if (sel === sid && tab === 'check' && $('#clBox')) $('#clBox').innerHTML = clHtml(r.sections); }).catch(() => { d._cl = { sections: d.rule_checklist }; if ($('#clBox')) $('#clBox').innerHTML = clHtml(d.rule_checklist); });
  };
  box.onclick = async e => {
    const t = e.target.closest('[data-t]'); if (t) { tab = t.dataset.t; draw(); box.scrollTop = 0; return; }
    if (e.target.closest('[data-menu]')) { const p = box.querySelector('.menu-pop'); p.hidden = !p.hidden; return; }
    const ex = e.target.closest('[data-ex]');
    if (ex) {
      const kind = ex.dataset.ex, note = kind === 'infeasible' ? (prompt('운영할 수 없는 이유를 한 줄로 남겨 주세요(선택).', '') ?? '') : '';
      try {
        const r = await post('state/exclude', { id: cid, sid, kind, note }); S.stateVer = (S.stateVer || 0) + 1; sel = null;
        toast(kind === 'not_now' ? (r.will_resurface ? `뺐습니다(${r.count}번째). 후보가 모자랄 때만 다시 나올 수 있습니다.` : `뺐습니다(${r.count}번째). 더는 다시 나오지 않습니다.`) : kind === 'infeasible' ? '운영 불가능으로 표시했습니다.' : "'이미 운영 중'으로 표시했습니다.");
        reload();
      } catch (err) { toast(err.message); }
    }
  };
  draw();
}

const rng = g => `min="${g[0]}" max="${g[g.length - 1]}" step="${g[1] - g[0]}"`;   // 정적 판: 미리 계산한 격자에 맞춘 범위
export async function render(view, arg, alive) {
  if (!S.cid) { view.innerHTML = needPick(); return; }
  const c = cx(), k = S.knobs, cid = S.cid; k.domain = '';
  view.innerHTML = `<div class="recapp">
    <aside class="rec-ctl">
      <h2>${esc(c.name)}</h2><p class="muted" style="margin:2px 0 14px">아직 하지 않은 프로그램 가운데 먼저 검토할 후보</p>
      <div class="knob"><label for="kw">필요 반영 정도 <span class="num" id="kwv"></span></label><input id="kw" type="range" ${STATIC ? rng(S.meta.grid.w) : 'min="0" max="0.5" step="0.05"'} value="${k.w}">
        <small class="muted">← 많이 하는 것 · 이 단지의 필요 →</small></div>
      <div class="knob" style="margin-top:14px"><label for="kl">분야 고르게 <span class="num" id="klv"></span></label><input id="kl" type="range" ${STATIC ? rng(S.meta.grid.lam) : 'min="0" max="0.75" step="0.05"'} value="${k.lam}"></div>
      <div class="row between" style="margin-top:14px"><span style="font-weight:600">후보 수</span><span class="seg" id="kk">${[5, 10, 15].map(n => `<button data-k="${n}" class="${k.k === n ? 'on' : ''}">${n}</button>`).join('')}</span></div>
      <div class="row between" style="margin-top:10px"><button class="btn sm ghost" id="kreset">기본값</button><span class="ms" id="recMs"></span></div>${STATIC ? '<div class="muted" style="font-size:0.867rem;margin-top:8px">공개 시연판입니다. 조절값은 미리 계산해 둔 단계로 움직이고, 제외 표시는 이 브라우저에만 저장됩니다.</div>' : ''}
      <h4 style="margin:20px 0 6px">목록의 분야 구성</h4><div id="mixList"></div>
      <h4 style="margin:12px 0 6px">이 단지의 목표</h4><div id="mixTarget"></div><div style="margin-top:8px">${domLegend()}</div>
      <h4 style="margin:20px 0 6px">제외·보류</h4><div id="exBox" class="muted">없음</div>
      <div class="row" style="margin-top:20px"><a class="btn pri" href="#/plan">예산·인력에 맞춰 묶기</a></div>
    </aside>
    <section class="rec-list">
      <div class="row between" style="margin-bottom:10px"><span class="seg" id="rmode"><button data-m="rank" class="${mode === 'rank' ? 'on' : ''}">순위</button><button data-m="domain" class="${mode === 'domain' ? 'on' : ''}">분야별</button></span><span class="muted" id="recCount"></span></div>
      <div id="recNote"></div><div id="recList"></div>
    </section>
    <section class="rec-detail" id="recDetail"></section>
  </div>`;
  const drawList = () => {
    const r = last; if (!r) return;
    if (mode === 'rank') {
      $('#recCount').textContent = `${r.items.length}개`;
      $('#recList').innerHTML = r.items.map(row).join('') || '<div class="empty">보여 줄 후보가 없습니다</div>';
    } else {
      $('#recCount').textContent = '분야마다 상위 3개';
      $('#recList').innerHTML = r.by_domain.map(d => `<div class="dgroup"><div class="row between">${domChip(d.domain, d.label)}<span class="muted">필요 ${pos(d.need)}</span></div>${d.items.map(i => domRow(i, d)).join('')}</div>`).join('');
    }
  };
  const load = async () => {
    const my = ++lastReq;
    $('#kwv').textContent = k.w.toFixed(2); $('#klv').textContent = k.lam.toFixed(2);
    const r = await api('recommend', { id: cid, w: k.w, lam: k.lam, k: k.k });
    if (my !== lastReq || !alive() || !$('#recList')) return;
    last = r;
    $('#recMs').innerHTML = STATIC ? '' : `<b>${r.ms}ms</b>`;
    const sh = r.shortage, notes = [];
    if (!r.has_records) notes.push(`<div class="note warn">기록 없는 단지라 모든 프로그램이 후보입니다. 이미 하는 것은 '제외 → 이미 운영 중'으로 표시해 주세요.</div>`);
    if (r.confirmed_used.length) notes.push(`<div class="note ok">확인된 필요 반영: ${r.confirmed_used.map(d => esc(S.meta.needs[d])).join(', ')}</div>`);
    if (sh) notes.push(`<div class="note warn">새 후보가 ${sh.fresh}개뿐입니다.${sh.resume ? ` 재개 검토 ${sh.resume}개 추가.` : ''}${sh.resurfaced ? ` 보류한 것 ${sh.resurfaced}개 다시 제안.` : ''}</div>`);
    $('#recNote').innerHTML = notes.join('');
    const ids = mode === 'rank' ? r.items.map(x => x.std_id) : r.by_domain.flatMap(d => d.items.map(i => i.std_id));
    const keep = sel && ids.includes(sel);
    if (!keep) sel = ids[0] || null;
    drawList();
    $('#mixList').innerHTML = stack(r.list_mix); $('#mixTarget').innerHTML = stack(r.target);
    if (!keep || !$('#recDetail').firstChild) drawDetail(cid, load);
    api('state', { id: cid }).then(stt => { if ($('#exBox')) $('#exBox').innerHTML = stt.excluded_view.length ? stt.excluded_view.map(e => `<div class="row between" style="padding:4px 0;color:var(--ink)"><span>${esc(e.name)} <span class="chip ${e.kind === 'infeasible' ? 'bad' : e.kind === 'not_now' ? 'warn' : ''}">${esc(e.kind_label)}</span></span><button class="btn sm" data-restore="${e.std_id}">되돌리기</button></div>`).join('') : '없음'; });
  };
  const reload = debounce(load, 60);
  $('#kw').addEventListener('input', e => { k.w = +e.target.value; reload(); });
  $('#kl').addEventListener('input', e => { k.lam = +e.target.value; reload(); });
  $('#kk').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; k.k = +b.dataset.k; $$('#kk button').forEach(x => x.classList.toggle('on', x === b)); load(); });
  $('#kreset').addEventListener('click', () => { Object.assign(k, { w: S.meta.defaults.w, lam: S.meta.defaults.lam, k: 10, domain: '' }); render(view, arg, alive); });
  $('#rmode').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; mode = b.dataset.m; $$('#rmode button').forEach(x => x.classList.toggle('on', x === b)); drawList(); $('#recList').parentElement.scrollTop = 0; });
  $('#recList').addEventListener('click', e => { const b = e.target.closest('.rrow'); if (!b) return; sel = b.dataset.sid; $$('.rrow').forEach(x => x.classList.toggle('on', x === b)); drawDetail(cid, load); });
  $('#exBox').addEventListener('click', async e => { const b = e.target.closest('[data-restore]'); if (!b) return; await post('state/restore', { id: cid, sid: b.dataset.restore }); S.stateVer = (S.stateVer || 0) + 1; toast('되돌렸습니다'); load(); });
  await load();
}
