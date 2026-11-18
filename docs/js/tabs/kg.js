// Knowledge Graph: project/knowledge_graph의 탐색 시제품을 /kg/에 붙여 보여 준다. 고른 단지·프로그램으로 바로 들어간다.
import { S, $, esc, cx } from '../core.js';

export async function render(view, arg) {
  if (!S.meta.kg) {
    view.innerHTML = `<div class="page"><div class="note warn"><b>지식 그래프 자료가 없습니다.</b> project/knowledge_graph 폴더에서 <code>python build_graph.py</code>를 실행한 뒤 서버를 다시 시작하세요.</div></div>`; return;
  }
  const focus = arg || (S.cid ? 'complex:' + S.cid : '');
  const src = 'kg/index.html' + (focus ? '#focus=' + encodeURIComponent(focus) : '');
  const c = cx();
  view.innerHTML = `<div class="kgwrap">
    <div class="kgbar"><b>Knowledge Graph</b><span class="muted">단지·프로그램·운영 기록·사례집·소식·실행 조건의 연결을 따라가며 봅니다.</span><span class="grow"></span>
      ${c ? `<button class="btn sm" data-f="complex:${S.cid}">${esc(c.name)}에서 시작</button>` : ''}<button class="btn sm" data-f="">프로그램 지도</button>
      <a class="btn sm ghost" href="${esc(src)}" target="_blank" rel="noopener">새 창으로</a></div>
    <iframe id="kgFrame" title="온터 Knowledge Graph" src="${esc(src)}"></iframe>
  </div>`;
  view.querySelector('.kgbar').addEventListener('click', e => {
    const b = e.target.closest('[data-f]'); if (!b) return;
    const fr = $('#kgFrame'), f = b.dataset.f;
    fr.src = 'about:blank'; setTimeout(() => (fr.src = 'kg/index.html' + (f ? '#focus=' + encodeURIComponent(f) : '')), 30);
  });
}
