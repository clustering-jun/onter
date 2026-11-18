// 공통: API, 상태, 표시 도우미, 작은 그림 부품
import { sget, spost } from './static.js';
export const STATIC = !!window.ONTER_STATIC;   // 정적 판(GitHub Pages). tools/build_static.py가 index.html에 켜 둔다
export const S = { meta: null, complexes: [], byId: {}, cid: null, knobs: { w: 0.2, lam: 0.25, k: 10, domain: '' }, plan: { budget: 1e6, hours: 80, n_max: 6, min_domains: null }, cache: {} };
const subs = {};
export const on = (ev, fn) => (subs[ev] = subs[ev] || []).push(fn);
export const emit = (ev, v) => (subs[ev] || []).forEach(f => f(v));

export async function api(path, params) {
  if (STATIC) return sget(path, params || {});
  const qs = params ? '?' + new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))) : '';
  const r = await fetch('api/' + path + qs);
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || '자료를 불러오지 못했습니다.');
  return d;
}
export async function post(path, body) {
  if (STATIC) return spost(path, body || {});
  const r = await fetch('api/' + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || '요청을 처리하지 못했습니다.');
  return d;
}
export async function cached(key, fn) { return S.cache[key] || (S.cache[key] = await fn()); }

export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];
export const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const NA = '<span class="na">자료 없음</span>';
const isNum = v => typeof v === 'number' && isFinite(v);
export const f = {
  int: v => isNum(v) ? Math.round(v).toLocaleString('ko-KR') : NA,
  n1: v => isNum(v) ? v.toLocaleString('ko-KR', { maximumFractionDigits: 1 }) : NA,
  n2: v => isNum(v) ? v.toLocaleString('ko-KR', { maximumFractionDigits: 2 }) : NA,
  pct: v => isNum(v) ? Math.round(v * 100) + '%' : NA,
  pct1: v => isNum(v) ? (v * 100).toFixed(1) + '%' : NA,
  man: v => isNum(v) ? (v < 10000 ? '거의 없음' : '약 ' + Math.round(v / 10000).toLocaleString('ko-KR') + '만 원') : NA,
  km: v => isNum(v) ? (v < 1 ? Math.round(v * 1000) + 'm' : v.toFixed(1) + 'km') : NA,
  top: v => isNum(v) ? '상위 ' + Math.max(1, Math.round((1 - v) * 100)) + '%' : NA,
  ym: v => v ? String(v).replace('-', '.') : NA,
};
export const DOM = { N1: '#2a78d6', N2: '#eb6834', N3: '#1baa83', N4: '#8a63d2', N5: '#d4a418', N6: '#d95a8c' };
export const TYPE_COLOR = { S1: '#2a9d8f', S2: '#e76f51', S3: '#264653' };   // 청록·테라코타·짙은 남청
export const domChip = (d, label) => `<span class="chip dom ${d || 'none'}">${esc(label || (S.meta.needs[d] || '여러 분야'))}</span>`;
export const stChip = (s, label) => `<span class="st ${s}">${esc(label || S.meta.status[s] || s)}</span>`;

export function toast(msg, ms = 2600) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms);
}
export function debounce(fn, ms = 80) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

// 마우스를 올리면 보이는 설명(data-tip). 점수처럼 평소엔 감춰 둘 값을 여기에 둔다.
export function initTip() {
  const tip = $('#tip');
  document.addEventListener('mouseover', e => {
    const el = e.target.closest('[data-tip]'); if (!el) return;
    tip.textContent = el.dataset.tip; tip.hidden = false;
    const r = el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(6, Math.min(innerWidth - w - 6, r.left + r.width / 2 - w / 2)) + 'px';
    tip.style.top = (r.top - h - 8 < 4 ? r.bottom + 8 : r.top - h - 8) + 'px';
  });
  document.addEventListener('mouseout', e => { if (e.target.closest('[data-tip]')) tip.hidden = true; });
  document.addEventListener('focusin', e => { const el = e.target.closest('[data-tip]'); if (el) el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })); });
  document.addEventListener('focusout', () => (tip.hidden = true));
}

export function setComplex(cid, go) {
  if (cid && S.byId[cid]) { S.cid = cid; try { localStorage.setItem('onter.cid', cid); } catch { } emit('complex', cid); }
  if (go) location.hash = '#/' + go;
}
export const cx = () => S.byId[S.cid];
export const needPick = (title = '단지를 먼저 선택하세요') => `<div class="page"><div class="panel empty"><h3 style="justify-content:center">${esc(title)}</h3><p>위 오른쪽의 단지 선택 상자에서 찾거나, <a href="#/map">지도</a>에서 단지를 누르세요.</p></div></div>`;

// ───────── 작은 그림 부품 ─────────
// 위치 표현: 백분위 p(0~1, 클수록 값이 큼) → "상위 12%" / "하위 30%"
export const pos = p => p == null ? '' : p >= 0.5 ? `상위 ${Math.max(1, Math.round((1 - p) * 100))}%` : `하위 ${Math.max(1, Math.round(p * 100))}%`;

// 월별 막대 차트. 세로축 눈금과 해(연도) 구분. 막대에 마우스를 올리면 '2025년 3월: 4건'처럼 보인다.
export function monthBars(vals, labels, { h = 110, unit = '건', color = 'var(--accent)', showValues = false, title = '' } = {}) {
  if (!vals || !vals.length) return `<div class="muted">기록 없음</div>`;
  const nums = vals.map(v => v == null ? 0 : v), max = Math.max(1, ...nums);
  const step = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000].find(x => max / x <= 4) || 10000, top = Math.ceil(max / step) * step;
  const ticks = []; for (let v = top; v >= 0; v -= step) ticks.push(v);
  const cols = vals.map((v, i) => {
    const [y, m] = String(labels[i]).split('-'), jan = m === '01';
    const tip = `${y}년 ${+m}월: ${v == null ? '자료 없음' : v.toLocaleString() + unit}`;
    return `<span class="col${jan && i ? ' yr' : ''}" data-tip="${tip}">${showValues && v ? `<b>${v}</b>` : ''}<i style="height:${v == null ? 0 : (v / top * 100).toFixed(1)}%;background:${v == null ? 'transparent' : color}"></i></span>`;
  }).join('');
  const xl = labels.map((l, i) => { const [y, m] = String(l).split('-'); return `<span class="${m === '01' && i ? 'yr' : ''}">${m === '01' || i === 0 ? `<b>${y}</b>` : (+m % 3 === 1 ? +m : '')}</span>`; }).join('');
  return `<div class="mbar" role="img" aria-label="${esc(title || '월별 막대 차트')}">
    <div class="yax" style="height:${h}px">${ticks.map(t => `<span>${t.toLocaleString()}</span>`).join('')}</div>
    <div class="plot"><div class="bars" style="height:${h}px;background-size:100% ${(100 / (ticks.length - 1)).toFixed(3)}%">${cols}</div><div class="xax">${xl}</div></div>
  </div>`;
}
// 순위 위치 막대: 왼쪽 낮음 ~ 오른쪽 높음, 가운데 선은 중앙
export const posBar = (p, color = 'var(--accent)') => `<div class="posbar"><span class="mid"></span><span class="dot" style="left:${(Math.max(0, Math.min(1, p)) * 100).toFixed(1)}%;background:${color}"></span></div>`;
export function hbars(rows, { max, color = 'var(--accent)', fmt = v => v } = {}) {   // rows: [{label, value, color?, tip?}]
  const m = max || Math.max(1e-9, ...rows.map(r => r.value || 0));
  return `<div class="hb">${rows.map(r => `<span${r.tip ? ` data-tip="${esc(r.tip)}"` : ''}>${r.html || esc(r.label)}</span><span class="bg"><span class="bar" style="display:block;width:${Math.max(0, Math.min(100, (r.value || 0) / m * 100)).toFixed(1)}%;background:${r.color || color}"></span></span><span class="v num">${r.value == null ? NA : fmt(r.value)}</span>`).join('')}</div>`;
}
export function stack(parts) {   // parts: {N1: 0.2, ...}
  const ids = S.meta.need_ids, tot = ids.reduce((a, d) => a + (parts[d] || 0), 0) || 1;
  return `<div class="stack">${ids.map(d => `<span style="width:${((parts[d] || 0) / tot * 100).toFixed(1)}%;background:${DOM[d]}" data-tip="${esc(S.meta.needs[d])} ${Math.round((parts[d] || 0) / tot * 100)}%"></span>`).join('')}</div>`;
}
export const domLegend = () => `<div class="row" style="gap:10px;font-size:0.867rem">${S.meta.need_ids.map(d => `<span><i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${DOM[d]};margin-right:4px"></i>${esc(S.meta.needs[d])}</span>`).join('')}</div>`;

// 필요 지수 막대: 점(지수) + 띠(5~95% 구간) + 삼각형(현재 공급). 구간이 넓으면 흐리게.
export function needChart(rows, { controls = false } = {}) {
  const lv = { high: 0.9, mid: 0.5, low: 0.1 }, lvKo = { high: '높음', mid: '보통', low: '낮음' };
  return `<div class="need">${rows.map(r => {
    const c = DOM[r.domain], un = r.uncertain && !r.confirmed;
    const tipTxt = `${r.label}\n필요 지수: 전체 단지 중 ${f.top(r.need).replace(/<[^>]+>/g, '')}\n가중치·지표를 바꿨을 때 구간: ${Math.round(r.lo * 100)}~${Math.round(r.hi * 100)}${r.uncertain ? '\n구간이 넓어 불확실한 분야입니다.' : ''}\n현재 공급: ${r.supply_pct == null ? '기록 없음' : '백분위 ' + Math.round(r.supply_pct * 100)}\n지표: ${r.indicators.map(i => i.label).join(', ')}`;
    return `<div class="lab"><i class="sw" style="background:${c}"></i>${esc(r.label)}</div>
      <div class="track ${un ? 'uncertain' : ''}" data-tip="${esc(tipTxt)}">
        <span class="band" style="left:${(r.lo * 100).toFixed(1)}%;width:${Math.max(1, (r.hi - r.lo) * 100).toFixed(1)}%;background:${c}"></span>
        <span class="pt" style="left:${(r.need * 100).toFixed(1)}%;background:${c}"></span>
        ${r.supply_pct == null ? '' : `<span class="sup" style="left:${(r.supply_pct * 100).toFixed(1)}%"></span>`}
        ${r.confirmed ? `<span class="conf" style="left:${lv[r.confirmed] * 100}%"></span>` : ''}
      </div>
      <div class="meta"><span class="num">${f.top(r.need)}</span></div>
      ${(un || r.priority || r.confirmed || controls) ? `<div class="confrow">
        ${un ? '<span class="chip faded" data-tip="지표 가중치에 따라 순위가 크게 달라지는 분야입니다. 참고로만 보세요.">불확실</span>' : ''}
        ${r.priority ? '<span class="chip warn" data-tip="필요는 상위 1/3인데 공급은 하위 1/3인 분야">우선 검토</span>' : ''}
        ${r.confirmed ? `<span class="chip acc" data-tip="${esc('현장에서 확인한 필요' + (r.confirmed_note ? ': ' + r.confirmed_note : ''))}">확인 ${lvKo[r.confirmed]}</span>` : ''}
        ${controls ? `<span class="muted">현장 확인</span><span class="seg" data-domain="${r.domain}">${[['', '미확인'], ['low', '낮음'], ['mid', '보통'], ['high', '높음']].map(([k, t]) => `<button data-level="${k}" class="${(r.confirmed || '') === k ? 'on' : ''}">${t}</button>`).join('')}</span>${r.confirmed_note ? `<span class="muted">${esc(r.confirmed_note)}</span>` : ''}` : ''}</div>` : ''}`;
  }).join('')}</div><div class="axis" style="margin-left:138px"><span>필요 낮음</span><span>● 필요 지수 · ▬ 불확실 구간 · ▼ 현재 공급${rows.some(r => r.confirmed) ? ' · ┊ 확인된 필요' : ''}</span><span>높음</span></div>`;
}

// 해피콜 만족도 블록: 전체 관리소와 견준 위치, 응답 수가 적으면 강조
export function happycallBlock(hc, { full = false } = {}) {
  if (hc.status === 'no_link') return `<div class="note">${esc(hc.label)}</div>`;
  const rows = [['overall', '종합 만족도'], ['housing', '주택관리'], ['rental', '임대운영'], ['welfare', '복지']].filter(([k]) => full || k === 'overall' || k === 'welfare');
  const line = ([k, lab]) => {
    const c = hc.compare[k];
    if (!c) return `<div class="hcrow"><span class="lab">${lab}</span><span class="na">${k === 'welfare' ? '복지 서비스를 이용한 응답자가 없어 값이 없습니다' : '자료 없음'}</span></div>`;
    const up = c.diff >= 0;
    return `<div class="hcrow" data-tip="${lab} ${c.value.toFixed(1)}점\n값이 있는 관리소 ${c.of}곳의 평균 ${c.mean.toFixed(1)}점\n${c.of}곳 가운데 ${c.rank}위(높은 순)">
      <span class="lab">${lab}</span><b class="num">${c.value.toFixed(1)}</b>${posBar(1 - c.top_pct, up ? 'var(--ok)' : 'var(--warn)')}
      <span class="cmp ${up ? 'up' : 'down'}">평균보다 ${Math.abs(c.diff).toFixed(1)}점 ${up ? '높음' : '낮음'} · ${c.of}곳 중 ${c.rank}위</span></div>`;
  };
  const nNote = hc.small_sample
    ? `<div class="note bad"><b>응답 ${f.int(hc.n)}명</b> (30명 미만이라 점수는 참고만)</div>`
    : `<div class="muted" style="font-size:0.867rem">응답 ${f.int(hc.n)}명(관리소 중앙값 ${f.int(hc.n_median)}명)</div>`;
  const shared = hc.status === 'shared' ? `<div class="note warn">${esc(hc.label)}. 아래는 관리소(${esc(hc.office)}) 전체의 값입니다.</div>` : '';
  return `${shared}${rows.map(line).join('')}<div class="axis" style="margin:2px 0 6px"><span>낮은 쪽</span><span>│ 가운데 = 전체 관리소의 중앙</span><span>높은 쪽</span></div>${nNote}`;
}

// 단지 카드(지도 옆과 단지 현황 맨 위에서 같이 쓴다)
export function complexCard(d, { actions = true } = {}) {
  const b = d.basics, a = d.activity, p = d.pct || {}, ex = d.extra;
  const ages = d.age_bands, tot = ages.reduce((s, x) => s + (x.n || 0), 0) || 1;
  const grp = [['20세 미만', ['10대미만', '10대'], '#8fc1ee'], ['20~59세', ['20대', '30대', '40대', '50대'], '#5b9bd9'], ['60~79세', ['60대', '70대'], '#eb9a6a'], ['80세 이상', ['80대', '90대', '100대'], '#c9521f']]
    .map(([l, bs, c]) => [l, ages.filter(x => bs.includes(x.band)).reduce((s, x) => s + (x.n || 0), 0) / tot, c]);
  const near = d.near.filter(x => ['경로당', '노인복지관', '종합사회복지관', '보건기관', '병원'].includes(x.label));
  const tile = (v, lab, sub, key, tip) => `<div class="tile"${tip ? ` data-tip="${esc(tip)}"` : ''}><b class="num">${v}</b><span>${lab}</span><em>${sub || '&nbsp;'}</em>${key && p[key] != null ? `<em class="rank">${S.complexes.length}곳 중 ${pos(p[key])}</em>` : ''}</div>`;
  const needTop = [...d.need].sort((x, y) => y.need - x.need).slice(0, 3);
  const tmax = Math.max(1, ...a.top.map(t => t.n));
  return `<div class="ccard">
    <div class="chead"><h2>${esc(d.name)}</h2>
      <div class="tags"><span class="chip" style="background:${TYPE_COLOR[d.type]};color:#fff" data-tip="${esc(d.type_label + '\n' + (d.type_desc || ''))}">${esc(d.type_label)} ⓘ</span>
      ${b.deployed ? '<span class="chip ok">주거복지사 배치</span>' : '<span class="chip warn">주거복지사 미배치</span>'}</div></div>
    <div class="sub">${esc(d.branch)} · ${esc(d.region)} · ${esc(d.supply)}</div><div class="addr">${esc(d.addr || '')}</div>
    <div class="sec tiles six">
      ${tile(f.int(b.hh), '세대', `주민 ${f.int(b.pop)}명`, 'hh')}
      ${tile(f.pct(b.age60), '60세 이상', `70세 이상 ${f.pct(b.age70)}`, 'age60')}
      ${tile(f.pct(b.age80), '80세 이상', `20세 미만 ${f.pct(b.age_u20)}`, 'age80')}
      ${tile(f.n2(b.pph) + '명', '세대당 인구', b.pph != null && b.pph < 1.5 ? '혼자 사는 세대가 많음' : b.pph != null && b.pph >= 2.3 ? '가족 세대가 많음' : '', null, '세대당 인구가 1에 가까울수록 1인 가구가 많습니다. 단지별 1인 가구 수 자료는 없어 이 값으로 가늠합니다.')}
      ${tile(f.int(b.years) + '년', '입주 후', b.heating ? esc(b.heating) : '', 'years')}
      ${tile(f.pct(b.small_unit), '40㎡ 미만 세대', `평균 전용 ${f.n1(b.area_avg)}㎡`, 'small_unit')}
    </div>
    <div class="sec"><h4>연령 구성</h4><div class="agebar">${grp.map(([l, v, c]) => `<span style="width:${(v * 100).toFixed(1)}%;background:${c}" data-tip="${l} ${Math.round(v * 100)}% (${Math.round(v * tot).toLocaleString()}명)"></span>`).join('')}</div>
      <div class="row" style="gap:10px;font-size:0.867rem;margin-top:3px">${grp.map(([l, v, c]) => `<span><i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${c};margin-right:3px"></i>${l} ${Math.round(v * 100)}%</span>`).join('')}</div></div>
    <div class="sec"><h4>필요가 커 보이는 분야</h4>
      <div class="row">${needTop.map(n => `<span class="chip dom ${n.domain}" style="${n.uncertain ? 'opacity:.55' : ''}" data-tip="${esc(n.label)}: 전체 단지 중 ${pos(n.need)}${n.uncertain ? '\n구간이 넓어 불확실한 분야입니다' : ''}${n.supply_pct == null ? '' : '\n현재 공급 백분위 ' + Math.round(n.supply_pct * 100)}">${esc(n.label)} ${pos(n.need)}${n.uncertain ? ' · 불확실' : ''}</span>`).join('')}
        ${d.need.filter(n => n.priority).map(n => `<span class="chip warn" data-tip="필요는 상위 1/3인데 프로그램 공급은 하위 1/3인 분야">우선 검토: ${esc(n.label)}</span>`).join('')}</div></div>
    <div class="sec"><h4>단지 안 공간</h4><dl class="kv spaces2">
      <dt>있음</dt><dd>${d.spaces.filter(x => x.has).map(x => `<span${x.operator ? ` data-tip="운영: ${esc(x.operator)}"` : ''}>${esc(x.label)}</span>`).join(' · ') || '<span class="muted">없음</span>'}</dd>
      ${d.spaces.some(x => !x.has) ? `<dt class="muted">없음</dt><dd class="muted">${d.spaces.filter(x => !x.has).map(x => esc(x.label)).join(' · ')}</dd>` : ''}</dl></div>
    <div class="sec"><h4>가까운 시설까지</h4><dl class="kv">${near.map(x => `<dt>${esc(x.label)}</dt><dd class="num">${f.km(x.km)}</dd>`).join('')}</dl></div>
    <div class="sec"><h4>프로그램 운영 <small class="muted">${esc(S.meta.months[0])}~${esc(S.meta.months.at(-1))} 활동 기록</small></h4>
      ${d.has_records ? `<div class="tiles"><div class="tile"><b class="num">${f.int(a.n_records)}건</b><span>활동 기록</span><em>최근 12개월 ${f.int(a.n_recent12)}건</em>${p.n_records != null ? `<em class="rank">기록 있는 단지 중 ${pos(p.n_records)}</em>` : ''}</div>
        <div class="tile"><b class="num">${f.int(a.richness)}종</b><span>프로그램 종류</span><em>96종 가운데</em>${p.richness != null ? `<em class="rank">기록 있는 단지 중 ${pos(p.richness)}</em>` : ''}</div>
        <div class="tile"><b class="num">${f.pct(a.active_month_ratio)}</b><span>기록이 있는 달</span><em>마지막 기록 ${f.ym(a.last_month)}</em></div></div>
        <h4 style="margin-top:10px">월별 활동 기록 수</h4>
        ${monthBars(a.monthly, a.months, { h: 84, title: '월별 활동 기록 수' })}
        <h4 style="margin-top:10px">많이 한 프로그램</h4>
        <div class="toplist">${a.top.slice(0, 5).map(t => `<div><a href="#/programs/${t.std_id}">${esc(t.name)}</a><span class="bg"><span style="width:${(t.n / tmax * 100).toFixed(0)}%"></span></span><b class="num">${t.n}건</b><small>${t.last ? '마지막 ' + f.ym(t.last) : ''}</small></div>`).join('')}</div>`
      : `<div class="note warn"><b>기록 없음.</b> 이 단지는 활동 기록 자료에 없습니다. 프로그램을 안 한 것인지 기록이 없는 것인지 알 수 없어 '미운영'으로 보지 않습니다.</div>`}</div>
    <div class="sec"><h4>돌봄·협력 기록</h4><dl class="kv">
      <dt>관리홈닥터 지원(100세대당 월)</dt><dd class="num">${f.n1(d.home_doctor.per100)}건${p.hd != null ? ` <small class="muted">${pos(p.hd)}</small>` : ''}</dd>
      <dt data-tip="관리 기록에 남은 건수입니다. 0건은 기록이 없다는 뜻이고, 추천 계산에는 쓰지 않습니다.">고독사 기록(2019~2026) ⓘ</dt><dd class="num">${ex.lonely_death.total ? `<b style="color:var(--bad)">${ex.lonely_death.total}건</b>` : '0건'}</dd>
      <dt>업무협약(2025)</dt><dd class="num">${f.int(ex.mou.n)}건</dd>
      <dt>일자리 지원(2025)</dt><dd class="num">${f.int(ex.job.n)}건</dd>
      <dt>입주민·유관기관 회의(2025)</dt><dd class="num">${f.int((ex.governance.find(g => g.year === '2025') || {}).value)}건</dd></dl></div>
    <div class="sec"><h4>해피콜 만족도 <small class="muted">2025, 관리소 단위</small></h4>${happycallBlock(d.happycall)}</div>
    ${actions ? `<div class="sec row"><a class="btn pri" href="#/complex">현황 자세히</a><a class="btn" href="#/recommend">추천 프로그램</a><a class="btn" href="#/plan">실행 계획</a><a class="btn" href="#/kg">Knowledge Graph</a></div>` : ''}
  </div>`;
}

export function table(cols, rows, { onRow, sortKey, sortDir = -1, cls = '' } = {}) {   // cols: [{key,label,r,fmt,html}]
  const el = document.createElement('div'); el.className = 'scroll ' + cls;
  let key = sortKey, dir = sortDir;
  const draw = () => {
    const rs = key ? [...rows].sort((a, b) => { const x = a[key], y = b[key]; if (x == null) return 1; if (y == null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * dir; }) : rows;
    el.innerHTML = `<table class="tbl"><thead><tr>${cols.map(c => `<th class="${c.r ? 'r ' : ''}${c.sort === false ? '' : 'sortable'}" data-k="${c.key}">${esc(c.label)}${key === c.key ? (dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead>
      <tbody>${rs.map((r, i) => `<tr class="${onRow ? 'click' : ''}" data-i="${rows.indexOf(r)}">${cols.map(c => `<td class="${c.r ? 'r num' : ''}">${c.html ? c.html(r) : c.fmt ? c.fmt(r[c.key], r) : r[c.key] == null ? NA : esc(r[c.key])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  };
  el.addEventListener('click', e => {
    const th = e.target.closest('th.sortable'); if (th) { const k = th.dataset.k; dir = key === k ? -dir : -1; key = k; draw(); return; }
    const tr = e.target.closest('tr.click'); if (tr && onRow && !e.target.closest('a,button')) onRow(rows[+tr.dataset.i], tr);
  });
  draw(); return el;
}

// 긴 화면의 목차: 상자 제목(h3)이나 data-toc를 모아 머리 아래에 고정해 두고, 지금 보고 있는 곳을 표시한다
let tocOff = null, tocUnpin = () => { };
['wheel', 'touchmove', 'keydown', 'mousedown'].forEach(ev => addEventListener(ev, e => { if (!e.target.closest || !e.target.closest('.toc')) tocUnpin(); }, { passive: true }));   // 직접 스크롤하면 목차 고정을 푼다
export function buildToc(view) {
  if (tocOff) { tocOff(); tocOff = null; }
  view.querySelector('.toc')?.remove();
  const page = view.querySelector('.page'); if (!page) return;
  const secs = [...page.querySelectorAll('.panel')].map(el => {
    const h = el.querySelector(':scope > h3, :scope > .row > h3');
    const label = el.dataset.toc || (h ? [...h.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim() : '');
    return label && label !== '-' ? { el, label } : null;
  }).filter(Boolean);
  if (secs.length < 4) return;
  const nav = document.createElement('nav'); nav.className = 'toc'; nav.setAttribute('aria-label', '이 화면의 목차');
  nav.innerHTML = `<div class="toc-in">${secs.map((x, i) => `<button data-i="${i}">${esc(x.label)}</button>`).join('')}</div>`;
  view.prepend(nav);
  secs.forEach(x => x.el.classList.add('toc-sec'));
  const btns = [...nav.querySelectorAll('button')];
  let pinned = -1;                                             // 목차를 눌러 고른 항목. 사용자가 직접 스크롤하기 전까지는 이 항목을 표시한다
  const mark = k => {
    btns.forEach((b, i) => b.classList.toggle('on', i === k));
    const on = btns[k]; if (on) nav.firstChild.scrollTo({ left: on.offsetLeft - nav.firstChild.offsetWidth / 2 + on.offsetWidth / 2, behavior: 'auto' });
  };
  const line = () => (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--topH')) || 56) + nav.offsetHeight + 24;
  nav.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    pinned = +b.dataset.i; mark(pinned);
    const el = secs[pinned].el;
    const to = Math.max(0, el.getBoundingClientRect().top + scrollY - line() + 12);
    window.scrollTo({ top: to, behavior: Math.abs(to - scrollY) < 1200 ? 'smooth' : 'auto' });   // 먼 곳은 바로 이동
    el.classList.remove('toc-flash'); void el.offsetWidth; el.classList.add('toc-flash');      // 어느 상자인지 잠깐 테두리로 알려 준다
  });
  const spy = () => {
    if (pinned >= 0) return;
    const ln = line(); let k = 0, best = -Infinity;
    secs.forEach((x, i) => { const t = x.el.getBoundingClientRect().top; if (t <= ln && t > best + 2) { best = t; k = i; } });   // 같은 줄에 나란한 상자는 앞의 것
    if (innerHeight + scrollY >= document.documentElement.scrollHeight - 4) k = secs.length - 1;
    mark(k);
  };
  tocUnpin = () => { pinned = -1; };
  addEventListener('scroll', spy, { passive: true }); spy();
  tocOff = () => removeEventListener('scroll', spy);
}
