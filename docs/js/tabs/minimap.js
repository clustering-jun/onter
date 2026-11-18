// 단지 현황의 작은 지도: 지금 보는 단지가 어디에 있는지 보여 주고, 지도에서 누르거나 이름을 검색해 다른 단지로 바꾼다.
import { S, $, esc, f, setComplex } from '../core.js';

let map = null;

export function leave() { if (map) { map.stop(); map.off(); map.remove(); map = null; } }

export function html(cid) {
  return `<div class="panel minimap" data-toc="위치">
    <h3>위치</h3>
    <div class="mm-search"><input id="mmQ" type="search" placeholder="단지 이름으로 검색" autocomplete="off" aria-label="단지 이름 검색"><div class="mm-list" id="mmList" hidden></div></div>
    <div class="mm-map"><div id="mmMap" aria-label="단지 위치 지도"></div><button class="btn sm" id="mmHome" type="button" data-tip="누를 때마다 전국과 이 단지 둘레를 오가며 확대·축소합니다">전국 보기</button></div>
  </div>`;
}

export function mount(cid) {
  leave();
  const c0 = S.byId[cid];
  map = L.map('mmMap', { zoomControl: true, attributionControl: true, scrollWheelZoom: false }).setView([c0.lat, c0.lon], 12);   // 쪽을 내리다 지도에 걸려 멈추지 않게 휠 확대는 끈다
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, opacity: 0.9, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(map);
  const canvas = L.canvas({ padding: 0.5 });
  S.complexes.forEach(c => {
    if (c.id === cid || c.lat == null) return;
    L.circleMarker([c.lat, c.lon], { renderer: canvas, radius: 5.5, color: '#111', weight: 1.6, opacity: 0.85, fillColor: '#111', fillOpacity: 0.25, bubblingMouseEvents: false })
      .bindTooltip(`<b class="t">${esc(c.name)}</b>${esc(c.supply || '')} · ${f.int(c.hh)}세대`, { direction: 'top', offset: [0, -5], className: 'mtip', opacity: 1 })
      .on('click', () => setComplex(c.id)).addTo(map);
  });
  L.circleMarker([c0.lat, c0.lon], { renderer: canvas, radius: 9, color: '#e63946', weight: 3, fillColor: '#e63946', fillOpacity: 0.85, interactive: false })
    .bindTooltip(esc(c0.name), { permanent: true, direction: 'top', offset: [0, -9], className: 'mtip msel', opacity: 1 }).addTo(map);
  const home = $('#mmHome');                                   // 전국 보기 ↔ 지역 보기: 누를 때마다 축소·확대
  let wide = false;
  home.addEventListener('click', () => {
    wide = !wide;
    map.flyTo(wide ? [36.3, 127.8] : [c0.lat, c0.lon], wide ? 7 : 12, { duration: 0.7 });
    home.textContent = wide ? '지역 보기' : '전국 보기';
  });
  setTimeout(() => { if (map) map.invalidateSize(); }, 60);

  const q = $('#mmQ'), list = $('#mmList');
  const hits = () => { const t = q.value.replace(/\s/g, ''); return t ? S.complexes.filter(c => c.id !== cid && (c.name + c.branch).replace(/\s/g, '').includes(t)).slice(0, 8) : []; };
  const draw = () => {
    const rows = hits();
    list.hidden = !q.value.trim();
    list.innerHTML = rows.map(c => `<button type="button" data-id="${c.id}"><span>${esc(c.name)}</span><small>${esc(c.branch)}</small></button>`).join('') || '<div class="empty">찾는 단지가 없습니다</div>';
  };
  q.addEventListener('input', draw);
  q.addEventListener('keydown', e => { if (e.key === 'Enter') { const r = hits()[0]; if (r) setComplex(r.id); } else if (e.key === 'Escape') { q.value = ''; draw(); } });
  list.addEventListener('click', e => { const b = e.target.closest('button'); if (b) setComplex(b.dataset.id); });
}
