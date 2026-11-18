import { STATIC, S, api, $, $$, esc, on, setComplex, initTip, buildToc } from './core.js';
import * as map from './tabs/map.js';
import * as complex from './tabs/complex.js';
import * as recommend from './tabs/recommend.js';
import * as plan from './tabs/plan.js';
import * as programs from './tabs/programs.js';
import * as cases from './tabs/cases.js';
import * as happycall from './tabs/happycall.js';
import * as analysis from './tabs/analysis.js';
import * as kg from './tabs/kg.js';
import * as about from './tabs/about.js';

const TABS = { map, complex, recommend, plan, programs, cases, happycall, analysis, kg, about };
const NEEDS_COMPLEX = new Set(['complex', 'recommend', 'plan', 'kg']);
const WITH_TOC = new Set(['complex', 'programs', 'happycall', 'analysis', 'about']);
const setTopH = () => document.documentElement.style.setProperty('--topH', document.querySelector('.top').offsetHeight + 'px');
addEventListener('resize', setTopH);
let current = null, token = 0;

async function route() {
  const [, tab = 'map', arg] = location.hash.split('/');
  const name = TABS[tab] ? tab : 'map';
  $$('#tabs a').forEach(a => a.classList.toggle('on', a.dataset.tab === name));
  const view = $('#view'), my = ++token;
  if (current && TABS[current].leave) TABS[current].leave();
  current = name;
  document.documentElement.classList.toggle('maptab', name === 'map');
  document.documentElement.classList.toggle('fullbleed', ['map', 'recommend', 'kg'].includes(name));   // 화면 전체를 쓰는 탭은 머리도 왼쪽 끝에 맞춘다      // 지도 화면만 전체를 90%로
  view.innerHTML = '<div class="page"><div class="panel empty"><span class="spin"></span> 불러오는 중</div></div>';
  try {
    await TABS[name].render(view, arg ? decodeURIComponent(arg) : undefined, () => my === token);
    setTopH();
    if (my === token) { if (WITH_TOC.has(name)) buildToc(view); else view.querySelector('.toc')?.remove(); }
  } catch (e) {
    if (my === token) view.innerHTML = `<div class="page"><div class="note bad"><b>화면을 그리지 못했습니다.</b> ${esc(e.message)}</div></div>`;
    console.error(e);
  }
  window.scrollTo(0, 0);
}

function picker() {
  const btn = $('#pickerBtn'), pop = $('#pickerPop'), input = $('#pickerInput'), list = $('#pickerList');
  const draw = () => {
    const q = input.value.trim();
    const rows = S.complexes.filter(c => !q || c.name.includes(q) || c.branch.includes(q)).slice(0, 60);
    list.innerHTML = rows.map(c => `<button data-id="${c.id}" role="option"><span>${esc(c.name)}</span><small>${esc(c.branch)}${c.has_records ? '' : ' · 기록 없음'}</small></button>`).join('') || '<div class="empty">찾는 단지가 없습니다</div>';
  };
  btn.addEventListener('click', () => { pop.hidden = !pop.hidden; if (!pop.hidden) { input.value = ''; draw(); input.focus(); } });
  input.addEventListener('input', draw);
  list.addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; pop.hidden = true; setComplex(b.dataset.id); });
  document.addEventListener('click', e => { if (!e.target.closest('#picker')) pop.hidden = true; });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') pop.hidden = true; });
}

async function llmDot() {
  const el = $('#llmDot');
  try {
    const s = await api('llm/status');
    S.llm = s;
    if (s.static) { el.className = 'llm ok'; el.dataset.tip = '공개 시연판입니다.\n로컬 LLM으로 미리 만들어 둔 문장과 점검표를 보여 줍니다.'; return; }
    el.className = 'llm ' + (s.available ? 'ok' : 'off');
    el.dataset.tip = s.available ? `로컬 LLM 사용 가능(${s.model})\n근거 문장 다듬기와 실행 점검표 생성에 씁니다. 계산에는 쓰지 않습니다.` : `로컬 LLM에 연결할 수 없습니다.\n문장은 규칙으로 만든 기본값을 보여 줍니다.\n${s.error || ''}`;
  } catch { el.className = 'llm off'; }
}

// 강조색 시안(고르는 중): 로컬 판에서만 머리 오른쪽에 선택 상자를 띄운다. 정해지면 app.css의 --accent를 바꾸고 이 부분을 지운다.
const ACCENTS = [['#1f6f8b', '지금 색(청록)'], ['#1d3557', '남색'], ['#2b59c3', '로열 블루'], ['#0f766e', '틸'], ['#1e6f50', '진초록'], ['#5b3fa0', '보라'], ['#8c2f5f', '자주'], ['#9b2c2c', '와인'], ['#b5532a', '테라코타'], ['#8a5a14', '황토'], ['#2f3742', '차콜']];
function accentTrial() {
  const set = c => { const r = document.documentElement.style; r.setProperty('--accent', c); r.setProperty('--accent-soft', `color-mix(in srgb, ${c} 12%, #fff)`); try { localStorage.setItem('onter.accent', c); } catch { } };
  let cur = ACCENTS[0][0]; try { cur = localStorage.getItem('onter.accent') || cur; } catch { }
  const sel = document.createElement('select'); sel.className = 'acctrial'; sel.setAttribute('aria-label', '강조색 시안');
  sel.innerHTML = ACCENTS.map(([c, n], i) => `<option value="${c}" ${c === cur ? 'selected' : ''}>강조색 ${i + 1} ${n}</option>`).join('');
  sel.addEventListener('input', () => set(sel.value));
  $('.top-right').prepend(sel); set(cur);
}

(async function start() {
  initTip(); picker();
  if (!STATIC) accentTrial();
  try {
    [S.meta, S.complexes] = await Promise.all([api('meta'), api('complexes')]);
  } catch (e) {
    $('#view').innerHTML = `<div class="page"><div class="note bad"><b>서버에 연결할 수 없습니다.</b> ${esc(e.message)}</div></div>`; return;
  }
  S.byId = Object.fromEntries(S.complexes.map(c => [c.id, c]));
  Object.assign(S.knobs, { w: S.meta.defaults.w, lam: S.meta.defaults.lam, k: S.meta.defaults.k });
  Object.assign(S.plan, { budget: S.meta.defaults.budget, hours: S.meta.defaults.hours, n_max: S.meta.defaults.n_max });
  if (!S.meta.kg && $('#tabs a[data-tab=kg]')) $('#tabs a[data-tab=kg]').dataset.tip = 'Knowledge Graph 자료가 없습니다';
  on('complex', cid => {
    $('#pickerName').textContent = S.byId[cid].name; $('#pickerBtn').classList.add('has');
    if (NEEDS_COMPLEX.has(current)) route(); else if (current === 'map') map.select(cid);
  });
  let saved = null; try { saved = localStorage.getItem('onter.cid'); } catch { }
  if (saved && S.byId[saved]) { S.cid = saved; $('#pickerName').textContent = S.byId[saved].name; $('#pickerBtn').classList.add('has'); }
  window.addEventListener('hashchange', route);
  if (!location.hash) location.hash = '#/map'; else route();
  llmDot(); setInterval(llmDot, 60000);
})();
