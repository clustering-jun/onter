// 지도(메인): Leaflet + OpenStreetMap 표준 타일. 단지를 눌러 고른다.
import { S, api, $, esc, f, setComplex, complexCard, TYPE_COLOR } from '../core.js';

// 색(사용자가 시안에서 고름)
//  WARM  살구→진빨강 5단계 : 값이 클수록 눈여겨볼 기준(고령 비율, 필요, 경과 연수, 소형 세대 비율)
//  COOL  회청→남색 5단계   : 규모·활동·만족도처럼 크다고 주의할 일은 아닌 기준
//  단지 유형은 파랑·빨강·남청(core.js의 TYPE_COLOR), 배치 여부는 남청·빨강
const WARM = ['#fcbba1', '#fc8d6a', '#f2553d', '#cb181d', '#7f0a12'];
const COOL = ['#bdc9e1', '#8fb4d8', '#5a9bc8', '#2b7bb5', '#03467a'];
const ZERO = '#ffffff', CNT = ['#fc8d6a', '#e0301f', '#7f0a12'];                 // 0이 대부분인 건수: 0은 흰 원, 그 위는 3단계
const CAT2 = { yes: '#1d3557', no: '#e63946' };

// 포인트 모양(사용자가 시안에서 고름): 속이 비치는 반투명 원에 같은 색의 진한 테두리. 겹친 단지가 비쳐 보인다.
// 값이 없는 원(점선)과 0인 원(흰 원)은 Leaflet 기본 모양 그대로 그린다.
const circ = (ctx, x, y, r) => { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); };
const PointCanvas = L.Canvas.extend({
  _updateCircle(layer) {
    const o = layer.options;
    if (o.plain) return L.Canvas.prototype._updateCircle.call(this, layer);
    if (!this._drawing || layer._empty()) return;
    const p = layer._point, ctx = this._ctx, r = Math.max(Math.round(layer._radius), 1);
    ctx.save();
    circ(ctx, p.x, p.y, r); ctx.globalAlpha = o.weight >= 3 ? 0.95 : 0.45; ctx.fillStyle = o.fillColor; ctx.fill();
    ctx.globalAlpha = 1; ctx.lineWidth = 2.2; ctx.strokeStyle = o.fillColor; ctx.stroke();
    if (o.weight >= 3) { circ(ctx, p.x, p.y, r + 2.5); ctx.lineWidth = 3; ctx.strokeStyle = '#111'; ctx.stroke(); }   // 고른 단지
    ctx.restore();
  },
});
const coolKeys = new Set(['hh', 'pph', 'n_records', 'richness', 'hd', 'hc_overall', 'hc_welfare']);
const METRICS = [
  { key: 'type', label: '단지 유형', kind: 'cat' },
  { key: 'deployed', label: '주거복지사 배치', kind: 'cat' },
  { key: 'age60', label: '60세 이상 비율', fmt: f.pct }, { key: 'age80', label: '80세 이상 비율', fmt: f.pct }, { key: 'pph', label: '세대당 인구', fmt: v => f.n2(v) + '명' },
  { key: 'hh', label: '세대 수', fmt: v => f.int(v) + '세대' }, { key: 'years', label: '입주 후 경과 연수', fmt: v => f.int(v) + '년' }, { key: 'small_unit', label: '40㎡ 미만 세대 비율', fmt: f.pct },
  { key: 'n_records', label: '활동 기록 수(30개월)', fmt: v => f.int(v) + '건', missing: '기록 없음' }, { key: 'richness', label: '프로그램 종류 수', fmt: v => f.int(v) + '종', missing: '기록 없음' },
  { key: 'n_priority', label: '우선 검토 분야 수', fmt: v => f.int(v) + '개', missing: '기록 없음', count: [1, 2], zero: '없음' },
  ...['N1', 'N2', 'N3', 'N4', 'N5', 'N6'].map(d => ({ key: 'need.' + d, label: '필요: ', need: d, fmt: v => '백분위 ' + Math.round(v * 100) })),
  { key: 'hd', label: '홈닥터 지원(100세대당 월)', fmt: v => f.n1(v) + '건' }, { key: 'ld', label: '고독사 기록 건수(2019~2026)', fmt: v => f.int(v) + '건', count: [1, 3], zero: '기록 없음(0건)' },
  { key: 'hc_overall', label: '해피콜 종합 만족도', fmt: v => f.n1(v) + '점', missing: '조사 값 없음' }, { key: 'hc_welfare', label: '해피콜 복지 만족도', fmt: v => f.n1(v) + '점', missing: '조사 값 없음' },
];
let map, layer, selTip = null, markers = {}, pulses = {}, st = { metric: 'type', branch: '', type: '', q: '' }, selected = null;
const HOME = [[36.3, 127.8], 7];

const val = (c, key) => key.startsWith('need.') ? c.need[key.slice(5)] : c[key];
const mlabel = m => m.need ? m.label + S.meta.needs[m.need] : m.label;
function scale(metric, rows) {
  const m = METRICS.find(x => x.key === metric);
  if (m.kind === 'cat') {
    if (metric === 'type') return { m, color: c => TYPE_COLOR[c.type], legend: Object.entries(S.meta.type_info).map(([k, v]) => [TYPE_COLOR[k], `${v.label} · ${v.n}곳`, v.desc.split('. ')[0].replace(/\.$/, '')]) };
    return { m, color: c => c.deployed ? CAT2.yes : CAT2.no, legend: [[CAT2.yes, `배치 · ${rows.filter(c => c.deployed).length}곳`], [CAT2.no, `미배치 · ${rows.filter(c => !c.deployed).length}곳`]] };
  }
  if (m.count) {                                               // 0이 대부분인 건수: 분위로 나누면 뜻이 없으므로 0 / 1단계 / 2단계 / 3단계로 나눈다
    const [a, b] = m.count, n = k => rows.filter(k).length, v = c => val(c, metric);
    const cls = x => x == null ? null : x === 0 ? 0 : x <= a ? 1 : x <= b ? 2 : 3;
    return {
      m, zeroish: c => v(c) === 0, color: c => { const k = cls(v(c)); return k == null ? null : k === 0 ? ZERO : CNT[k - 1]; },
      legend: [[ZERO, `${m.zero} · ${n(c => v(c) === 0)}곳`], [CNT[0], `${a === 1 ? m.fmt(1) : '1~' + m.fmt(a)} · ${n(c => cls(v(c)) === 1)}곳`],
      [CNT[1], `${a + 1 === b ? m.fmt(b) : (a + 1) + '~' + m.fmt(b)} · ${n(c => cls(v(c)) === 2)}곳`], [CNT[2], `${m.fmt(b + 1)} 이상 · ${n(c => cls(v(c)) === 3)}곳`]].concat(m.missing ? [[null, m.missing]] : []),
    };
  }
  const vs = rows.map(c => val(c, metric)).filter(v => v != null).sort((a, b) => a - b);
  const qs = m.steps || [0.2, 0.4, 0.6, 0.8].map(p => vs[Math.floor(p * (vs.length - 1))]);
  const bin = v => qs.findIndex(q => v <= q), SEQ = coolKeys.has(metric) ? COOL : WARM;
  return {
    m, color: c => { const v = val(c, metric); if (v == null) return null; const b = bin(v); return SEQ[b < 0 ? 4 : b]; },
    legend: SEQ.map((c, i) => [c, i === 0 ? (m.steps ? m.fmt(qs[0]) : `${m.fmt(vs[0])} ~ ${m.fmt(qs[0])}`) : i === 4 ? `${m.fmt(qs[3])} 초과` : `~ ${m.fmt(qs[i])}`]).concat(m.missing ? [[null, m.missing]] : []),
  };
}
const passes = c => (!st.branch || c.branch === st.branch) && (!st.type || c.type === st.type) && (!st.q || c.name.includes(st.q));

function tipHtml(c) {                                         // 마우스를 올렸을 때: 단지 이름, 주소, 공급 유형, 세대 수
  return `<b class="t">${esc(c.name)}</b><span class="k">${esc(c.addr || '')}</span><br>${esc(c.supply || '공급 유형 자료 없음')} · ${f.int(c.hh)}세대`;
}

function draw(fit) {
  const rows = S.complexes.filter(passes), sc = scale(st.metric, S.complexes);
  layer.clearLayers(); markers = {}; pulses = {};
  rows.forEach(c => {
    const col = sc.color(c), z = sc.zeroish && sc.zeroish(c), r = (5.4 + Math.sqrt(c.hh) / 5.8) * (z ? 0.8 : 1);
    const mk = L.circleMarker([c.lat, c.lon], { radius: r, color: col ? (z ? '#5d6673' : '#2f3742') : '#626d7d', weight: col ? 1.2 : 1.4, dashArray: col ? null : '3 2', fillColor: col || '#fff', fillOpacity: col ? 0.95 : 0.65, plain: !col || !!z, base: col ? (z ? '#5d6673' : '#2f3742') : '#626d7d' });
    mk.bindTooltip(tipHtml(c), { direction: 'top', offset: [0, -r], className: 'mtip', opacity: 1 });
    mk.on('click', () => setComplex(c.id));
    mk.addTo(layer); markers[c.id] = mk;
    if (col && !z) {                                           // 반짝임: 원 뒤에서 같은 색 고리가 퍼졌다 사라진다. 단지마다 박자를 달리한다
      const dur = 2.4 + Math.random() * 1.6;
      pulses[c.id] = L.marker([c.lat, c.lon], { pane: 'pulse', interactive: false, keyboard: false,
        icon: L.divIcon({ className: 'pulse', iconSize: [2 * r, 2 * r], html: `<i style="background:${col};animation-duration:${dur.toFixed(2)}s;animation-delay:-${(Math.random() * dur).toFixed(2)}s"></i>` }) }).addTo(layer);
    }
  });
  $('#mapCount').textContent = `${rows.length}곳 표시 / 전체 ${S.complexes.length}곳`;
  $('#legend').innerHTML = `<b>${esc(mlabel(sc.m))}</b><div class="lg">${sc.legend.map(([c, t, d]) => `<span><i style="background:${c || '#fff'};${c ? '' : 'border:1px dashed #7b8696'}"></i>${esc(t)}${d ? `<span class="d">${esc(d)}</span>` : ''}</span>`).join('')}</div>`;
  rows.filter(c => !(sc.zeroish && sc.zeroish(c))).forEach(c => markers[c.id] && markers[c.id].bringToFront());   // 값이 있는 단지를 위로
  const list = [...rows].sort((a, b) => sc.m.kind === 'cat' ? a.name.localeCompare(b.name, 'ko') : (val(b, st.metric) ?? -Infinity) - (val(a, st.metric) ?? -Infinity)).slice(0, 200);
  $('#clist').innerHTML = list.map(c => { const v = val(c, st.metric); return `<button data-id="${c.id}" class="${c.id === S.cid ? 'on' : ''}"><span>${esc(c.name)}</span><span class="v">${sc.m.kind === 'cat' ? esc(c.branch) : v == null ? (sc.m.missing || '자료 없음') : sc.m.fmt(v)}</span></button>`; }).join('') || '<div class="empty">조건에 맞는 단지가 없습니다</div>';
  highlight();
  if (fit) {                                                   // 지사·유형 등을 고르면 그 단지들이 다 보이게 지도를 옮긴다
    if (rows.length && rows.length < S.complexes.length) map.flyToBounds(L.latLngBounds(rows.map(c => [c.lat, c.lon])).pad(0.15), { duration: 0.7, maxZoom: 12 });
    else map.flyTo(...HOME, { duration: 0.7 });
  }
}
// 고른 단지의 설명 상자: 눌렀을 때 뜨고 계속 떠 있다. 고른 원과 다른 원을 가장 덜 가리는 쪽(위·오른쪽·왼쪽·아래)에 놓는다.
function placeSel() {
  if (selTip) { selTip.remove(); selTip = null; }
  const c = selected && S.byId[selected], mk = c && markers[selected];
  if (!mk || !map) return;
  const p = map.latLngToContainerPoint([c.lat, c.lon]), size = map.getSize(), r = mk.options.radius, gap = r + 12, W = 380, H = 96;
  const boxes = { top: [p.x - W / 2, p.y - gap - H], right: [p.x + gap, p.y - H / 2], left: [p.x - gap - W, p.y - H / 2], bottom: [p.x - W / 2, p.y + gap] };
  const pts = Object.entries(markers).filter(([id]) => id !== selected).map(([, m]) => map.latLngToContainerPoint(m.getLatLng()));
  const cost = ([x, y]) => pts.filter(q => q.x > x - 8 && q.x < x + W + 8 && q.y > y - 8 && q.y < y + H + 8).length
    + 50 * (Math.max(0, -x) + Math.max(0, x + W - size.x) + Math.max(0, -y) + Math.max(0, y + H - size.y) > 0);   // 지도 밖으로 나가는 쪽은 피한다
  const dir = Object.keys(boxes).reduce((a, b) => cost(boxes[b]) < cost(boxes[a]) ? b : a);
  const off = { top: [0, -gap + 6], bottom: [0, gap - 6], right: [gap - 6, 0], left: [-gap + 6, 0] }[dir];
  selTip = L.tooltip({ permanent: true, direction: dir, offset: off, className: 'mtip msel', opacity: 1 }).setLatLng([c.lat, c.lon]).setContent(tipHtml(c)).addTo(map);
}
function highlight() {
  if (selected && markers[selected]) {                       // 앞서 고른 단지: 테두리를 되돌리고 마우스 올림 설명을 다시 붙인다
    const m = markers[selected];
    m.setStyle({ color: m.options.base, weight: 1.1 });
    if (!m.getTooltip()) m.bindTooltip(tipHtml(S.byId[selected]), { direction: 'top', offset: [0, -m.options.radius], className: 'mtip', opacity: 1 });
  }
  selected = S.cid;
  if (selected && markers[selected]) { const m = markers[selected]; m.setStyle({ color: '#111', weight: 3.5 }); m.bringToFront(); m.unbindTooltip(); }   // 고른 단지는 상자가 떠 있으므로 마우스 올림 설명을 뗀다
  document.querySelectorAll('#clist button').forEach(b => b.classList.toggle('on', b.dataset.id === S.cid));
  placeSel();
}
async function card() {
  const el = $('#mapcard'); if (!el) return;
  if (!S.cid) {
    const m = S.meta.counts;
    el.innerHTML = `<h3>단지를 선택하세요</h3><p class="muted">지도의 원이나 왼쪽 목록에서 단지를 누르면 기본 현황이 여기에 나옵니다.</p>
      <div class="tiles"><div class="tile"><b class="num">${f.int(m.complexes)}</b><span>단지</span></div><div class="tile"><b class="num">${f.int(m.with_records)}</b><span>활동 기록 있음</span></div>
      <div class="tile"><b class="num">${f.int(m.programs)}</b><span>추천 대상 프로그램</span></div><div class="tile"><b class="num">${f.int(m.records)}</b><span>활동 기록</span></div></div>
      <h4 style="margin-top:14px">단지 유형</h4>${Object.entries(S.meta.type_info).map(([k, v]) => `<div style="margin-top:6px"><span class="chip" style="background:${TYPE_COLOR[k]};color:#fff">${esc(v.label)}</span> <b>${v.n}곳</b><div style="font-size:0.933rem;margin-top:2px">${esc(v.desc)}</div><div class="muted" style="font-size:0.867rem">중앙값: ${esc(v.facts)}</div></div>`).join('')}
      <div class="note" style="margin-top:12px">점선 원은 그 기준의 값이 없는 단지입니다. 값이 없는 것과 0인 것은 다르게 표시합니다.</div>`;
    return;
  }
  el.innerHTML = '<div class="empty"><span class="spin"></span></div>';
  const id = S.cid, d = await api('complex', { id });
  if (id === S.cid && $('#mapcard')) { $('#mapcard').innerHTML = complexCard(d); $('#mapcard').scrollTop = 0; }
}
export function select(cid) {
  highlight(); card();
  const c = S.byId[cid]; if (c && map) map.flyTo([c.lat, c.lon], Math.max(map.getZoom(), 11), { duration: 0.6 });
}
export function leave() { if (map) { map.stop(); layer.clearLayers(); map.remove(); map = null; selTip = null; markers = {}; pulses = {}; } }   // 이동 중에 탭을 떠나도 그리기 오류가 나지 않게 멈추고 비운다

export async function render(view) {
  const branches = [...new Set(S.complexes.map(c => c.branch))].sort((a, b) => a.localeCompare(b, 'ko'));
  view.innerHTML = `<div class="mapwrap">
    <aside class="mapside">
      <div class="field"><label for="fq">단지 찾기</label><input id="fq" type="search" placeholder="단지 이름" value="${esc(st.q)}"></div>
      <div class="field"><label for="fm">색으로 볼 기준</label><select id="fm">${METRICS.map(m => `<option value="${m.key}" ${m.key === st.metric ? 'selected' : ''}>${esc(mlabel(m))}</option>`).join('')}</select></div>
      <div class="row"><div class="field grow"><label for="fb">지사</label><select id="fb"><option value="">전체</option>${branches.map(b => `<option ${b === st.branch ? 'selected' : ''}>${esc(b)}</option>`).join('')}</select></div>
        <div class="field grow"><label for="ft">유형</label><select id="ft"><option value="">전체</option>${Object.entries(S.meta.types).map(([k, v]) => `<option value="${k}" ${k === st.type ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></div></div>
      <div class="row between"><span class="muted" id="mapCount" style="font-size:0.867rem"></span><button class="btn sm ghost" id="freset">조건 지우기</button></div>
      <div class="clist" id="clist"></div>
    </aside>
    <div class="maparea"><div id="map" aria-label="단지 지도"></div><div class="legend" id="legend"></div></div>
    <aside class="mapcard" id="mapcard"></aside>
  </div>`;
  map = L.map('map', { zoomControl: true, renderer: new PointCanvas({ padding: 0.5 }) }).setView(...HOME);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, opacity: 0.9, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> 기여자' }).addTo(map);
  map.createPane('pulse').style.zIndex = 390;                  // 원(캔버스, 400) 바로 아래
  layer = L.layerGroup().addTo(map);
  map.on('moveend', placeSel);                                 // 지도가 움직이면 상자 자리를 다시 고른다
  const bind = (id, k, fit) => $(id).addEventListener('input', e => { st[k] = e.target.value.trim(); draw(fit); });
  bind('#fq', 'q'); bind('#fm', 'metric'); bind('#fb', 'branch', true); bind('#ft', 'type');
  $('#freset').addEventListener('click', () => { Object.assign(st, { branch: '', type: '', q: '' }); render(view); });
  $('#clist').addEventListener('click', e => { const b = e.target.closest('button'); if (b) setComplex(b.dataset.id); });
  draw(); card();
  setTimeout(() => {
    if (!map) return;
    map.invalidateSize();
    if (st.branch) draw(true); else if (S.cid) { const c = S.byId[S.cid]; map.setView([c.lat, c.lon], 11); }
  }, 60);
}
