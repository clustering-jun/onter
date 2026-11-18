// 단지 현황: 단지 카드 + 통합 자료 전부(기본 정보, 연령, 필요 지표 원값, 운영 이력, 최근 기록, 상태표, 비슷한 단지, 접근성, 홈닥터, 해피콜, 그 밖의 기록)
import { panel as welfarePanel } from './welfare.js';
import { STATIC, buildToc, S, api, post, $, $$, esc, f, needPick, complexCard, needChart, hbars, stChip, domChip, setComplex, table, toast, DOM, NA, monthBars, pos, happycallBlock, TYPE_COLOR } from '../core.js';

const ST_ORDER = ['running', 'paused', 'not_run', 'no_record', 'declared', 'snoozed', 'infeasible'];
const ST_HELP = {
  running: '최근 12개월 안에 활동 기록이 있음', paused: '과거에 기록이 있지만 최근 12개월에는 없음(재개 검토 대상)', not_run: '단지에 활동 기록은 있는데 이 프로그램 기록은 없음',
  no_record: '단지의 활동 기록 자체가 없음. 안 한 것인지 알 수 없음', declared: '사용자가 이미 운영 중이라고 표시함(기록 누락)', snoozed: '사용자가 지금은 아님으로 뺌', infeasible: '사용자가 운영 불가능으로 표시함',
};
const rk = (p, key) => p[key] == null ? '' : `<small>${S.complexes.length}곳 중 ${pos(p[key])}</small>`;
const indVal = i => {
  if (i.value == null) return NA;
  if (i.composite) return '<span class="muted">여러 거리를 묶은 값</span>';
  const l = i.label, v = i.value;
  if (l.includes('비율')) return f.pct1(v); if (l.includes('거리')) return f.km(v); if (l.includes('연수')) return f.n1(v) + '년'; if (l.includes('세대당 인구')) return f.n2(v) + '명';
  if (l.includes('면적')) return f.n1(v) + '㎡'; if (l.includes('영구임대')) return v ? '예' : '아니오'; if (l.includes('공간 종류')) return f.int(v) + '종'; if (l.includes('CCTV')) return f.n1(v) + '대';
  return f.n2(v);
};
const yearTable = (rows, cols) => `<table class="tbl"><thead><tr>${cols.map(c => `<th class="${c.r ? 'r' : ''}">${c.label}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${cols.map(c => `<td class="${c.r ? 'r num' : ''}">${c.key === 'year' ? esc(r.year) : f.int(r[c.key])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;

export async function render(view, arg, alive) {
  if (arg && S.byId[arg] && arg !== S.cid) { setComplex(arg); return; }
  if (!S.cid) { view.innerHTML = needPick(); return; }
  const cid = S.cid, [d, matrix] = await Promise.all([api('complex', { id: cid }), api('matrix', { id: cid })]);
  if (!alive()) return;
  const a = d.activity, b = d.basics, p = d.pct, ex = d.extra, hd = d.home_doctor;
  const kinds = { hybrid: ['종합(구성·운영·거리)', '추천의 근거 계산에 쓰는 이웃'], struct: ['구성이 닮은 단지', '주민·주택 구성이 닮음. 멀리 있을 수 있음'], geo: ['가까운 단지', '같은 지사일 가능성이 높아 협력기관을 공유할 수 있음'] };
  const ageMax = Math.max(1, ...d.age_bands.map(x => x.n || 0)), ageTot = d.age_bands.reduce((s, x) => s + (x.n || 0), 0) || 1;
  const ld = ex.lonely_death, bd = ex.building, wc = ex.welfare_center;
  view.innerHTML = `<div class="page">
    <div class="grid g-main">
      <div class="panel" data-toc="기본 현황">${complexCard(d, { actions: false })}
        <div class="sec row"><a class="btn pri" href="#/recommend">추천 프로그램 보기</a><a class="btn" href="#/plan">실행 계획</a><a class="btn" href="#/kg">Knowledge Graph</a></div></div>
      <div class="grid" style="align-content:start">
        <figure class="panel photo ${S.meta.photos.includes(cid) ? '' : 'sample'}"><img src="img/complex/${S.meta.photos.includes(cid) ? cid : 'default'}.jpg" alt="${esc(d.name)} 전경">
          <figcaption><span class="real">${esc(d.name)} 단지 사진</span><span class="smp">예시 사진입니다. 이 단지의 사진이 아닙니다.</span></figcaption></figure>
        <div class="panel"><h3>분야별 필요와 공급 <small class="muted">전체 단지 가운데 위치</small></h3>
          <div id="needBox">${needChart(d.need, { controls: true })}</div>
          <div class="note" style="margin-top:10px">현장에서 확인한 필요가 있으면 낮음·보통·높음을 고르세요. 추천 계산에 그 값을 씁니다.</div>
          ${d.need.some(r => r.uncertain) ? `<div class="note warn" style="margin-top:6px">흐리게 보이는 분야(${d.need.filter(r => r.uncertain).map(r => esc(r.label)).join(', ')})는 지표 가중치에 따라 순위가 크게 달라집니다.</div>` : ''}
        </div>
      </div>
    </div>

    <div class="grid g2">
      <div class="panel"><h3>기본 정보</h3><table class="info"><tbody>
        <tr><th>주소</th><td>${esc(d.addr || '')}${bd.village ? ` <span class="muted">(${esc(bd.village)})</span>` : ''}</td></tr>
        <tr><th>지사 · 지역</th><td>${esc(d.branch)} · ${esc(d.region)}</td></tr>
        <tr><th>공급 유형</th><td>${esc(d.supply)}</td></tr>
        <tr><th>단지 유형</th><td><span class="chip" style="background:${TYPE_COLOR[d.type]};color:#fff">${esc(d.type_label)}</span><div style="margin-top:6px">${esc(d.type_desc || '').split('. ').map((x, i, arr) => x + (i < arr.length - 1 ? '.' : '')).join('<br>')}</div></td></tr>
        <tr><th>세대 · 주민</th><td>${f.int(b.hh)}세대 · ${f.int(b.pop)}명 · 세대당 ${f.n2(b.pph)}명 ${rk(p, 'hh')}</td></tr>
        <tr><th>성별</th><td>여성 ${f.pct1(b.female)} · 남성 ${b.female == null ? NA : f.pct1(1 - b.female)}</td></tr>
        <tr><th>입주</th><td>${bd.move_in ? esc(String(bd.move_in).slice(0, 10)) + ' 입주 시작 · ' : ''}${f.n1(b.years)}년 경과 ${rk(p, 'years')}</td></tr>
        <tr><th>건물</th><td>${f.int(bd.buildings)}개 동 · 최고 ${f.int(bd.top_floor)}층 · 상가 ${f.int(bd.shops)}호</td></tr>
        <tr><th>주택 크기</th><td>평균 전용 ${f.n1(b.area_avg)}㎡ · 40㎡ 미만 ${f.pct(b.small_unit)} · 방 ${f.n1(b.rooms)}개(평균) ${rk(p, 'small_unit')}</td></tr>
        <tr><th>난방</th><td>${esc(b.heating || '') || NA}</td></tr>
        <tr><th>승강기</th><td>${f.int(bd.elevators)}대 · 100세대당 ${f.n1(b.elev100)}대 ${rk(p, 'elev100')}</td></tr>
        <tr><th>CCTV</th><td>${f.int(bd.cctv)}대 · 100세대당 ${f.n1(b.cctv100)}대 ${rk(p, 'cctv100')}</td></tr>
        <tr><th>주차</th><td>${f.int(bd.parking)}면 · 세대당 ${f.n2(b.parking)}면</td></tr>
        <tr><th>주거복지사</th><td>${b.deployed ? '배치' : '미배치'}</td></tr>
        <tr><th>단지 안 공간</th><td>${d.spaces.filter(s => s.has).map(s => esc(s.label)).join(', ') || '없음'} <span class="muted">(${f.int(b.n_space)}종)</span></td></tr>
        <tr><th>복지관</th><td>${wc.operator ? `운영 ${esc(wc.operator)}${wc.floors ? ' · ' + f.int(wc.floors) + '층' : ''}${wc.remodeled ? ' · 리모델링 ' + esc(String(wc.remodeled).slice(0, 10)) : ''}` : '단지 안 복지관 없음'}</td></tr>
      </tbody></table></div>
      <div class="grid" style="align-content:start">
        <div class="panel"><h3>필요 지수에 들어간 지표 <small class="muted">이 단지의 실제 값</small></h3>
          <div class="scroll" style="max-height:330px"><table class="tbl"><thead><tr><th>분야</th><th>지표</th><th class="r">이 단지 값</th><th class="r" data-tip="전체 단지 가운데 '필요가 큰 쪽'에서 본 위치. 상위일수록 이 지표로는 필요가 크다는 뜻입니다.">필요 쪽 위치 ⓘ</th></tr></thead>
            <tbody>${d.need.map(n => n.indicators.map((i, k) => `<tr>${k === 0 ? `<td rowspan="${n.indicators.length}">${domChip(n.domain, n.label)}</td>` : ''}<td>${esc(i.label)}</td><td class="r num">${indVal(i)}</td><td class="r num">${i.need_pct == null ? NA : pos(i.need_pct)}</td></tr>`).join('')).join('')}</tbody></table></div>
        </div>
        <div class="panel"><h3>연령 구성 <small class="muted">10세 단위, 명</small></h3>
          ${hbars(d.age_bands.map(x => ({ label: x.band.replace('미만', ' 미만'), value: x.n, color: ['60대', '70대'].includes(x.band) ? '#eb9a6a' : ['80대', '90대', '100대'].includes(x.band) ? '#c9521f' : '#5b9bd9', tip: `${x.band}: ${f.int(x.n).replace(/<[^>]+>/g, '')}명 (${Math.round((x.n || 0) / ageTot * 100)}%)` })), { max: ageMax, fmt: v => v.toLocaleString() + '명 · ' + Math.round(v / ageTot * 100) + '%' })}
          <div class="muted" style="font-size:0.867rem;margin-top:6px">60세 이상 ${f.pct(b.age60)} ${p.age60 != null ? '(' + pos(p.age60) + ')' : ''} · 80세 이상 ${f.pct(b.age80)} ${p.age80 != null ? '(' + pos(p.age80) + ')' : ''} · 20세 미만 ${f.pct(b.age_u20)}</div></div>
        <div class="panel"><h3>고독사 기록 <small class="muted">2019~2026</small></h3>
          ${ld.total ? `<div class="row" style="gap:14px;margin-bottom:8px"><div><b class="num" style="font-size:1.733rem;color:var(--bad)">${ld.total}건</b> <span class="muted">8년 합계</span></div>
</div>
            <div class="yearcells">${ld.by_year.map(y => `<div class="${y.value ? 'hit' : ''} ${y.value >= 2 ? 'hit2' : ''}" data-tip="${y.year}년: ${y.value || 0}건"><b class="num">${y.value || '·'}</b><span>${y.year.slice(2)}년</span></div>`).join('')}</div>`
      : `<div class="zero-note"><b class="num">0건</b><span>2019~2026년 관리 기록에 남은 건이 없습니다.</span></div>`}
</div>
      </div>
    </div>

    <div class="panel"><h3>운영 이력 <small class="muted">${esc(S.meta.months[0])}~${esc(S.meta.months.at(-1))} 활동 기록</small></h3>
      ${d.has_records ? `
        <div class="tiles"><div class="tile"><b class="num">${f.int(a.n_records)}건</b><span>활동 기록</span><em class="rank">기록 있는 단지 중 ${pos(p.n_records)}</em></div>
          ${Object.entries(a.by_year).map(([y, n]) => `<div class="tile"><b class="num">${n}건</b><span>${y}년${y === '2026' ? ' 상반기' : ''}</span></div>`).join('')}
          <div class="tile"><b class="num">${f.int(a.richness)}종</b><span>프로그램 종류</span><em class="rank">기록 있는 단지 중 ${pos(p.richness)}</em></div>
          <div class="tile"><b class="num">${f.pct(a.active_month_ratio)}</b><span>기록이 있는 달</span><em>30개월 가운데</em></div>
          <div class="tile" data-tip="두 번 이상 기록된 프로그램이 전체 기록에서 차지하는 비중"><b class="num">${f.pct(a.repeat_share)}</b><span>반복 운영 비중</span></div></div>
        <h4 style="margin-top:14px">월별 활동 기록 수</h4>
        ${monthBars(a.monthly, a.months, { h: 150, title: '월별 활동 기록 수' })}
        <div class="grid g2" style="margin-top:16px">
          <div><h4>많이 한 프로그램 <small class="muted">기록 건수</small></h4>
            <div class="toplist">${a.top.map(t => `<div><a href="#/programs/${t.std_id}">${esc(t.name)}</a><span class="bg"><span style="width:${(t.n / Math.max(1, a.top[0].n) * 100).toFixed(0)}%;background:${DOM[t.domain] || 'var(--accent)'}"></span></span><b class="num">${t.n}건</b><small>${esc(S.meta.needs[t.domain] || '여러 분야')} · 마지막 ${f.ym(t.last)}</small></div>`).join('')}</div></div>
          <div><h4>분야별 기록 비중 <small class="muted">한 프로그램이 여러 분야에 걸치면 나눠서 셉니다</small></h4>
            ${hbars(S.meta.need_ids.map(k => ({ label: S.meta.needs[k], value: a.domain_count[k], color: DOM[k] })), { fmt: v => Math.round(v / Object.values(a.domain_count).reduce((x, y) => x + y, 0) * 100) + '%' })}
            <h4 style="margin-top:12px">함께 한 기관 유형</h4><div class="row">${a.partner_types.length ? a.partner_types.map(x => `<span class="chip">${esc(x)}</span>`).join('') : '<span class="muted">기록에 적힌 협력기관이 없습니다</span>'}</div></div>
        </div>
        <h4 style="margin-top:16px">연도별 집계 <small class="muted">단지 통합표 기준(모든 기록 포함)</small></h4>
        ${yearTable(ex.community, [{ key: 'year', label: '연도' }, { key: 'records', label: '기록', r: 1 }, { key: 'sessions', label: '활동 횟수', r: 1 }, { key: 'participants', label: '참여 인원(연인원)', r: 1 }, { key: 'orgs', label: '참여 기관', r: 1 }, { key: 'kinds', label: '프로그램 이름 종류', r: 1 }, { key: 'shows', label: '문화예술공연', r: 1 }, { key: 'contest', label: '외부 공모사업', r: 1 }, { key: 'mou', label: '업무협약 연계', r: 1 }])}
        <div class="muted" style="font-size:0.867rem;margin-top:4px">참여 인원은 회차마다 더한 연인원이고 고유 주민 수가 아닙니다.</div>
        <h4 style="margin-top:16px">최근 기록 ${a.recent.length}건</h4>
        <div class="scroll" style="max-height:320px"><table class="tbl"><thead><tr><th>연월</th><th>활동 이름</th><th>표준 프로그램</th><th class="r">참여</th><th>장소</th></tr></thead>
          <tbody>${a.recent.map(r => `<tr><td class="num">${f.ym(r.month)}</td><td>${esc(r.title)}</td><td><a href="#/programs/${r.std_id}">${esc(r.std_name)}</a></td><td class="r num">${r.participants == null ? '<span class="muted">-</span>' : r.participants + '명'}</td><td>${r.place ? esc(r.place) : '<span class="muted">-</span>'}</td></tr>`).join('')}</tbody></table></div>`
      : `<div class="note warn"><b>기록 없음.</b> 이 단지는 활동 기록 자료에 없어 운영 이력을 보여 줄 수 없습니다. 0건이 아니라 자료가 없는 것입니다. 추천은 구성이 닮은 단지와 가까운 단지를 기준으로 냅니다.</div>`}
    </div>

    <div class="panel"><h3>프로그램 상태 <small class="muted">추천 대상 ${matrix.length}종</small></h3>
      <div class="row" id="stFilter" style="margin-bottom:8px"><button class="btn sm pri" data-s="">전체 ${matrix.length}</button>${ST_ORDER.filter(s => d.status_counts[s]).map(s => `<button class="btn sm" data-s="${s}" data-tip="${esc(ST_HELP[s])}">${esc(S.meta.status[s])} ${d.status_counts[s]}</button>`).join('')}</div>
      <div id="matrixBox"></div>
      <div class="muted" style="font-size:0.867rem;margin-top:6px">결측(자료 없음)·기록 없음·미운영·운영 불가능을 구분합니다. '미운영'은 기록 기준이며 실제로 했지만 기록하지 않은 경우를 가를 수 없습니다. 그런 프로그램은 추천 화면에서 '이미 운영 중'으로 표시해 주세요.</div>
    </div>

    <div class="grid g2">
      <div class="panel"><h3>가까운 시설까지 거리 <small class="muted">통합표의 지역 참고 중앙값과 비교</small></h3>
        <table class="tbl"><thead><tr><th>시설</th><th class="r">이 단지</th><th class="r">지역 중앙값</th><th></th></tr></thead><tbody>${d.near.map(x => { const ref = ex.region_ref[x.label]; const far = x.km != null && ref != null && x.km > ref * 1.5; return `<tr><td>${esc(x.label)}</td><td class="r num">${f.km(x.km)}</td><td class="r num">${ref == null ? NA : f.km(ref)}</td><td>${x.km == null || ref == null ? '' : far ? '<span class="chip warn">지역보다 먼 편</span>' : x.km < ref * 0.67 ? '<span class="chip ok">가까운 편</span>' : ''}</td></tr>`; }).join('')}</tbody></table>
        <div class="muted" style="font-size:0.867rem;margin-top:6px">'자료 없음'은 0km가 아니라 거리 자료가 비어 있는 것입니다. 반경 500m 안 시설 종류 ${f.int(b.n_fac500)}종.</div></div>
      <div class="panel"><h3>해피콜 만족도 <small class="muted">2025, 관리소 단위</small></h3>${happycallBlock(d.happycall, { full: true })}
        <div class="muted" style="font-size:0.867rem;margin-top:6px">점은 전체 관리소 가운데 이 관리소의 위치입니다. <a href="#/happycall">해피콜 탭</a>에서 전체 관리소와 주민 의견을 볼 수 있습니다.</div></div>
    </div>

    <div class="grid g2">
      <div class="panel"><h3>관리홈닥터 지원</h3>
        <div class="tiles"><div class="tile"><b class="num">${f.n1(hd.per100)}건</b><span>100세대당 월</span><em class="rank">${p.hd != null ? S.complexes.length + '곳 중 ' + pos(p.hd) : ''}</em></div>
          <div class="tile"><b class="num">${hd.trend == null ? NA : (hd.trend > 0 ? '+' : '') + Math.round(hd.trend * 100) + '%'}</b><span>최근 추세</span></div></div>
        <h4 style="margin-top:10px">지원 종류별 <small class="muted">100세대당 월</small></h4>
        ${hbars([['생활지원', hd.life], ['가사지원', hd.chores], ['의료지원', hd.medical], ['경제지원', hd.econ]].map(([l, v]) => ({ label: l, value: v })), { fmt: v => f.n1(v) + '건' })}
        <h4 style="margin-top:12px">월별 지원 건수 <small class="muted">2022년부터. 비어 있는 달은 자료 없음</small></h4>
        ${hd.months.length ? monthBars(hd.monthly, hd.months, { h: 110, showValues: false, color: '#6ea6d6', title: '월별 홈닥터 지원 건수' }) : NA}
        <div class="muted" style="font-size:0.867rem;margin-top:6px">이용 실적은 공급이 있어야 생기므로 필요 지수에는 넣지 않았습니다.</div></div>
      <div class="panel"><h3>협력·회의·일자리 기록</h3>
        <table class="info"><tbody>
          <tr><th>업무협약(2025)</th><td>${f.int(ex.mou.n)}건 · 사업 진행 중 ${f.int(ex.mou.active)}건 · 전문 인력 연계 ${f.int(ex.mou.expert)}건 · 종료 ${f.int(ex.mou.ended)}건</td></tr>
          <tr><th>일자리 지원(2025)</th><td>${f.int(ex.job.n)}건 · 세대 지원 ${f.int(ex.job.household)}건 · 취업 지원 ${f.int(ex.job.employment)}건</td></tr>
          <tr><th>유관기관 협력(2025)</th><td>${f.int(d.partnerships.gov)}건</td></tr>
          <tr><th>입주민·유관기관 회의</th><td>${ex.governance.map(g => `${esc(g.year)} ${g.value == null ? '자료 없음' : Math.round(g.value) + '건'}`).join(' · ')}</td></tr>
          <tr><th>안전 회의(TBM)</th><td>${ex.tbm.map(t => `${t.year}년 ${t.meetings == null ? '자료 없음' : Math.round(t.meetings) + '회(참석 ' + f.int(t.attendees).replace(/<[^>]+>/g, '') + '명)'}`).join(' · ')}</td></tr>
        </tbody></table>
        <h4 style="margin-top:14px">현장 메모</h4><textarea id="memo" rows="4" placeholder="${STATIC ? '이 단지에 대해 남겨 둘 내용(이 브라우저에만 저장됩니다)' : '이 단지에 대해 남겨 둘 내용(다른 사람도 볼 수 있습니다)'}">${esc(d.user.memo)}</textarea>
        <div class="row" style="margin-top:6px"><button class="btn sm" id="memoSave">저장</button><span class="muted" id="memoMsg" style="font-size:0.867rem"></span></div>
        <h4 style="margin-top:10px">제외·보류한 프로그램</h4>
        <div id="exList">${d.user.excluded.length ? d.user.excluded.map(e => `<div class="row between" style="padding:3px 0"><span>${esc(e.name)} <span class="chip ${e.kind === 'infeasible' ? 'bad' : e.kind === 'not_now' ? 'warn' : ''}">${esc(e.kind_label)}${e.kind === 'not_now' ? ' ' + e.count + '번' : ''}</span></span><button class="btn sm" data-restore="${e.std_id}">되돌리기</button></div>`).join('') : '<span class="muted">없음</span>'}</div></div>
    </div>

    <div class="panel"><h3>주민에게 안내할 수 있는 정부·지자체 복지서비스</h3><div id="wfBox"><div class="empty"><span class="spin"></span></div></div></div>

    <div class="grid g3">${Object.entries(kinds).map(([k, [t, h]], i) => `<div class="panel" data-toc="${i ? '-' : '비슷한 단지'}"><h3>${t}</h3><div class="muted" style="font-size:0.867rem;margin:-4px 0 6px">${h}</div>
      ${d.peers.filter(x => x.kind === k).map(x => `<div class="row between" style="padding:5px 0;border-bottom:1px solid var(--line2)"><a href="#/complex/${x.id}">${esc(x.name)}</a>
        <span class="muted" style="font-size:0.867rem" data-tip="구성 유사도 ${f.n2(x.struct)} · 운영 유사도 ${f.n2(x.behav)} · 거리 유사도 ${f.n2(x.geo)}">${esc(S.meta.types[x.type] || '')} · ${f.int(x.hh)}세대${x.same_branch ? ' · 같은 지사' : ''}</span></div>`).join('') || '<div class="muted">자료 없음</div>'}</div>`).join('')}</div>
  </div>`;

  buildToc(view);
  welfarePanel($('#wfBox'), cid);
  $('#needBox').addEventListener('click', async e => {
    const btn = e.target.closest('.seg button'); if (!btn) return;
    const domain = btn.parentElement.dataset.domain, level = btn.dataset.level || null;
    let note = '';
    if (level) note = prompt(`'${S.meta.needs[domain]}' 필요를 '${btn.textContent}'으로 확인한 근거를 한 줄로 남겨 주세요(선택).`, '') ?? '';
    try { await post('state/confirm', { id: cid, domain, level, note }); toast(level ? (STATIC ? '이 브라우저에 저장했습니다. 공개 시연판에서는 추천에 반영되지 않습니다.' : '확인된 필요를 저장했습니다. 추천에 반영됩니다.') : '확인 표시를 지웠습니다.'); render(view, undefined, alive); }
    catch (err) { toast(err.message); }
  });
  const cols = [{ key: 'name', label: '프로그램', html: r => `<a href="#/programs/${r.std_id}">${esc(r.name)}</a>` }, { key: 'domain', label: '분야', html: r => domChip(r.domain) },
  { key: 'status', label: '상태', html: r => stChip(r.status, r.status_label) }, { key: 'n', label: '기록 수', r: 1, fmt: (v, r) => r.status === 'no_record' ? NA : v },
  { key: 'last', label: '마지막 기록', fmt: v => v ? f.ym(v) : '<span class="muted">-</span>' }, { key: 'pop', label: '전체 단지 운영 비율', r: 1, fmt: f.pct }];
  const drawM = s => { const box = $('#matrixBox'); box.innerHTML = ''; box.append(table(cols, matrix.filter(r => !s || r.status === s), { sortKey: 'n' })); box.firstChild.style.maxHeight = '360px'; };
  drawM('');
  $('#stFilter').addEventListener('click', e => { const btn = e.target.closest('button'); if (!btn) return; $$('#stFilter button').forEach(x => x.classList.toggle('pri', x === btn)); drawM(btn.dataset.s); });
  $('#memoSave').addEventListener('click', async () => { await post('state/memo', { id: cid, memo: $('#memo').value }); $('#memoMsg').textContent = '저장했습니다'; });
  $('#exList').addEventListener('click', async e => { const btn = e.target.closest('[data-restore]'); if (!btn) return; await post('state/restore', { id: cid, sid: btn.dataset.restore }); toast('되돌렸습니다'); render(view, undefined, alive); });
}
