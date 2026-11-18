// 사례·소식: 사례집 카드(목록 + 상세, 필터), 걸림돌·해결 정리, 뉴스(제목·링크)
import { S, api, cached, $, $$, esc } from '../core.js';

let sub = 'cards', cat = '', sel = null;
const flt = { q: '', domain: '', obstacle: '', linked: '' }, nflt = { q: '' };

// 긴 제목을 '프로그램 이름'과 '한 줄 설명'으로 나눈다:  충북 청주산남2 '숙골빨래터': 이불 빨래 … → 숙골빨래터 / 이불 빨래 …
const short = c => {
  const i = c.headline.indexOf(': ');
  return { title: c.program_name || (i > 0 ? c.headline.slice(0, i) : c.headline), desc: i > 0 ? c.headline.slice(i + 2) : '' };
};

function detailHtml(c, d) {
  const s = short(c), obs = d.obstacles.filter(o => o.case_id === c.case_id), cs = d.cases.find(x => x.case_id === c.case_id);
  const list = xs => `<ul>${xs.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`;
  const partners = c.partners.map(x => { const m = x.match(/^(.*?)\((.*)\)$/); return m ? `<li><b>${esc(m[1])}</b> <span class="muted">— ${esc(m[2])}</span></li>` : `<li>${esc(x)}</li>`; }).join('');
  return `<div class="row between"><div class="row"><span class="chip">${esc(c.domain || '')}</span><span class="muted">${esc(c.region || '')}</span></div><span class="muted" style="font-size:0.867rem">사례 ${esc(c.case_id)}</span></div>
    <h2 style="margin-top:6px">${esc(s.title)}</h2>
    <p style="margin:4px 0 0;font-size:1rem;color:var(--ink2)">${esc(s.desc)}</p>
    <div class="row" style="margin-top:8px">${c.std_id ? `<a class="chip acc" href="#/programs/${c.std_id}">표준 프로그램: ${esc(c.std_name)}</a>` : '<span class="chip">연결된 표준 프로그램 없음</span>'}
      ${c.complex_ids.filter(i => S.byId[i]).map(i => `<a class="chip" href="#/complex/${i}">${esc(S.byId[i].name)}</a>`).join('')}</div>
    ${c.need.length ? `<section><h4>왜 시작했나</h4>${list(c.need)}</section>` : ''}
    ${c.target ? `<section><h4>누구를 위해</h4><p style="margin:0;font-size:1rem">${esc(c.target)}</p></section>` : ''}
    ${c.how.length || c.operation ? `<section><h4>어떻게 운영했나</h4>${c.operation ? `<p style="margin:0 0 4px;font-size:1rem"><b>운영 주기</b> ${esc(c.operation)}</p>` : ''}${c.how.length ? list(c.how) : ''}</section>` : ''}
    ${c.partners.length ? `<section><h4>누구와 함께 했나</h4><ul>${partners}</ul></section>` : ''}
    <section><h4>부딪힌 문제와 해결 <small class="muted">${obs.length}건</small></h4>
      ${obs.length ? obs.map(o => `<div class="ob"><div><span class="chip warn">${esc(o.category)}</span><div class="q" style="margin-top:4px">${esc(o.obstacle)}</div></div><div class="arrow">→</div>
        <div>${o.solution ? `${o.strategy ? `<span class="chip ok">${esc(o.strategy)}</span>` : ''}<div class="a" style="margin-top:4px">${esc(o.solution)}</div>` : '<span class="muted">해결 방법이 사례집에 적혀 있지 않습니다</span>'}</div></div>`).join('') : '<div class="muted">사례집에 적힌 걸림돌이 없습니다</div>'}</section>
    ${c.outcomes.length ? `<section><h4>사례집에 적힌 결과</h4>${list(c.outcomes)}<div class="note" style="margin-top:6px">사례집의 서술입니다. 효과를 검증한 수치가 아니며, 다른 단지에서 같은 결과가 난다는 뜻이 아닙니다.</div></section>` : ''}
    ${c.lessons ? `<section><h4>담당자가 남긴 말</h4><p style="margin:0;font-size:1rem">${esc(c.lessons)}</p></section>` : ''}
    ${cs && cs.summary ? `<section><h4>사례 요약</h4><p style="margin:0;font-size:1rem">${esc(cs.summary)}</p></section>` : ''}
    <div class="muted" style="font-size:0.867rem;margin-top:14px">출처: ${esc(c.source)}</div>`;
}

export async function render(view, arg, alive) {
  const d = await cached('cases', () => api('cases'));
  if (!alive()) return;
  if (arg) { sub = 'cards'; sel = arg; }
  const cats = [...new Set(d.obstacles.map(o => o.category))], strats = [...new Set(d.playbook.map(p => p.strategy))];
  const domains = [...new Set(d.cards.map(c => c.domain).filter(Boolean))];
  const obsByCase = {}; d.obstacles.forEach(o => (obsByCase[o.case_id] = obsByCase[o.case_id] || []).push(o));

  const drawCards = () => {
    const rows = d.cards.filter(c => {
      const text = (c.headline + ' ' + (c.std_name || '') + ' ' + c.need.join(' ') + ' ' + c.how.join(' ') + ' ' + c.partners.join(' ')).toLowerCase();
      return (!flt.q || text.includes(flt.q.toLowerCase())) && (!flt.domain || c.domain === flt.domain)
        && (!flt.obstacle || (obsByCase[c.case_id] || []).some(o => o.category === flt.obstacle)) && (!flt.linked || (flt.linked === '1') === !!c.std_id);
    });
    if (!rows.find(c => c.card_id === sel)) sel = rows[0]?.card_id || null;
    $('#csCount').textContent = `${rows.length}장 / 전체 ${d.cards.length}장`;
    $('#csList').innerHTML = rows.map(c => { const s = short(c), n = (obsByCase[c.case_id] || []).length; return `<button class="csitem ${c.card_id === sel ? 'on' : ''}" data-id="${c.card_id}">
        <div class="t">${esc(s.title)}</div><div class="s">${esc(s.desc)}</div>
        <div class="m"><span class="chip">${esc(c.domain || '')}</span><span class="chip">${esc(c.region || '')}</span>${n ? `<span class="chip warn">걸림돌 ${n}건</span>` : ''}${c.std_id ? `<span class="chip acc">${esc(c.std_name)}</span>` : ''}</div></button>`; }).join('') || '<div class="empty">조건에 맞는 사례가 없습니다</div>';
    const c = d.cards.find(x => x.card_id === sel);
    $('#csDetail').innerHTML = c ? detailHtml(c, d) : '<div class="empty">왼쪽에서 사례를 고르세요</div>';
    $('#csDetail').scrollTop = 0;
  };

  const draw = () => {
    $$('#csTabs button').forEach(b => b.classList.toggle('on', b.dataset.s === sub));
    const body = $('#csBody');
    if (sub === 'cards') {
      body.innerHTML = `<div class="cslayout"><div>
          <div class="csfilter"><input id="cfQ" type="search" placeholder="사례 찾기(이름, 내용, 협력기관)" value="${esc(flt.q)}">
            <select id="cfD"><option value="">분야 전체</option>${domains.map(x => `<option ${x === flt.domain ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>
            <select id="cfO"><option value="">걸림돌 유형 전체</option>${cats.map(x => `<option ${x === flt.obstacle ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>
            <select id="cfL" style="grid-column:1/-1"><option value="">표준 프로그램 연결 여부 전체</option><option value="1" ${flt.linked === '1' ? 'selected' : ''}>표준 프로그램과 연결된 사례</option><option value="0" ${flt.linked === '0' ? 'selected' : ''}>연결되지 않은 사례</option></select></div>
          <div class="muted" id="csCount" style="font-size:0.867rem;margin-bottom:6px"></div><div class="cslist" id="csList"></div></div>
        <div class="panel csdetail" id="csDetail"></div></div>`;
      const bind = (id, k) => $(id).addEventListener('input', e => { flt[k] = e.target.value.trim(); drawCards(); });
      bind('#cfQ', 'q'); bind('#cfD', 'domain'); bind('#cfO', 'obstacle'); bind('#cfL', 'linked');
      $('#csList').addEventListener('click', e => { const b = e.target.closest('.csitem'); if (b) { sel = b.dataset.id; history.replaceState(null, '', '#/cases/' + sel); drawCards(); } });
      drawCards();
    }
    if (sub === 'play') {
      const byCat = cats.map(c => ({ c, rows: d.obstacles.filter(o => o.category === c) })).sort((x, y) => y.rows.length - x.rows.length), max = byCat[0].rows.length;
      const strat = rows => { const m = {}; rows.forEach(o => { const k = o.strategy || '적혀 있지 않음'; m[k] = (m[k] || 0) + 1; }); return Object.entries(m).sort((x, y) => y[1] - x[1]); };
      body.innerHTML = `<div class="panel"><h3>걸림돌 유형별 요약</h3>
        <table class="tbl sumtbl"><thead><tr><th>걸림돌 유형</th><th>사례 수</th><th>사례집에서 쓴 해결 방식</th></tr></thead><tbody>
          ${byCat.map(g => `<tr class="click ${cat === g.c ? 'on' : ''}" data-cat="${esc(g.c)}"><td><b>${esc(g.c)}</b></td>
            <td><div class="cntbar"><span style="width:${(g.rows.length / max * 100).toFixed(0)}%"></span><b class="num">${g.rows.length}건</b></div></td>
            <td>${strat(g.rows).map(([k, n]) => `<span class="chip ${k === '적혀 있지 않음' ? '' : 'ok'}">${esc(k)} ${n}</span>`).join(' ')}</td></tr>`).join('')}
        </tbody></table>
        <div class="row" style="margin-top:8px"><span class="muted">유형을 누르면 아래 목록이 좁혀집니다.</span>${cat ? `<button class="btn sm" data-cat="">전체 보기</button>` : ''}</div></div>
        ${byCat.filter(g => !cat || g.c === cat).map(g => `<div class="panel"><h3>${esc(g.c)} <small class="muted">${g.rows.length}건</small></h3>
          <table class="tbl obtbl"><thead><tr><th>부딪힌 문제</th><th>해결 방식</th><th>어떻게 풀었나</th><th>사례</th></tr></thead><tbody>
          ${g.rows.map(o => { const card = d.cards.find(x => x.case_id === o.case_id), cs = d.cases.find(x => x.case_id === o.case_id); return `<tr><td${o.evidence ? ` data-tip="${esc('사례집 원문: ' + o.evidence)}"` : ''}>${esc(o.obstacle)}</td>
            <td>${o.strategy ? `<span class="chip ok">${esc(o.strategy)}</span>` : '<span class="muted">-</span>'}</td>
            <td>${o.solution ? esc(o.solution) : '<span class="muted">사례집에 적혀 있지 않습니다</span>'}</td>
            <td>${card ? `<a href="#/cases/${card.card_id}">${esc(short(card).title)}</a><div class="muted">${esc(card.region || '')}</div>` : esc(cs ? cs.title : o.case_id)}</td></tr>`; }).join('')}
          </tbody></table></div>`).join('')}`;
    }
    if (sub === 'news') {
      const rows = d.news.filter(n => !nflt.q || (n.title + ' ' + (n.std_name || '') + ' ' + (n.outlet || '')).includes(nflt.q));
      body.innerHTML = `<div class="panel"><div class="row between"><h3>주거복지 소식 <small class="muted">${rows.length}건 · 제목과 링크만 싣습니다(본문은 재사용 허락을 확인하지 않았습니다)</small></h3><input id="nfQ" type="search" placeholder="제목·프로그램·매체 찾기" value="${esc(nflt.q)}"></div>
        <table class="tbl" style="margin-top:8px"><thead><tr><th>날짜</th><th>제목</th><th>매체</th><th>관련 프로그램</th></tr></thead><tbody>${rows.map(n => `<tr><td class="num" style="white-space:nowrap">${esc(n.date || '')}</td><td><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a>${n.representative ? '' : ' <span class="chip">같은 내용의 다른 기사</span>'}</td><td style="white-space:nowrap">${esc(n.outlet || '')}</td><td>${n.std_id ? `<a href="#/programs/${n.std_id}">${esc(n.std_name || '')}</a>` : '<span class="muted">-</span>'}</td></tr>`).join('')}</tbody></table></div>`;
      $('#nfQ').addEventListener('input', e => { nflt.q = e.target.value.trim(); const pos = e.target.selectionStart; draw(); const el = $('#nfQ'); el.focus(); el.setSelectionRange(pos, pos); });
    }
  };
  view.innerHTML = `<div class="page"><div class="page-head"><div><h2>사례·소식</h2><p>주거복지사 활동 사례집의 복지 사례를 정리했습니다.</p></div></div>
    <div class="subtabs" id="csTabs"><button data-s="cards">사례 카드 ${d.cards.length}</button><button data-s="play">걸림돌·해결 ${d.obstacles.length}</button><button data-s="news">소식 ${d.news.length}</button></div>
    <div id="csBody" class="grid"></div>
    </div>`;
  $('#csTabs').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { sub = b.dataset.s; draw(); } });
  $('#csBody').addEventListener('click', e => { const b = e.target.closest('[data-cat]'); if (b && sub === 'play') { cat = b.dataset.cat; draw(); } });
  draw();
}
