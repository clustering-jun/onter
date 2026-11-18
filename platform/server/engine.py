"""온터 플랫폼 엔진: project/model의 네 모듈을 메모리에 올려 두고 단지 한 곳 단위로 빠르게 다시 계산한다.

- 순위·묶음 선택은 요청마다 한 단지만 계산한다(96개 프로그램 벡터 연산 + 정수계획, 수 밀리초).
- 상태 구분: 결측(자료 없음) / 기록 없음(단지에 활동 기록 자체가 없음) / 미운영(기록은 있는데 이 프로그램은 없음) /
  운영 중(최근 12개월) / 과거 운영(12개월 넘게 기록 없음) / 운영 불가능(사용자 표시) / 보류(지금은 아님) / 기록 누락(사용자 표시).
- 후보가 모자랄 때 제외한 프로그램을 되살려 채우지 않는다. 채우는 순서는 ① 과거 운영(재개 검토) ② 보류 1~2회인 것까지.
"""
import json
import math
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # project/platform
PROJECT = ROOT.parent
sys.path.insert(0, str(PROJECT / "model"))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from onter import config as C, data as D, features as F, m1_profile as M1, m2_cases as M2, m3_rank as R, m4_feasibility as M4, explain as X, expert as XP

from concurrent.futures import ThreadPoolExecutor

# 계산은 모두 이 일꾼 스레드 하나에서 한다. 요청마다 생겼다 사라지는 스레드에서 pandas·numpy를 돌리면
# Windows에서 프로세스가 접근 위반으로 죽는 일이 있었다(요청 스레드는 입출력만 맡는다).
_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="engine")


def run(fn):
    return _EXEC.submit(fn).result()

TYPE_LABEL = {"S1": "젊은 국민임대형", "S2": "고령 영구임대형", "S3": "원격형"}
LEVEL = {"high": 0.9, "mid": 0.5, "low": 0.1}                      # 확인된 필요 → 필요 백분위 자리에 넣는 값
LEVEL_KO = {"high": "높음", "mid": "보통", "low": "낮음"}
SPACES = [("sp_senior", "경로당"), ("sp_welfare", "복지관"), ("sp_hall", "주민공동시설·집회소"), ("sp_library", "도서관"), ("sp_daycare", "어린이집"), ("sp_gym", "체육시설")]
NEAR = [("d_경로당", "경로당"), ("d_노인복지관", "노인복지관"), ("d_종합사회복지관", "종합사회복지관"), ("d_보건기관", "보건기관"), ("d_의원", "의원"),
        ("d_병원", "병원"), ("d_응급의료시설", "응급의료시설"), ("d_약국", "약국"), ("d_초등학교", "초등학교"), ("d_어린이집", "어린이집")]
CONFIRMED_MIN = 2                                                    # 확인된 필요가 '높음'인 분야에서 목록에 먼저 넣는 개수
PCT_KEYS = ["hh", "age60", "age80", "age_u20", "pph", "years", "small_unit", "hd", "area_avg", "elev100", "cctv100"]
MAX_RESURFACE = 2                                                    # '지금은 아님'으로 뺀 프로그램을 후보 부족 때 다시 보여 줄 수 있는 횟수
UNCERTAIN_WIDTH = 0.25                                               # 필요 구간 폭이 이보다 넓으면 '불확실'로 흐리게 표시


def clean(o):
    """JSON으로 내보낼 수 있게 numpy·NaN을 정리한다. NaN은 None(=결측)."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [clean(v) for v in o]
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if o is pd.NA or o is pd.NaT:
        return None
    if isinstance(o, (pd.Timestamp, pd.Period)):
        return str(o)
    return o


def prank(v, mask):
    """mask 안에서의 백분위 순위(pandas rank(pct=True)와 같다). mask 밖은 NaN."""
    out = np.full(len(v), np.nan)
    if mask.any():
        out[mask] = rankdata(v[mask]) / mask.sum()
    return out


class Engine:
    def __init__(self):
        t0 = time.time()
        self.c, self.p = D.complexes(), D.programs()
        self.ids, self.items = list(self.c.index), list(self.p.index)
        self.ix = {cid: i for i, cid in enumerate(self.ids)}
        self.jx = {sid: j for j, sid in enumerate(self.items)}
        first, last = C.FIRST_MONTH, C.LAST_MONTH
        self.recent_from = str(pd.Period(last, "M") - 11)
        self.Xb = F.interactions(first, last).reindex(index=self.ids, columns=self.items).fillna(0)
        self.Xc = F.interactions(first, last, "count").reindex(index=self.ids, columns=self.items).fillna(0)
        self.X12 = F.interactions(self.recent_from, last).reindex(index=self.ids, columns=self.items).fillna(0)
        self.xb, self.x12, self.xc = self.Xb.to_numpy() > 0, self.X12.to_numpy() > 0, self.Xc.to_numpy()
        self.act = set(F.active_complexes(first, last))
        self.has_rec = np.array([cid in self.act for cid in self.ids])
        r = F.window(first, last)
        self.records = r[r["std_id"].isin(self.items)]
        g = self.records.groupby(["complex_id", "std_id"])["ym"]
        self.last_ym = g.max().to_dict()
        self.month_counts = r.groupby(["complex_id", "ym"]).size()
        self.months = [str(m) for m in pd.period_range(first, last, freq="M")]

        # 모듈 1
        pf = C.OUTPUTS / "m1_complex_profile.csv"
        self.prof = (pd.read_csv(pf, index_col=0) if pf.exists() else M1.profile()).reindex(self.ids)
        self.need = M1.need_table("S").reindex(self.ids)[C.NEED_IDS]
        self.need_np = self.need.to_numpy()
        self.base = M1.demand_base("complex").reindex(self.ids)[C.NEED_IDS].to_numpy()
        self.M = F.need_membership().reindex(self.items)[C.NEED_IDS].fillna(0)
        self.Mm = self.M.to_numpy()
        T = F.target_membership()
        nf = R.need_fit(self.Xb, self.M, need=self.need, T=T).to_numpy()
        raw = self.need_np @ self.Mm.T
        self.TF = np.where(raw > 0, nf / np.where(raw > 0, raw, 1), 1.0)       # 대상 적합 배수(단지×프로그램)

        # 모듈 2
        self.S = M2.sim_matrix("hybrid")
        self.IS = M2.item_sim("hybrid")
        pe = C.OUTPUTS / "m2_complex_peers.csv"
        self.peers_tbl = pd.read_csv(pe) if pe.exists() else pd.DataFrame()
        act_ix = np.array([self.ix[c_] for c_ in self.ids if c_ in self.act])
        Sn = self.S.reindex(index=self.ids, columns=self.ids).to_numpy().copy()
        np.fill_diagonal(Sn, -np.inf)
        k = R.DEFAULT["k_peer"]
        self.peer_ix = act_ix[np.argsort(-Sn[:, act_ix], axis=1)[:, :k]]      # 단지별 이웃 20곳(기록 있는 단지 중)
        self.peer_n = np.stack([self.xb[self.peer_ix[u]].sum(0) for u in range(len(self.ids))])
        self.peer_k = k

        # 모듈 3 성분(단지×프로그램 원점수)
        self.knn = R.userknn(self.Xb, self.S, k).to_numpy()
        self.ease = R.ease(self.Xb).to_numpy()
        self.pop = self.xb[self.has_rec].mean(0)
        self.prim = self.p["need_primary"]
        self.prim_np = np.array([x if isinstance(x, str) else "" for x in self.prim])

        # 모듈 4
        req, self.cap = M4.requirements(), M4.capacity()
        self.expert = XP.available()
        if self.expert:
            req = M4.apply_expert(req, XP.sheet_b())
            self.feas, self.comp = M4.feasibility_expert(req, self.cap)
        else:
            self.feas, self.comp = M4.feasibility(req, self.cap)
        self.req = req.reindex(self.items)
        self.feas_np = self.feas.reindex(index=self.ids, columns=self.items).to_numpy()
        dp = C.TABLES / "e5_deployment_dependence.csv"
        dep = pd.read_csv(dp).set_index("std_id") if dp.exists() else pd.DataFrame(columns=["lo", "mh_or"])
        self.dep_data = {s: bool(dep.at[s, "lo"] > 1) for s in dep.index}
        self.needs_ww = self.req["x_needs_welfare_worker"].fillna(0).to_numpy().astype(bool) if self.expert else np.zeros(len(self.items), bool)
        self.deployed = self.cap["deployed"].reindex(self.ids).fillna(0).to_numpy().astype(bool)

        # 검색 색인, 해피콜, 캐시된 LLM 문장
        self.search_ix = M2.ProgramSearch(M2.train_title_docs(first, last))
        self._load_happycall()
        self.llm_cache = {}
        lf = C.OUTPUTS / "llm" / "explanations_llm.jsonl"
        if lf.exists():
            for line in lf.open(encoding="utf-8"):
                try:
                    x = json.loads(line)
                    self.llm_cache[x["key"]] = dict(text=x["text"], source=x["source"], draft=x["draft"])
                except (json.JSONDecodeError, KeyError):
                    continue
        self.og, self.rs = D.codebook()["partner_org"], D.codebook()["resource"]
        self.ind_base = M1._base()                                      # 필요 지표 원값(접근성 묶음 포함)
        self.pct = {k: F.pct_rank(self.c[k].astype(float)) for k in PCT_KEYS}
        act_ids = [c_ for c_ in self.ids if c_ in self.act]
        for k in ("n_records", "richness"):
            self.pct[k] = F.pct_rank(self.prof.loc[act_ids, k].astype(float)).reindex(self.ids)
        mp = C.DATA / "complex_month_panel_20261117_v1" / "complex_month_panel.csv"
        self.hd_panel = {}
        if mp.exists():
            m = pd.read_csv(mp, usecols=["complex_id", "target_month", "source_observed", "recorded_support_count"])
            m.loc[m["source_observed"] != 1, "recorded_support_count"] = np.nan
            self.hd_panel = {cid: (list(g["target_month"]), [None if pd.isna(v) else int(v) for v in g["recorded_support_count"]]) for cid, g in m.sort_values("target_month").groupby("complex_id")}
        self.type_info = self._type_info()
        raw = C.DATA / "complex_integrated_20261117_v1" / "data" / "complex_master.csv"
        self.raw = pd.read_csv(raw, low_memory=False).set_index("complex_id").reindex(self.ids) if raw.exists() else pd.DataFrame(index=self.ids)
        self.ld = self.c["ld_total"].reindex(self.ids).fillna(0).astype(int)
        self.load_sec = round(time.time() - t0, 1)

    def extra(self, cid):
        """단지 통합표의 나머지 자료: 고독사 기록, 회의·협약·일자리, 연도별 커뮤니티 집계, 건물, 복지관, 지역 기준 거리."""
        r = self.raw.loc[cid] if cid in self.raw.index else pd.Series(dtype=object)
        g = lambda k: None if k not in r.index or pd.isna(r[k]) else (r[k].item() if hasattr(r[k], "item") else r[k])
        yrs = lambda fmt, years: [dict(year=str(y), value=g(fmt.format(y))) for y in years]
        comm = []
        for y in (2024, 2025, 2026):
            comm.append(dict(year=str(y) + ("(상반기)" if y == 2026 else ""), records=g(f"커뮤니티_{y}_관측행수"), sessions=g(f"커뮤니티_{y}_활동횟수"), participants=g(f"커뮤니티_{y}_참여인원_계"),
                             individuals=g(f"커뮤니티_{y}_참여인원_개인"), orgs=g(f"커뮤니티_{y}_참여기관수"), kinds=g(f"커뮤니티_{y}_프로그램명종류"),
                             shows=g(f"커뮤니티_{y}_문화예술공연여부_Y행수"), contest=g(f"커뮤니티_{y}_외부공모사업여부_Y행수"), mou=g(f"커뮤니티_{y}_업무협약여부_Y행수")))
        gov = yrs("거버넌스_{}_회의건수", (2022, 2023, 2024, 2025)) + [dict(year="2026(상반기)", value=g("거버넌스_2026_상반기_회의건수"))]
        ref = {lab: g(f"지역참고_{lab}_지역중앙값_km") for _, lab in NEAR}
        return dict(
            lonely_death=dict(by_year=yrs("고독사_{}_기록발생건수", range(2019, 2027)), total=int(self.ld.get(cid, 0)),
                              n_complexes_any=int((self.ld > 0).sum()), rank_pct=float((self.ld <= self.ld.get(cid, 0)).mean())),
            governance=gov, community=comm,
            tbm=[dict(year="2024", meetings=g("TBM_2024_관측행수"), attendees=g("TBM_2024_총참석자수")), dict(year="2025", meetings=g("TBM_2025_관측행수"), attendees=g("TBM_2025_총참석자수"))],
            mou=dict(n=g("업무협약_2025_기록건수"), ended=g("업무협약_2025_협약종료여부_Y행수"), expert=g("업무협약_2025_전문인력여부_Y행수"), active=g("업무협약_2025_사업진행여부_Y행수")),
            job=dict(n=g("일자리지원_2025_기록건수"), household=g("일자리지원_2025_세대지원여부_Y행수"), employment=g("일자리지원_2025_취업지원여부_Y행수")),
            building=dict(village=g("마을명"), units_built=g("건설호수"), buildings=g("건설동수"), top_floor=g("최고층수"), low_floor=g("최저층수"), shops=g("상가호수"),
                          opened=g("단지개소일자"), move_in=g("입주지정시작일자"), elevators=g("승강기대수"), cctv=g("CCTV대수"), parking=g("주차_관측합계")),
            welfare_center=dict(operator=g("복지관운영주체명"), floors=g("복지관층수"), remodeled=g("복지관리모델링일자"), elevator=g("복지관승강기설치일자")),
            region_ref=ref)

    def _type_info(self):
        """단지 유형 3종의 설명. 숫자는 그 유형 단지들의 중앙값이다."""
        c, t = self.c, self.prof["type"]
        med = lambda ty, k: float(c.loc[t == ty, k].median())
        out = {}
        for ty, lab in TYPE_LABEL.items():
            n = int((t == ty).sum())
            facts = f"60세 이상 {med(ty, 'age60'):.0%}, 세대당 {med(ty, 'pph'):.1f}명, 입주 {med(ty, 'years'):.0f}년, {med(ty, 'hh'):,.0f}세대"
            if ty == "S1":
                desc = "가족 세대가 많고 고령 비율이 낮은 단지. 국민임대가 대부분이다."
            elif ty == "S2":
                desc = "혼자 사는 고령 세대가 많은 오래된 영구임대 단지. 대부분 40㎡ 미만이고 복지관이 가깝다."
            else:
                desc = (f"주변 시설이 먼 단지. 병원까지 {med(ty, 'd_병원'):.1f}km, 노인복지관까지 {med(ty, 'd_노인복지관'):.1f}km(다른 유형은 "
                        f"{med('S2', 'd_병원'):.1f}km, {med('S2', 'd_노인복지관'):.1f}km 안팎)로, 어린이집·약국 같은 생활 시설도 멀다. 규모가 작고 고령 비율은 중간이다.")
            out[ty] = dict(label=lab, n=n, desc=desc, facts=facts)
        return out

    # ───────── 해피콜 ─────────
    def _load_happycall(self):
        hp = C.DATA / "happycall_2025_v1"
        ms = pd.read_csv(hp / "management_scores.csv")
        mp = pd.read_csv(C.DATA / "complex_keys_20261117_v1" / "happycall_office_map_confirmed.csv")
        self.hc_scores = ms
        self.hc_by_complex = {}
        self.hc_ref = {}                                                # 점수별 전체 관리소 평균·개수(상대 비교용)
        for k in ("overall_satisfaction", "welfare_satisfaction", "housing_management_satisfaction", "rental_operation_satisfaction"):
            v = ms[k].dropna()
            self.hc_ref[k] = dict(mean=float(v.mean()), n=int(len(v)), values=np.sort(v.to_numpy()))
        ms_ix = ms.set_index("source_name")
        for _, m in mp.iterrows():
            cid = m["complex_id"]
            if not isinstance(cid, str):
                continue
            shared = m["complexes_for_office"] and m["complexes_for_office"] > 1
            row = ms_ix.loc[m["source_name"]] if m["source_name"] in ms_ix.index else None
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            self.hc_by_complex.setdefault(cid, []).append(dict(office=m["source_name"], shared=bool(shared), n_complexes=int(m["complexes_for_office"] or 1), row=row))

    def happycall_for(self, cid):
        """단지의 해피콜 만족도와 상태. 통합 관리소 값은 단지 값이 아니므로 참고로만 준다."""
        hs = self.hc_by_complex.get(cid)
        if not hs:
            return dict(status="no_link", label="연결된 관리소 조사 결과 없음")
        h = hs[0]
        r = h["row"]
        if r is None:
            return dict(status="no_link", label="연결된 관리소 조사 결과 없음")
        f = lambda k: None if pd.isna(r[k]) else float(r[k])
        out = dict(office=h["office"], n=int(r["n_total"]), n_welfare=None if pd.isna(r.get("n_welfare")) else int(r["n_welfare"]), small_sample=bool(r["small_sample"]),
                   overall=f("overall_satisfaction"), welfare=f("welfare_satisfaction"), housing=f("housing_management_satisfaction"),
                   rental=f("rental_operation_satisfaction"), major=f("major_service_satisfaction"), branch_rank=None if pd.isna(r.get("branch_rank")) else int(r["branch_rank"]))
        cmp_ = {}
        for key, col in (("overall", "overall_satisfaction"), ("welfare", "welfare_satisfaction"), ("housing", "housing_management_satisfaction"), ("rental", "rental_operation_satisfaction")):
            ref, v = self.hc_ref[col], out[key]
            if v is not None:
                rank = int((ref["values"] > v).sum()) + 1               # 1위가 가장 높은 점수
                cmp_[key] = dict(value=v, mean=ref["mean"], diff=v - ref["mean"], rank=rank, of=ref["n"], top_pct=rank / ref["n"])
            else:
                cmp_[key] = None
        out["compare"] = cmp_
        out["n_median"] = float(self.hc_scores["n_total"].median())
        if h["shared"]:
            out.update(status="shared", label=f"통합 관리소({h['n_complexes']}개 단지 합산) 값이라 이 단지의 값으로 보지 않음")
        elif out["small_sample"]:
            out.update(status="small", label="응답 수가 적어 참고만")
        else:
            out.update(status="ok", label="관리소 단위 조사 결과")
        if out["welfare"] is None:
            out["welfare_label"] = "복지 문항 응답 없음"
        return out

    # ───────── 상태 구분 ─────────
    def statuses(self, cid, st=None):
        """프로그램별 상태. st: 이 단지의 사용자 상태(store) — excluded {sid: {kind, count}}."""
        u = self.ix[cid]
        ex = (st or {}).get("excluded", {})
        out = {}
        for j, sid in enumerate(self.items):
            e = ex.get(sid)
            if e and e.get("kind") == "infeasible":
                s = "infeasible"
            elif e and e.get("kind") == "already":
                s = "declared"
            elif self.x12[u, j]:
                s = "running"
            elif self.xb[u, j]:
                s = "paused"
            elif e and e.get("kind") == "not_now":
                s = "snoozed"
            elif not self.has_rec[u]:
                s = "no_record"
            else:
                s = "not_run"
            out[sid] = s
        return out

    STATUS_KO = {"running": "운영 중", "paused": "과거 운영", "not_run": "미운영", "no_record": "기록 없음", "infeasible": "운영 불가능", "snoozed": "보류", "declared": "운영 중(기록 누락)"}

    # ───────── 단지 목록·상세 ─────────
    def complex_list(self):
        c, pf = self.c, self.prof
        out = []
        for u, cid in enumerate(self.ids):
            hc = self.happycall_for(cid)
            ad = str(c.at[cid, "addr"]).split()
            out.append(dict(id=cid, name=c.at[cid, "name"], branch=c.at[cid, "branch"], lat=c.at[cid, "lat"], lon=c.at[cid, "lon"], region=c.at[cid, "region"], sido=ad[0] if ad else None, sgg=ad[1] if len(ad) > 1 else None, addr=c.at[cid, "addr"],
                            supply=c.at[cid, "supply"], type=pf.at[cid, "type"], hh=c.at[cid, "hh"], age60=c.at[cid, "age60"], age80=c.at[cid, "age80"],
                            age_u20=c.at[cid, "age_u20"], pph=c.at[cid, "pph"], years=c.at[cid, "years"], deployed=int(c.at[cid, "deployed"]),
                            has_records=bool(self.has_rec[u]), n_records=pf.at[cid, "n_records"] if self.has_rec[u] else None,
                            richness=pf.at[cid, "richness"] if self.has_rec[u] else None, n_priority=pf.at[cid, "n_priority"],
                            need={d: self.need.at[cid, d] for d in C.NEED_IDS}, sp_senior=int(c.at[cid, "sp_senior"]), sp_welfare=int(c.at[cid, "sp_welfare"]),
                            hd=c.at[cid, "hd"], ld=int(self.ld.get(cid, 0)), small_unit=c.at[cid, "small_unit"], hc_n=hc.get("n"), hc_small=hc.get("small_sample"),
                            hc_welfare=hc.get("welfare") if hc.get("status") == "ok" else None,
                            hc_overall=hc.get("overall") if hc.get("status") == "ok" else None))
        return clean(out)

    def need_view(self, cid, st=None):
        """분야별 필요: 지수·구간·공급·어긋남과 사용자가 확인한 값."""
        pf, conf = self.prof, (st or {}).get("confirmed", {})
        out = []
        for d in C.NEED_IDS:
            lo, hi = pf.at[cid, f"need_lo_{d}"], pf.at[cid, f"need_hi_{d}"]
            cf = conf.get(d)
            out.append(dict(domain=d, label=C.NEED[d], need=self.need.at[cid, d], lo=lo, hi=hi, width=hi - lo, uncertain=bool(hi - lo > UNCERTAIN_WIDTH),
                            supply_pct=pf.at[cid, f"supply_pct_{d}"], supply_rate=pf.at[cid, f"supply_rate_{d}"], supply_share=pf.at[cid, f"supply_share_{d}"],
                            gap=pf.at[cid, f"gap_{d}"], priority=bool(pf.at[cid, f"priority_{d}"] == 1),
                            confirmed=cf.get("level") if cf else None, confirmed_note=cf.get("note") if cf else None,
                            indicators=[self._ind(cid, col, sign, lab) for col, sign, w, lab in M1.INDICATORS[d]["S"]]))
        return out

    def _ind(self, cid, col, sign, lab):
        """필요 지표 하나: 원값과 '필요가 큰 쪽' 기준 백분위(1에 가까울수록 필요가 큼)."""
        base = self.ind_base
        if col not in base.columns:
            return dict(label=lab, sign=sign, value=None, need_pct=None)
        s = base[col].astype(float)
        v = s.at[cid]
        r = F.pct_rank(sign * s).at[cid]
        return dict(label=lab, sign=sign, value=None if pd.isna(v) else float(v), need_pct=None if pd.isna(r) else float(r), composite=col.startswith("acc_"))

    def complex_detail(self, cid, st=None):
        c, pf, u = self.c.loc[cid], self.prof.loc[cid], self.ix[cid]
        has = bool(self.has_rec[u])
        mc = [int(self.month_counts.get((cid, m), 0)) for m in self.months]
        peers = []
        if len(self.peers_tbl):
            pt = self.peers_tbl[self.peers_tbl["complex_id"] == cid]
            for kind in ("hybrid", "struct", "geo"):
                for _, x in pt[pt["kind"] == kind].head(6).iterrows():
                    peers.append(dict(kind=kind, id=x["peer_id"], name=x["peer"], similarity=x["similarity"], struct=x["struct_sim"], behav=x["behav_sim"], geo=x["geo_sim"],
                                      same_branch=int(x["same_branch"]), type=self.prof.at[x["peer_id"], "type"], hh=self.c.at[x["peer_id"], "hh"]))
        stt = self.statuses(cid, st)
        counts = pd.Series(stt).value_counts().to_dict()
        dom_mix = dom_cnt = by_year = None
        recent = []
        if has:
            dm = self.xc[u] @ self.Mm
            dom_mix = {d: float(v) for d, v in zip(C.NEED_IDS, dm / dm.sum())} if dm.sum() > 0 else None
            dom_cnt = {d: float(v) for d, v in zip(C.NEED_IDS, dm)}
            by_year = {}
            for m_, n_ in zip(self.months, mc):
                by_year[m_[:4]] = by_year.get(m_[:4], 0) + n_
            rr = self.records[self.records["complex_id"] == cid].sort_values("start_date", ascending=False).head(15)
            recent = [dict(month=x["ym"], title=str(x["program_name_masked"])[:60], std_id=x["std_id"], std_name=self.p.at[x["std_id"], "name"],
                           participants=None if pd.isna(x["participants_total"]) else int(x["participants_total"]),
                           place=None if pd.isna(x["place_masked"]) else str(x["place_masked"])[:24]) for _, x in rr.iterrows()]
        hdm = self.hd_panel.get(cid, ([], []))
        pct = {k: (None if pd.isna(v.get(cid, np.nan)) else float(v.get(cid))) for k, v in self.pct.items()}
        top10 = self.Xc.loc[cid].sort_values(ascending=False)
        top = [dict(std_id=s, name=self.p.at[s, "name"], n=int(n), last=self.last_ym.get((cid, s)), domain=self.prim_np[self.jx[s]] or None) for s, n in top10.head(10).items() if n > 0]
        out = dict(
            id=cid, name=c["name"], branch=c["branch"], addr=c["addr"], region=c["region"], supply=c["supply"], type=pf["type"], type_label=TYPE_LABEL.get(pf["type"], pf["type"]),
            type_desc=self.type_info.get(pf["type"], {}).get("desc"), pct=pct,
            basics=dict(hh=c["hh"], pop=c["pop"], pph=c["pph"], age60=c["age60"], age70=c["age70"], age80=c["age80"], age_u20=c["age_u20"], age_work=c["age_work"],
                        female=c["female"], years=c["years"], area_avg=c["area_avg"], small_unit=c["small_unit"], elev100=c["elev100"], cctv100=c["cctv100"],
                        heating=c["heating"], deployed=int(c["deployed"]), rooms=c["rooms"], parking=c["parking"], n_space=c["n_space"], n_fac500=c["n_fac500"]),
            age_bands=[dict(band=b, n=c[f"n_{b}"]) for b in ["10대미만", "10대", "20대", "30대", "40대", "50대", "60대", "70대", "80대", "90대", "100대"]],
            spaces=[dict(label=lab, has=int(c[k]), operator=c["welfare_operator"] if k == "sp_welfare" and isinstance(c["welfare_operator"], str) else None) for k, lab in SPACES],
            near=[dict(label=lab, km=None if pd.isna(c[k]) else float(c[k])) for k, lab in NEAR],
            home_doctor=dict(per100=c["hd"], life=c["hd_life"], chores=c["hd_chores"], medical=c["hd_medical"], econ=c["hd_econ"], trend=c["hd_trend"],
                             months=hdm[0], monthly=hdm[1]),
            partnerships=dict(mou=c["mou25"], job=c["job25"], gov=c["gov25"]),
            has_records=has,
            activity=dict(n_records=pf["n_records"] if has else None, richness=pf["richness"] if has else None, active_month_ratio=pf["active_month_ratio"] if has else None,
                          last_month=pf["last_month"] if has else None, repeat_share=pf["repeat_share"] if has else None,
                          n_recent12=int(sum(mc[-12:])) if has else None, months=self.months, monthly=mc if has else None, top=top, domain_mix=dom_mix,
                          domain_count=dom_cnt, by_year=by_year, recent=recent,
                          partner_types=[self.og.get(o, o) for o in str(pf["partner_types"]).split("|")] if has and isinstance(pf["partner_types"], str) else []),
            need=self.need_view(cid, st), n_priority=pf["n_priority"], status_counts=counts,
            peers=peers, happycall=self.happycall_for(cid), extra=self.extra(cid),
            user=dict(confirmed=(st or {}).get("confirmed", {}), excluded=self._excluded_view(st), memo=(st or {}).get("memo", "")))
        return clean(out)

    def _excluded_view(self, st):
        kinds = {"infeasible": "운영 불가능", "not_now": "지금은 아님", "already": "이미 운영 중(기록 누락)"}
        return [dict(std_id=s, name=self.p.at[s, "name"], kind=e["kind"], kind_label=kinds.get(e["kind"], e["kind"]), count=e.get("count", 1), note=e.get("note", ""), ts=e.get("ts"))
                for s, e in ((st or {}).get("excluded", {})).items() if s in self.jx]

    def program_matrix(self, cid, st=None):
        """단지의 전체 프로그램 상태표(분야별)."""
        u, stt = self.ix[cid], self.statuses(cid, st)
        rows = [dict(std_id=s, name=self.p.at[s, "name"], family=self.p.at[s, "family_label"], domain=self.prim_np[j], status=stt[s], status_label=self.STATUS_KO[stt[s]],
                     n=int(self.xc[u, j]), last=self.last_ym.get((cid, s)), pop=float(self.pop[j])) for j, s in enumerate(self.items)]
        return clean(rows)

    # ───────── 순위 ─────────
    def _need_vec(self, u, st):
        """필요 벡터와 목표 분포. 사용자가 확인한 분야는 그 값으로 바꾼다."""
        need = self.need_np[u].copy()
        conf = (st or {}).get("confirmed", {})
        for i, d in enumerate(C.NEED_IDS):
            lv = (conf.get(d) or {}).get("level")
            if lv in LEVEL:
                need[i] = LEVEL[lv]
        q = self.base[u] * np.exp(R.DEFAULT["beta"] * (need - need.mean()))
        return need, q / q.sum()

    def _scores(self, u, w, mask, need):
        """mask 안에서 근거·필요 순위를 섞은 점수와 성분."""
        ev = np.nanmean(np.stack([prank(self.knn[u], mask), prank(self.ease[u], mask), prank(self.pop, mask)]), axis=0)
        evr = prank(np.nan_to_num(ev, nan=-1), mask)
        nfv = (need @ self.Mm.T) * self.TF[u]
        nfr = prank(nfv, mask)
        return (1 - w) * evr + w * nfr, evr, nfr

    @staticmethod
    def _calib(score, avail, Mm, q, k, lam, alpha=0.01, seed=()):
        """필요 보정 재순위(한 단지). 후보가 모자라면 있는 만큼만 돌려준다(다른 프로그램으로 채우지 않는다).

        seed: 먼저 넣을 프로그램 색인(확인된 필요가 '높음'인 분야의 상위 후보). 나머지 자리는 보정 재순위로 채운다.
        """
        avail = avail.copy()
        r = prank(score, avail)
        acc, q, top = np.zeros(Mm.shape[1]), np.maximum(q, 1e-9), []
        for j in seed:
            if avail[j] and len(top) < k:
                top.append(int(j))
                avail[j] = False
                acc += Mm[j]
        for t in range(len(top), min(k, len(top) + int(avail.sum()))):
            pmix = (acc[None, :] + Mm) / (t + 1)
            pmix = (1 - alpha) * pmix + alpha * q
            obj = (1 - lam) * r - lam * (q * np.log(q / pmix)).sum(1)
            obj[~avail] = -np.inf
            j = int(np.argmax(obj))
            top.append(j)
            avail[j] = False
            acc += Mm[j]
        return top

    def recommend(self, cid, w=None, lam=None, k=10, domain=None, st=None):
        t0 = time.perf_counter()
        w = R.DEFAULT["w_need"] if w is None else float(w)
        lam = R.DEFAULT["lam"] if lam is None else float(lam)
        u = self.ix[cid]
        stt = self.statuses(cid, st)
        s_arr = np.array([stt[s] for s in self.items])
        need, q = self._need_vec(u, st)
        cand = ~self.xb[u]                                           # 모델 기준 후보(기록상 한 번도 안 한 프로그램)
        score, evr, nfr = self._scores(u, w, cand, need)
        fresh = cand & np.isin(s_arr, ["not_run", "no_record"])
        in_dom = np.ones(len(self.items), bool) if not domain else (self.prim_np == domain)
        fresh_d = fresh & in_dom
        seed = []                                                    # 확인된 필요 '높음' 분야: 점수순 상위 2개를 먼저 넣는다
        conf = (st or {}).get("confirmed", {})
        if not domain:
            for d in C.NEED_IDS:
                if (conf.get(d) or {}).get("level") == "high":
                    js = np.where(fresh_d & (self.prim_np == d))[0]
                    seed += list(js[np.argsort(-score[js])][:CONFIRMED_MIN])
        top = self._calib(score, fresh_d, self.Mm, q, k, 0.0 if domain else lam, seed=seed)
        top = sorted(top, key=lambda j: -score[j]) if seed else top     # 먼저 넣은 것도 점수순으로 다시 줄 세운다
        picked = [(j, "fresh") for j in top]
        short = None
        if len(picked) < k:                                          # 후보 부족: 제외한 것을 되살리지 않고 정해진 순서로만 채운다
            all_mask = np.ones(len(self.items), bool)
            s_all, _, _ = self._scores(u, w, all_mask, need)
            paused = np.where((s_arr == "paused") & in_dom)[0]
            ex = (st or {}).get("excluded", {})
            snooze = np.array([j for j in np.where((s_arr == "snoozed") & in_dom)[0] if ex.get(self.items[j], {}).get("count", 1) <= MAX_RESURFACE], dtype=int)
            for pool, tag in ((paused, "resume"), (snooze, "resurfaced")):
                for j in pool[np.argsort(-s_all[pool])] if len(pool) else []:
                    if len(picked) >= k:
                        break
                    picked.append((int(j), tag))
            short = dict(wanted=k, fresh=len(top), shown=len(picked), resume=sum(t == "resume" for _, t in picked), resurfaced=sum(t == "resurfaced" for _, t in picked),
                         held_back=int(((s_arr == "infeasible") | (s_arr == "declared") | (s_arr == "snoozed")).sum() - sum(t == "resurfaced" for _, t in picked)))
        recs = [self._rec(cid, u, j, rank, tag, score, evr, nfr, need, stt, st) for rank, (j, tag) in enumerate(picked, 1)]
        # 분야별 상위 3개(전체 프로그램 대상, 상태 표시)
        s_all, _, _ = self._scores(u, w, np.ones(len(self.items), bool), need)
        by_dom = []
        for d in C.NEED_IDS:
            js = np.where((self.prim_np == d) & ~np.isin(s_arr, ["infeasible"]))[0]
            js = js[np.argsort(-s_all[js])][:3]
            by_dom.append(dict(domain=d, label=C.NEED[d], need=float(need[C.NEED_IDS.index(d)]),
                               items=[dict(std_id=self.items[j], name=self.p.at[self.items[j], "name"], status=stt[self.items[j]], status_label=self.STATUS_KO[stt[self.items[j]]],
                                           score=float(s_all[j])) for j in js]))
        mix = (self.Mm[[j for j, _ in picked]].sum(0) / max(1, len(picked))) if picked else np.zeros(len(C.NEED_IDS))
        return clean(dict(complex_id=cid, w=w, lam=lam, k=k, domain=domain, items=recs, shortage=short, by_domain=by_dom,
                          target=dict(zip(C.NEED_IDS, q)), list_mix=dict(zip(C.NEED_IDS, mix)), n_candidates=int(fresh.sum()),
                          has_records=bool(self.has_rec[u]), confirmed_used=[d for d in C.NEED_IDS if ((st or {}).get("confirmed", {}).get(d) or {}).get("level") in LEVEL],
                          ms=round((time.perf_counter() - t0) * 1000, 2)))

    def _rec(self, cid, u, j, rank, tag, score, evr, nfr, need, stt, st):
        sid, q = self.items[j], self.req.iloc[j]
        d = self.prim_np[j] or None
        di = C.NEED_IDS.index(d) if d else None
        pf = self.prof
        npct = float(need[di]) if d else float(need.mean())
        conf = ((st or {}).get("confirmed", {}).get(d) or {}).get("level") if d else None
        unc = bool(d and (pf.at[cid, f"need_hi_{d}"] - pf.at[cid, f"need_lo_{d}"]) > UNCERTAIN_WIDTH)
        gap = bool(self.needs_ww[j] and not self.deployed[u])
        reasons = []
        if conf:
            reasons.append(dict(kind="need", text=f"확인된 필요: {C.NEED[d]} {LEVEL_KO[conf]}"))
        elif d and npct >= 0.6:
            reasons.append(dict(kind="need", text=f"{C.NEED[d]} 필요 상위 {max(1, round(100 * (1 - npct)))}%", uncertain=unc))
        reasons.append(dict(kind="peer", text=f"비슷한 단지 {self.peer_k}곳 중 {int(self.peer_n[u, j])}곳 운영"))
        reasons.append(dict(kind="pop", text=f"전체 단지의 {round(100 * self.pop[j])}% 운영"))
        return dict(rank=rank, std_id=sid, name=self.p.at[sid, "name"], family=self.p.at[sid, "family_label"], domain=d, domain_label=C.NEED.get(d, "여러 분야"),
                    tag=tag, status=stt[sid], status_label=self.STATUS_KO[stt[sid]],
                    hidden=dict(score=None if np.isnan(score[j]) else float(score[j]), evidence_pct=None if np.isnan(evr[j]) else float(evr[j]),
                                need_fit_pct=None if np.isnan(nfr[j]) else float(nfr[j]), feasibility=float(self.feas_np[u, j])),
                    need_pct=npct, need_uncertain=unc, need_confirmed=conf, peer_n=int(self.peer_n[u, j]), peer_k=self.peer_k, pop=float(self.pop[j]), reasons=reasons,
                    cost_year=float(q["cost_year"]), hours_year=float(q["staff_load"]), difficulty=int(q["staff_tier"]), months=str(q["peak_months"]).split("|"),
                    cost_session=q.get("x_cost_session"), hours_session=q.get("x_staff_hours"), welfare_gap=gap, needs_welfare_worker=bool(self.needs_ww[j]),
                    welfare_dependent_data=self.dep_data.get(sid, False), basis="expert" if self.expert else "draft",
                    last=self.last_ym.get((cid, sid)), excluded_count=((st or {}).get("excluded", {}).get(sid) or {}).get("count"))

    # ───────── 후보 상세 ─────────
    def rec_dict(self, cid, sid, st=None):
        """explain.py가 쓰는 추천 사전(점검표·사례 포함)."""
        u, j = self.ix[cid], self.jx[sid]
        need, _ = self._need_vec(u, st)
        d = self.prim_np[j] or None
        rec = dict(complex_id=cid, complex=self.c.at[cid, "name"], std_id=sid, name=self.p.at[sid, "name"], family=self.p.at[sid, "family_label"], domain=d,
                   need_pct=float(need[C.NEED_IDS.index(d)]) if d else float(need.mean()), peer_n=int(self.peer_n[u, j]), peer_k=self.peer_k, pop=float(self.pop[j]),
                   feasibility=float(self.feas_np[u, j]))
        rec["check"] = M4.checklist(sid, cid, self.req, self.cap, self.comp)
        rec["evidence"] = M2.evidence_bundle(cid, sid, self.S, self.IS, 3)          # 배치로 만든 근거 문장과 같은 사실을 쓰려고 3건
        return rec

    def candidate(self, cid, sid, st=None):
        rec = self.rec_dict(cid, sid, st)
        j = self.jx[sid]
        cb = D.casebook()
        cards = cb["cards"]
        case_ids = list(cards.loc[cards["std_id"] == sid, "case_id"].unique())
        rel = "같은 프로그램 사례"
        if not case_ids and rec["evidence"]["casebook"]:
            case_ids = list(cards.loc[cards["card_id"].isin([x["card_id"] for x in rec["evidence"]["casebook"]]), "case_id"].unique())
            rel = "비슷한 프로그램 사례"
        ob = cb["obstacles"]
        ob = ob[ob["case_id"].isin(case_ids)]
        obstacles = [dict(case_id=x["case_id"], category=x["obstacle_category"], obstacle=x["obstacle"], solution=None if pd.isna(x["solution"]) else x["solution"],
                          strategy=None if pd.isna(x["solution_strategy"]) else x["solution_strategy"], status=x["status"], relation=rel) for _, x in ob.iterrows()]
        key = f"{cid}|{sid}"
        cached = self.llm_cache.get(key)
        draft = X.template(rec)
        conf = bool((st or {}).get("confirmed"))
        llm = cached if cached and cached["source"] == "llm" and cached.get("draft") == draft and not conf else None
        stt = self.statuses(cid, st)
        q = self.req.iloc[j]
        out = dict(complex_id=cid, std_id=sid, name=rec["name"], family=rec["family"], domain=rec["domain"], domain_label=C.NEED.get(rec["domain"], "여러 분야"),
                   definition=str(self.p.at[sid, "definition"]).split(": ", 1)[-1], status=stt[sid], status_label=self.STATUS_KO[stt[sid]],
                   check=rec["check"], evidence=rec["evidence"], obstacles=obstacles, explanation=dict(template=draft, llm=llm["text"] if llm else None),
                   facts=X.facts(rec), draft_values=dict(cost_year=q.get("cost_year_draft"), staff_tier=q.get("staff_tier_draft")) if self.expert else None,
                   welfare_dependent_data=self.dep_data.get(sid, False), rule_checklist=self.rule_checklist(rec),
                   more_cases=M2.peer_cases(cid, sid, self.S, 8))
        return clean(out)

    def rule_checklist(self, rec):
        """규칙으로 만든 실행 점검표(LLM이 없거나 검사에서 떨어졌을 때의 기본값). 사실만 쓴다."""
        ck = rec["check"]
        prep, coop, run, log, warn = [], [], [], [], []
        places = ck.get("essential_places") or ck.get("place") or []
        if places:
            prep.append(f"장소 확보: {', '.join(places)} 가운데 쓸 수 있는 곳을 정한다.")
        months = ck["peak_months"].replace("|", "·")
        prep.append(f"시기 정하기: 다른 단지 기록에서는 {months}월에 많이 열렸다.")
        if ck.get("basis") == "expert":
            prep.append(f"인력 계획: 1회에 약 {ck['staff_hours_session']:g}명×시간이 든다(실행 난이도 5단계 중 {ck['difficulty']}).")
            cs = ck["cost_session"] // 10000
            prep.append(f"예산 확인: 1회 약 {cs:,}만 원, 부담 주체는 {'·'.join(ck['payers'])} 순으로 검토한다." if cs else "예산 확인: 1회 비용은 거의 들지 않는 것으로 검토되었다.")
        else:
            prep.append(f"예산 확인: 연간 약 {ck['cost_year_est'] // 10000:,}만 원(추정).")
        eps = ck.get("essential_partners")
        if ck.get("self_run"):
            coop.append("협력기관 없이 자체 운영할 수 있는 프로그램으로 검토되었다.")
        for e in eps or []:
            coop.append(f"{e['type']}에 협조를 요청한다(이 단지 여건: {e['status']}).")
        if not eps:
            for e in ck["partners"][:2]:
                coop.append(f"{e['type']}와 함께 한 기록이 많다(이 단지 여건: {e['status']}).")
        if ck["resources"]:
            coop.append(f"필요 자원: {', '.join(ck['resources'])}.")
        n_peer = len(rec["evidence"]["peer_records"])
        if n_peer:
            run.append(f"비슷한 단지 기록 {n_peer}건의 진행 방식을 참고해 회차와 대상을 정한다.")
        run.append(f"참여 규모: 다른 단지 기록의 중앙값은 {ck['participants_med']}명이다.")
        run.append("주민 안내: 게시판·방송·세대 안내 가운데 대상에 맞는 방법을 고른다.")
        log += ["실행 뒤 참여자 수, 대상, 실제 비용, 미참여 사유를 기록한다.", "다음 검토 때 유지·변경·중단을 정할 수 있게 주민 반응을 한 줄로 남긴다."]
        if ck.get("welfare_gap"):
            warn.append("주거복지사가 있어야 하는 프로그램으로 검토되었는데 이 단지는 미배치다. 맡을 사람을 먼저 정한다.")
        for o in ck["obstacles"][:3]:
            warn.append(f"예상 걸림돌 '{o['obstacle']}': 사례집에서는 '{o['strategy']}' 방식으로 푼 사례가 {o['n']}건 있다.")
        return [dict(section="준비", items=prep), dict(section="협력·자원", items=coop), dict(section="진행", items=run), dict(section="확인·기록", items=log), dict(section="주의", items=warn)]

    # ───────── 묶음 선택(정수계획) ─────────
    def plan(self, cid, w=None, lam=None, budget=1e6, hours=None, n_max=6, min_domains=None, st=None, pinned=None):
        t0 = time.perf_counter()
        w = R.DEFAULT["w_need"] if w is None else float(w)
        hours = M4.LOAD_HOURS if hours is None else float(hours)
        u = self.ix[cid]
        stt = self.statuses(cid, st)
        s_arr = np.array([stt[s] for s in self.items])
        need, q = self._need_vec(u, st)
        cand = ~self.xb[u]
        score, _, _ = self._scores(u, w, cand, need)
        fresh = cand & np.isin(s_arr, ["not_run", "no_record"])
        sc = pd.Series(score[fresh], index=np.array(self.items)[fresh])
        if min_domains is None:                                       # 기본: 필요 상위 두 분야에서 1개씩
            min_domains = {C.NEED_IDS[i]: 1 for i in np.argsort(-need)[:2]}
        min_domains = {d: int(m) for d, m in min_domains.items() if int(m) > 0}
        t1 = time.perf_counter()
        pl = M4.plan(sc, self.req, self.prim, budget=float(budget) or None, load=hours or None, n_max=int(n_max), min_per_domain=min_domains)
        relaxed = False
        if not pl["feasible"] and min_domains:                        # 분야 조건 때문에 안 풀리면 조건을 빼고 다시
            pl = M4.plan(sc, self.req, self.prim, budget=float(budget) or None, load=hours or None, n_max=int(n_max))
            relaxed = True
        solve_ms = (time.perf_counter() - t1) * 1000
        items = []
        for sid in sorted(pl["items"], key=lambda s: -sc[s]):
            j = self.jx[sid]
            qq = self.req.iloc[j]
            items.append(dict(std_id=sid, name=self.p.at[sid, "name"], domain=self.prim_np[j] or None, domain_label=C.NEED.get(self.prim_np[j], "여러 분야"),
                              cost_year=float(qq["cost_year"]), hours_year=float(qq["staff_load"]), difficulty=int(qq["staff_tier"]), months=str(qq["peak_months"]).split("|"),
                              welfare_gap=bool(self.needs_ww[j] and not self.deployed[u]), score=float(sc[sid])))
        cal = {m: [] for m in range(1, 13)}
        for it in items:
            cal[int(it["months"][0])].append(it["name"])
        return clean(dict(complex_id=cid, feasible=pl["feasible"], relaxed=relaxed, items=items, cost=pl["cost"], hours=pl["load"], n=len(items),
                          budget=float(budget), hours_limit=hours, n_max=int(n_max), min_domains=min_domains, calendar=cal, n_candidates=int(fresh.sum()),
                          unit="공단 쪽 부담분(전문가 검토값 기준 추정)" if self.expert else "기록 추정",
                          solve_ms=round(solve_ms, 2), ms=round((time.perf_counter() - t0) * 1000, 2)))


if __name__ == "__main__":
    e = Engine()
    print("loaded", e.load_sec, "s")
    r = e.recommend("KOH_1")
    print([x["name"] for x in r["items"]], r["ms"])
    print(e.plan("KOH_1")["solve_ms"])
