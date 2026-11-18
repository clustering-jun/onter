// 정적 판(GitHub Pages): 서버 없이 tools/build_static.py가 미리 계산해 둔 api/*.json만 읽는다.
// 조절값은 미리 계산한 격자 가운데 가장 가까운 값으로 맞추고, 사용자 입력(제외·확인·메모)은 이 브라우저에만 저장한다.
const files = {};
const get = name => files[name] || (files[name] = fetch(`api/${name}.json`).then(r => {
  if (!r.ok) { delete files[name]; throw new Error('자료를 불러오지 못했습니다.'); }
  return r.json();
}));
const snap = (v, grid) => grid.reduce((a, b) => Math.abs(b - v) < Math.abs(a - v) ? b : a);
const KIND = { infeasible: '운영 불가능', not_now: '지금은 아님', already: '이미 운영 중(기록 누락)' };
let grid = null;

const store = {
  all() { try { return JSON.parse(localStorage.getItem('onter.state') || '{}'); } catch { return {}; } },
  get(cid) { return { confirmed: {}, excluded: {}, memo: '', ...(this.all()[cid] || {}) }; },
  set(cid, st) { const a = this.all(); a[cid] = st; try { localStorage.setItem('onter.state', JSON.stringify(a)); } catch { } },
};
async function excludedView(cid) {
  const names = Object.fromEntries((await get('programs')).map(p => [p.std_id, p.name]));
  return Object.entries(store.get(cid).excluded).map(([sid, e]) => ({ std_id: sid, name: names[sid] || sid, kind: e.kind, kind_label: KIND[e.kind] || e.kind, count: e.count, note: e.note || '' }));
}
const planKey = b => `${snap(b.budget ?? grid.budget[0], grid.budget)}|${snap(b.n_max ?? grid.n_max[0], grid.n_max)}`;

export async function sget(path, p = {}) {
  switch (path) {
    case 'meta': { const m = await get('meta'); grid = m.grid; return m; }
    case 'complexes': case 'programs': case 'cases': case 'happycall': case 'analytics': case 'welfare': return get(path);
    case 'llm/status': return { available: false, static: true };
    case 'complex': {
      const d = structuredClone((await get('complex/' + p.id)).complex), st = store.get(p.id);
      d.user = { confirmed: st.confirmed, excluded: await excludedView(p.id), memo: st.memo };
      for (const v of Object.values(d)) if (Array.isArray(v) && v[0] && 'confirmed' in v[0]) v.forEach(r => { const c = st.confirmed[r.domain]; r.confirmed = c ? c.level : null; r.confirmed_note = c ? c.note : null; });
      return d;
    }
    case 'matrix': return (await get('complex/' + p.id)).matrix;
    case 'program': return get('program/' + p.sid);
    case 'candidate': {
      const c = (await get('cand/' + p.id))[p.sid];
      if (!c) throw new Error('이 후보의 상세 자료는 정적 판에 들어 있지 않습니다.');
      return { ...c.detail };
    }
    case 'recommend': {
      const all = await get('rec/' + p.id), r = all[`${snap(+p.w, grid.w)}|${snap(+p.lam, grid.lam)}`], k = +p.k || 10;
      const ex = new Set(Object.keys(store.get(p.id).excluded)), keep = x => !ex.has(x.std_id);
      const items = r.items.filter(keep).slice(0, k).map((x, i) => ({ ...x, rank: i + 1 }));
      return { ...r, k, items, by_domain: r.by_domain.map(d => ({ ...d, items: d.items.filter(keep) })), list_mix: r.mix[k] || r.list_mix, ms: 0 };
    }
    case 'state': return { ...store.get(p.id), excluded_view: await excludedView(p.id) };
    case 'search': {
      const q = (p.q || '').trim(), n = q.replace(/\s/g, '');
      if (!q) return { q, programs: [], complexes: [], cards: [], news: [] };
      const [progs, cxs, cases] = await Promise.all([get('programs'), get('complexes'), get('cases')]);
      const hit = (s, t = n) => String(s || '').replace(/\s/g, '').includes(t);
      const name = progs.filter(x => hit(x.name)), rest = progs.filter(x => !hit(x.name) && Object.values(x).some(v => typeof v === 'string' && hit(v)));
      return {
        q, programs: [...name, ...rest].slice(0, 12).map(x => ({ std_id: x.std_id, name: x.name })),
        complexes: cxs.filter(c => hit(c.name, q) || hit(c.addr, q)).slice(0, 10).map(c => ({ id: c.id, name: c.name })),
        cards: (cases.cards || []).filter(c => hit(c.headline) || hit(c.name)).slice(0, 6).map(c => ({ card_id: c.card_id, headline: c.headline || '' })), news: [],
      };
    }
  }
  throw new Error('정적 판에 없는 자료입니다: ' + path);
}

export async function spost(path, b = {}) {
  const st = b.id ? store.get(b.id) : null;
  switch (path) {
    case 'plan': return (await get('plan/' + b.id))[planKey(b)].plan;
    case 'llm/plan': return (await get('plan/' + b.id))[planKey(b)].brief;
    case 'llm/explain': return (await get('cand/' + b.id))[b.sid].explain;
    case 'llm/checklist': return (await get('cand/' + b.id))[b.sid].checklist;
    case 'state/exclude': {
      const n = (st.excluded[b.sid]?.count || 0) + 1;
      st.excluded[b.sid] = { kind: b.kind, count: n, note: b.note || '' }; store.set(b.id, st);
      return { ok: true, count: n, will_resurface: false };
    }
    case 'state/restore': delete st.excluded[b.sid]; store.set(b.id, st); return { ok: true };
    case 'state/confirm': if (b.level) st.confirmed[b.domain] = { level: b.level, note: b.note || '' }; else delete st.confirmed[b.domain]; store.set(b.id, st); return { ok: true, state: st };
    case 'state/memo': st.memo = b.memo || ''; store.set(b.id, st); return { ok: true };
  }
  throw new Error('정적 판에서는 할 수 없는 요청입니다: ' + path);
}
