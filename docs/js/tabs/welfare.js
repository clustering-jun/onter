// 정부·지자체 복지서비스: 한국사회보장정보원 목록(중앙부처·지자체). 복지 프로그램 사전 탭 안의 한 화면이고, 단지 현황에는 그 지역 것만 추려 보여 준다.
// 공단이 여는 프로그램이 아니라 주민에게 안내할 수 있는 공공 서비스다. 추천 계산에는 쓰지 않는다.
import { S, api, cached, $, $$, esc, f, debounce } from '../core.js';

const st = { q: '', scope: 'all', sido: '', sgg: '', life: '', theme: '', target: '', n: 30 };
const load = () => cached('welfare', () => api('welfare'));
const uniq = (rows, k) => [...new Set(rows.flatMap(r => r[k]))].sort((a, b) => a.localeCompare(b, 'ko'));
const place = r => r.sido ? `${r.sido}${r.sgg ? ' ' + r.sgg : ''}` : '';
export function setRegion(sido, sgg) { Object.assign(st, { sido: sido || '', sgg: sgg || '', scope: 'local', q: '', life: '', theme: '', target: '', n: 30 }); }

// 지자체 서비스 가운데 이 지역에 해당하는 것: 시군구가 같거나, 시도 전체에 해당하는 것(시군구가 비어 있음)
const inRegion = (r, sido, sgg) => r.sido === sido && (!sgg || !r.sgg || r.sgg === sgg);

const card = r => `<div class="pgcard wfcard">
    <div class="row between"><span class="chip ${r.sido ? '' : 'ok'}">${r.sido ? esc(place(r)) : '중앙부처'}</span><span class="muted">조회 ${f.int(r.views)}</span></div>
    <h4>${esc(r.name)}</h4>
    <div class="muted">${esc(r.org)}</div>
    <p>${esc(r.digest)}</p>
    <div class="row">${[...r.life.map(x => `<span class="chip">${esc(x)}</span>`), ...r.target.map(x => `<span class="chip warn">${esc(x)}</span>`), ...r.theme.slice(0, 3).map(x => `<span class="chip dom none">${esc(x)}</span>`)].join('')}</div>
    <div class="pgmeta">${[r.cycle && `지원 주기 <b>${esc(r.cycle)}</b>`, r.kind && `제공 <b>${esc(r.kind)}</b>`, r.apply && `신청 <b>${esc(r.apply)}</b>`, r.online && '<b>온라인 신청 가능</b>', r.tel && `문의 <b>${esc(r.tel)}</b>`].filter(Boolean).map(x => `<span>${x}</span>`).join('')}</div>
    <div class="row" style="margin-top:10px"><a class="btn sm" href="${esc(r.link)}" target="_blank" rel="noopener">복지로에서 자세히 ↗</a></div>
  </div>`;

export const modeToggle = on => `<span class="seg" id="pgMode"><button data-m="" class="${on === 'programs' ? 'on' : ''}">공단 프로그램</button><button data-m="welfare" class="${on === 'welfare' ? 'on' : ''}">정부·지자체 복지서비스</button></span>`;
export const bindToggle = () => $('#pgMode').addEventListener('click', e => { const b = e.target.closest('button'); if (b && !b.classList.contains('on')) location.hash = '#/programs' + (b.dataset.m ? '/' + b.dataset.m : ''); });

export async function render(view, alive) {
  const w = await load();
  if (!alive()) return;
  if (!w.meta) {
    view.innerHTML = `<div class="page"><div class="page-head"><div><h2>정부·지자체 복지서비스</h2></div>${modeToggle('welfare')}</div><div class="note warn"><b>복지서비스 자료가 없습니다.</b> <code>python tools/welfare_services/fetch.py</code>로 받은 뒤 서버를 다시 시작하십시오.</div></div>`;
    bindToggle(); return;
  }
  const all = [...w.central, ...w.local], sidos = [...new Set(w.local.map(r => r.sido))].sort((a, b) => a.localeCompare(b, 'ko'));
  const c = S.cid ? S.byId[S.cid] : null;
  const opt = (vals, cur, first) => `<option value="">${first}</option>${vals.map(v => `<option ${v === cur ? 'selected' : ''}>${esc(v)}</option>`).join('')}`;
  view.innerHTML = `<div class="page">
    <div class="page-head"><div><h2>정부·지자체 복지서비스</h2><p>주민에게 안내할 수 있는 공공 복지서비스입니다. 중앙부처 ${f.int(w.central.length)}건, 지자체 ${f.int(w.local.length)}건 · 한국사회보장정보원 ${esc(w.meta.fetched)} 기준</p></div>${modeToggle('welfare')}</div>
    <div class="panel pgtool">
      <input id="wfQ" type="search" placeholder="서비스 이름이나 내용으로 찾기 (예: 난방비, 돌봄, 틀니, 일자리)" value="${esc(st.q)}">
      <div class="row">
        <span class="seg" id="wfScope">${[['all', '전체'], ['central', '중앙부처'], ['local', '지자체']].map(([k, t]) => `<button data-s="${k}" class="${st.scope === k ? 'on' : ''}">${t}</button>`).join('')}</span>
        <select id="wfSido" aria-label="시도">${opt(sidos, st.sido, '시도 전체')}</select>
        <select id="wfSgg" aria-label="시군구"></select>
        <select id="wfLife" aria-label="생애주기">${opt(uniq(all, 'life'), st.life, '생애주기 전체')}</select>
        <select id="wfTarget" aria-label="대상">${opt(uniq(all, 'target'), st.target, '대상 전체')}</select>
        <select id="wfTheme" aria-label="관심 주제">${opt(uniq(all, 'theme'), st.theme, '주제 전체')}</select>
        ${c ? `<button class="btn sm" id="wfMine">${esc(c.name)} 지역으로</button>` : ''}<button class="btn sm ghost" id="wfReset">조건 지우기</button>
      </div>
    </div>
    <div class="muted" id="wfCount"></div>
    <div class="pggrid" id="wfGrid"></div>
    <div class="row" style="justify-content:center;margin-top:14px"><button class="btn" id="wfMore">더 보기</button></div></div>`;
  bindToggle();
  const sggs = () => { const v = [...new Set(w.local.filter(r => r.sido === st.sido && r.sgg).map(r => r.sgg))].sort((a, b) => a.localeCompare(b, 'ko')); $('#wfSgg').innerHTML = opt(v, st.sgg, st.sido ? '시군구 전체' : '시도를 먼저 고르세요'); $('#wfSgg').disabled = !st.sido; };
  const draw = () => {
    const q = st.q.replace(/\s/g, ''), hit = r => !q || (r.name + r.digest + r.org).replace(/\s/g, '').includes(q);
    const tag = r => (!st.life || r.life.includes(st.life)) && (!st.target || r.target.includes(st.target)) && (!st.theme || r.theme.includes(st.theme));
    const rows = [...(st.scope === 'local' ? [] : w.central), ...(st.scope === 'central' ? [] : w.local.filter(r => !st.sido || inRegion(r, st.sido, st.sgg)))].filter(r => hit(r) && tag(r))
      .sort((a, b) => (st.sgg ? (b.sgg === st.sgg) - (a.sgg === st.sgg) : 0) || b.views - a.views);
    $('#wfCount').textContent = `${f.int(rows.length).replace(/<[^>]+>/g, '')}건 · 조회가 많은 순${st.sgg ? ' (고른 시군구의 서비스 먼저)' : ''}${st.sido && st.scope !== 'central' ? ' · 시도 전체에 해당하는 서비스 포함' : ''}`;
    $('#wfGrid').innerHTML = rows.slice(0, st.n).map(card).join('') || '<div class="empty">조건에 맞는 서비스가 없습니다</div>';
    $('#wfMore').hidden = rows.length <= st.n;
    $$('#wfScope button').forEach(b => b.classList.toggle('on', b.dataset.s === st.scope));
  };
  const on = (id, k) => $(id).addEventListener('input', e => { st[k] = e.target.value; st.n = 30; if (k === 'sido') { st.sgg = ''; sggs(); } draw(); });
  on('#wfSido', 'sido'); on('#wfSgg', 'sgg'); on('#wfLife', 'life'); on('#wfTarget', 'target'); on('#wfTheme', 'theme');
  $('#wfQ').addEventListener('input', debounce(e => { st.q = e.target.value.trim(); st.n = 30; draw(); }, 150));
  $('#wfScope').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; st.scope = b.dataset.s; st.n = 30; draw(); });
  $('#wfMore').addEventListener('click', () => { st.n += 30; draw(); });
  $('#wfReset').addEventListener('click', () => { Object.assign(st, { q: '', scope: 'all', sido: '', sgg: '', life: '', theme: '', target: '', n: 30 }); render(view, alive); });
  if (c) $('#wfMine').addEventListener('click', () => { setRegion(c.sido, c.sgg); render(view, alive); });
  sggs(); draw();
}

// 단지 현황에 넣는 요약: 이 단지가 있는 시군구·시도의 서비스 수와 많이 찾는 것 몇 개
export async function panel(el, cid) {
  const w = await load(), c = S.byId[cid];
  if (!el.isConnected) return;
  if (!w.meta) { el.innerHTML = '<span class="muted">복지서비스 자료가 없습니다.</span>'; return; }
  const here = w.local.filter(r => r.sido === c.sido && r.sgg === c.sgg), wide = w.local.filter(r => r.sido === c.sido && !r.sgg);
  const top = (rows, n) => [...rows].sort((a, b) => b.views - a.views).slice(0, n);
  const line = r => `<a class="wfline" href="${esc(r.link)}" target="_blank" rel="noopener"><b>${esc(r.name)}</b><span>${esc(r.digest)}</span><span class="row">${[...r.life, ...r.target].slice(0, 4).map(x => `<span class="chip">${esc(x)}</span>`).join('')}${r.kind ? `<span class="muted">${esc(r.kind)}</span>` : ''}</span></a>`;
  const senior = rows => rows.filter(r => r.life.includes('노년'));
  el.innerHTML = `<div class="tiles" style="grid-template-columns:repeat(3,1fr)">
      <div class="tile"><span>${esc(c.sgg || '')}</span><b class="num">${f.int(here.length)}</b><span>시군구 서비스</span></div>
      <div class="tile"><span>${esc(c.sido || '')}</span><b class="num">${f.int(wide.length)}</b><span>시도 서비스</span></div>
      <div class="tile"><span>전국</span><b class="num">${f.int(w.central.length)}</b><span>중앙부처 서비스</span></div></div>
    <div class="grid g2" style="margin-top:14px">
      <div><h4>${esc(c.sgg || c.sido)}에서 많이 찾는 서비스</h4>${top(here.length ? here : wide, 5).map(line).join('') || '<span class="muted">등록된 서비스가 없습니다</span>'}</div>
      <div><h4>어르신 대상 서비스 <small class="muted">이 지역 + 중앙부처</small></h4>${top([...senior(here), ...senior(wide), ...senior(w.central)], 5).map(line).join('')}</div>
    </div>
    <div class="row" style="margin-top:12px"><button class="btn sm pri" id="wfAll">이 지역 서비스 모두 보기</button><span class="muted" style="font-size:0.867rem">한국사회보장정보원 ${esc(w.meta.fetched)} 기준 · 누르면 복지로로 이동합니다 · 추천 계산에는 쓰지 않습니다</span></div>`;
  el.querySelector('#wfAll').addEventListener('click', () => { setRegion(c.sido, c.sgg); location.hash = '#/programs/welfare'; });
}
