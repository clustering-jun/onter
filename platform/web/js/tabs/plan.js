// 실행 계획: 예산·인력 한도와 조절 손잡이를 바꿀 때마다 정수계획(모듈 4)으로 묶음을 다시 고른다
import { STATIC, S, post, $, esc, f, needPick, domChip, debounce, cx } from '../core.js';

let lastReq = 0;

const rng = g => `min="${g[0]}" max="${g[g.length - 1]}" step="${g[1] - g[0]}"`;   // 정적 판: 미리 계산한 격자에 맞춘 범위
export async function render(view, arg, alive) {
  if (!S.cid) { view.innerHTML = needPick(); return; }
  const c = cx(), p = S.plan, k = S.knobs, cid = S.cid;
  view.innerHTML = `<div class="page">
    <div class="page-head"><div><h2>${esc(c.name)} · 한 해 실행 계획</h2><p>정한 예산·인력 안에서 검토 후보를 묶습니다. 값을 바꾸면 바로 다시 계산합니다.</p></div>
      <div class="row"><a class="btn" href="#/recommend">추천 목록</a></div></div>
    <div class="grid g-side">
      <aside class="panel ctrl"><h3>한도와 조건</h3>
        <div class="knob"><label for="pb">공단 쪽 연간 예산 <span class="num" id="pbv"></span></label><input id="pb" type="range" ${STATIC ? rng(S.meta.grid.budget) : 'min="0" max="3000000" step="50000"'} value="${p.budget}"><small class="muted">단지·공단·LH가 부담하는 몫의 합계(외부 후원 제외)</small></div>
        <div class="knob"><label for="ph">연간 인력 <span class="num" id="phv"></span></label><input id="ph" type="range" ${STATIC ? rng(S.meta.grid.hours) : 'min="10" max="240" step="5"'} value="${p.hours}"><small class="muted">직원·봉사자가 들이는 시간(명×시간)</small></div>
        <div class="knob"><label for="pn">프로그램 수 <span class="num" id="pnv"></span></label><input id="pn" type="range" ${STATIC ? rng(S.meta.grid.n_max) : 'min="1" max="10" step="1"'} value="${p.n_max}"></div>
        <div><div class="row between"><span style="font-weight:600;font-size:0.933rem">분야별 최소 개수</span><button class="btn sm ghost" id="pauto" data-tip="필요가 높은 두 분야에서 1개씩 넣는 기본 조건으로 되돌립니다">자동</button></div>
          <div id="pmin" style="display:grid;grid-template-columns:1fr auto;gap:4px 8px;margin-top:4px;font-size:0.933rem"></div></div>
        <div class="knob"><label for="pw">필요 반영 정도 <span class="num" id="pwv"></span></label><input id="pw" type="range" min="0" max="0.5" step="0.05" value="${k.w}" ${STATIC ? 'disabled' : ''}><small class="muted">추천 화면의 값과 같이 움직입니다</small></div>
        <div class="row between"><button class="btn sm ghost" id="preset">기본값으로</button><span class="ms" id="planMs"></span></div>${STATIC ? '<div class="muted" style="font-size:0.867rem">공개 시연판입니다. 예산·인력·프로그램 수를 미리 계산해 둔 단계로 바꿀 수 있습니다.</div>' : ''}
      </aside>
      <section class="grid" style="align-content:start">
        <div id="planNote"></div>
        <div class="panel"><h3>고른 묶음 <small class="muted" id="planCount"></small></h3><div id="planItems"></div>
          <div class="grid g2" style="margin-top:12px">
            <div><div class="row between"><b>공단 쪽 연간 비용</b><span class="num" id="gcT"></span></div><div class="gauge" id="gc"><span></span></div></div>
            <div><div class="row between"><b>연간 인력</b><span class="num" id="ghT"></span></div><div class="gauge" id="gh"><span></span></div></div>
          </div>
          <div class="muted" style="font-size:0.867rem;margin-top:8px">비용·인력은 전문가 검토값(1회 기준)에 단지당 연간 기록 수를 곱한 추정입니다. 실제 집행액이 아닙니다.</div></div>
        <div class="panel"><h3>달력 <small class="muted">다른 단지 기록에서 가장 많이 열린 달에 놓았습니다</small></h3><div class="cal" id="planCal"></div></div>
        <div class="panel"><h3>묶음 설명</h3>
          <div class="answer" id="brief"><span class="muted">묶음을 고르는 중</span></div></div>
      </section>
    </div></div>`;
  let cur = null;
  const body = () => ({ id: cid, w: k.w, lam: k.lam, budget: p.budget, hours: p.hours, n_max: p.n_max, min_domains: p.min_domains });
  const load = async () => {
    const my = ++lastReq;
    $('#pbv').textContent = Math.round(p.budget / 10000).toLocaleString() + '만 원'; $('#phv').textContent = p.hours + '명×시간'; $('#pnv').textContent = p.n_max + '개 이내'; $('#pwv').textContent = k.w.toFixed(2);
    const t0 = performance.now(), r = await post('plan', body()), rt = performance.now() - t0;
    if (my !== lastReq || !alive() || !$('#planItems')) return;
    cur = r;
    if (!STATIC) $('#planMs').innerHTML = `정수계획 <b>${r.solve_ms}ms</b> · 왕복 ${rt.toFixed(0)}ms`;
    $('#planMs').dataset.tip = `정수계획 풀이 ${r.solve_ms}ms\n서버 계산 전체 ${r.ms}ms\n브라우저 왕복 ${rt.toFixed(0)}ms\n후보 ${r.n_candidates}개에서 고름`;
    const notes = [];
    if (!r.feasible) notes.push('<div class="note bad"><b>조건을 모두 만족하는 묶음이 없습니다.</b> 예산·인력을 늘리거나 분야별 최소 개수를 줄여 보세요.</div>');
    if (r.relaxed) notes.push('<div class="note warn">분야별 최소 개수 조건은 한도 안에서 맞출 수 없어 뺐습니다.</div>');
    if (r.items.some(i => i.welfare_gap)) notes.push(`<div class="note warn">주거복지사가 있어야 하는 프로그램이 들어 있습니다(${r.items.filter(i => i.welfare_gap).map(i => esc(i.name)).join(', ')}). 이 단지는 미배치입니다.</div>`);
    $('#planNote').innerHTML = notes.join('');
    $('#planCount').textContent = `${r.n}개 / 후보 ${r.n_candidates}개 가운데`;
    const mc = Math.max(1, ...r.items.map(i => i.cost_year)), mh = Math.max(1, ...r.items.map(i => i.hours_year));
    $('#planItems').innerHTML = r.items.length ? `<table class="tbl"><thead><tr><th>프로그램</th><th>분야</th><th class="r">공단 쪽 연간 비용</th><th class="r">연간 인력</th><th class="r">난이도</th><th>많이 여는 달</th></tr></thead><tbody>${r.items.map(i => `<tr>
        <td><a href="#/programs/${i.std_id}">${esc(i.name)}</a>${i.welfare_gap ? ' <span class="chip warn">미배치 주의</span>' : ''}</td><td>${domChip(i.domain, i.domain_label)}</td>
        <td class="r num"><div>${f.man(i.cost_year)}</div><div class="gauge" style="height:4px"><span style="width:${(i.cost_year / mc * 100).toFixed(0)}%"></span></div></td>
        <td class="r num"><div>${f.n1(i.hours_year)}명×시간</div><div class="gauge" style="height:4px"><span style="width:${(i.hours_year / mh * 100).toFixed(0)}%"></span></div></td>
        <td class="r num">${i.difficulty}/5</td><td>${i.months.join('·')}월</td></tr>`).join('')}</tbody></table>` : '<div class="empty">고른 프로그램이 없습니다</div>';
    const g = (id, v, lim, txt) => { const el = $(id); el.classList.toggle('over', v > lim + 1e-6); el.firstElementChild.style.width = Math.min(100, lim ? v / lim * 100 : 0).toFixed(1) + '%'; $(id + 'T').textContent = txt; };
    g('#gc', r.cost, r.budget, `${Math.round(r.cost / 10000).toLocaleString()} / ${Math.round(r.budget / 10000).toLocaleString()}만 원`);
    g('#gh', r.hours, r.hours_limit, `${Math.round(r.hours)} / ${Math.round(r.hours_limit)}명×시간`);
    $('#planCal').innerHTML = Array.from({ length: 12 }, (_, i) => { const xs = r.calendar[i + 1] || []; return `<div class="${xs.length >= 2 ? 'busy' : ''}"><b>${i + 1}월${xs.length >= 2 ? ' · ' + xs.length + '개 겹침' : ''}</b>${xs.map(n => `<span>${esc(n)}</span>`).join('')}</div>`; }).join('');
    $('#pmin').innerHTML = S.meta.need_ids.map(d => `<span>${domChip(d)}</span><span class="seg" data-d="${d}">${[0, 1, 2].map(n => `<button data-n="${n}" class="${(r.min_domains[d] || 0) === n ? 'on' : ''}">${n}</button>`).join('')}</span>`).join('');
    briefSoon(r);
  };
  const reload = debounce(load, 40);
  const bind = (id, fn) => $(id).addEventListener('input', e => { fn(+e.target.value); reload(); });
  bind('#pb', v => (p.budget = v)); bind('#ph', v => (p.hours = v)); bind('#pn', v => (p.n_max = v)); bind('#pw', v => (k.w = v));
  $('#pmin').addEventListener('click', e => { const b = e.target.closest('button'); if (!b || !cur || STATIC) return; p.min_domains = { ...cur.min_domains, [b.parentElement.dataset.d]: +b.dataset.n }; load(); });
  $('#pauto').addEventListener('click', () => { p.min_domains = null; load(); });
  $('#preset').addEventListener('click', () => { Object.assign(p, { budget: S.meta.defaults.budget, hours: S.meta.defaults.hours, n_max: S.meta.defaults.n_max, min_domains: null }); k.w = S.meta.defaults.w; render(view, arg, alive); });
  // 묶음이 정해지고 0.9초 동안 더 바뀌지 않으면 설명을 자동으로 만든다(손잡이를 움직이는 동안에는 요청하지 않는다)
  let briefT = null, briefN = 0;
  const briefSoon = r => {
    clearTimeout(briefT); const my = ++briefN, el = $('#brief');
    if (!r.items.length) { el.textContent = '지금 조건으로는 고를 수 있는 프로그램이 없습니다. 예산이나 인력 한도를 늘려 보세요.'; return; }
    el.innerHTML = '<span class="muted"><span class="spin"></span> 설명을 쓰는 중</span>';
    briefT = setTimeout(async () => {
      try { const x = await post('llm/plan', body()); if (my === briefN && $('#brief')) $('#brief').textContent = x.text; }
      catch (err) { if (my === briefN && $('#brief')) $('#brief').textContent = '설명을 불러오지 못했습니다.'; }
    }, 900);
  };
  await load();
}
