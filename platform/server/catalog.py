"""조회용 자료: 프로그램 사전, 검색, 사례집·뉴스, 해피콜, 분석용 단지 표. 계산은 하지 않고 전처리 자료를 읽어 보여 준다."""
import re

import pandas as pd

from engine import C, D, M1, M4, clean, TYPE_LABEL

VARS = [  # (열, 이름, 단위, 묶음) — 분석 탭의 변수 탐색기
    ("hh", "세대 수", "세대", "규모"), ("pop", "주민 수", "명", "규모"), ("pph", "세대당 인구", "명", "규모"), ("years", "입주 후 경과 연수", "년", "주택"),
    ("area_avg", "평균 전용면적", "㎡", "주택"), ("small_unit", "40㎡ 미만 세대 비율", "%", "주택"), ("elev100", "승강기(100세대당)", "대", "주택"), ("cctv100", "CCTV(100세대당)", "대", "주택"),
    ("age60", "60세 이상 비율", "%", "인구"), ("age70", "70세 이상 비율", "%", "인구"), ("age80", "80세 이상 비율", "%", "인구"), ("age_u20", "20세 미만 비율", "%", "인구"),
    ("age_work", "20~59세 비율", "%", "인구"), ("female", "여성 비율", "%", "인구"), ("n_space", "단지 안 공용 공간 종류", "종", "공간"),
    ("d_경로당", "경로당까지 거리", "km", "접근성"), ("d_노인복지관", "노인복지관까지 거리", "km", "접근성"), ("d_종합사회복지관", "종합사회복지관까지 거리", "km", "접근성"),
    ("d_보건기관", "보건기관까지 거리", "km", "접근성"), ("d_병원", "병원까지 거리", "km", "접근성"), ("d_응급의료시설", "응급의료시설까지 거리", "km", "접근성"),
    ("hd", "홈닥터 지원(100세대당 월)", "건", "서비스"), ("mou25", "업무협약(2025)", "건", "서비스"), ("gov25", "유관기관 협력(2025)", "건", "서비스"),
]
PCT = {"small_unit", "age60", "age70", "age80", "age_u20", "age_work", "female"}


class Catalog:
    def __init__(self, eng):
        self.e = eng
        cb, nw = D.casebook(), D.news()
        self.cards, self.obst, self.playbook, self.cases_tbl = cb["cards"], cb["obstacles"], cb["playbook"], cb["cases"]
        self.articles, self.art_prog = nw["articles"], nw["article_program"]
        self.cb_codes = D.codebook()
        al = C.DATA / "community_nlp_2026_v1" / "alias_dictionary.csv"
        self.alias = pd.read_csv(al) if al.exists() else pd.DataFrame(columns=["std_id", "canonical_title", "n_records", "variants"])
        self.n_cards = self.cards.groupby("std_id").size().to_dict()
        ap = self.art_prog[self.art_prog["confidence"] != "low"]
        self.n_news = ap.groupby("std_id")["news_id"].nunique().to_dict()
        self._programs = None

    # ───────── 프로그램 사전 ─────────
    def programs(self):
        if self._programs is None:
            e, rows = self.e, []
            for j, sid in enumerate(e.items):
                q = e.req.iloc[j]
                rows.append(dict(std_id=sid, name=e.p.at[sid, "name"], family=e.p.at[sid, "family_label"], domain=e.prim_np[j] or None, domain_label=C.NEED.get(e.prim_np[j], "여러 분야"),
                                 adoption=float(e.pop[j]), n_records=int(q["n_records"]), n_complexes=int(q["n_complexes"]), cost_session=q.get("x_cost_session"),
                                 hours_session=q.get("x_staff_hours"), difficulty=int(q["staff_tier"]), cost_year=float(q["cost_year"]), needs_welfare_worker=bool(e.needs_ww[j]),
                                 welfare_dependent_data=e.dep_data.get(sid, False), months=str(q["peak_months"]).split("|"), n_cards=self.n_cards.get(sid, 0), n_news=self.n_news.get(sid, 0),
                                 household_visit=float(q["household_visit"]), partner_rate=float(q["partner_rate"])))
            self._programs = clean(rows)
        return self._programs

    def program(self, sid):
        e = self.e
        if sid not in e.jx:
            raise KeyError(sid)
        j, q, p = e.jx[sid], e.req.iloc[e.jx[sid]], e.p.loc[sid]
        cb = self.cb_codes
        lab = lambda codes, key: [cb[key].get(x, x) for x in (codes or [])]
        ran = e.xb[:, j]
        by_type = [dict(type=t, label=TYPE_LABEL[t], rate=float(ran[(e.prof["type"].to_numpy() == t) & e.has_rec].mean())) for t in ("S1", "S2", "S3")]
        by_dep = [dict(label="주거복지사 배치", rate=float(ran[e.deployed & e.has_rec].mean())), dict(label="미배치", rate=float(ran[~e.deployed & e.has_rec].mean()))]
        r = e.records[e.records["std_id"] == sid]
        mon = r["ym"].str[5:].astype(int).value_counts(normalize=True).reindex(range(1, 13)).fillna(0)
        trend = r.groupby("ym").size().reindex(e.months).fillna(0).astype(int)
        top = e.Xc[sid].sort_values(ascending=False).head(10)
        ex = r.sort_values("ym", ascending=False).drop_duplicates("complex_id").head(6)
        og = cb["partner_org"]
        partners = sorted([(o, float(q[f"og_{o}"])) for o in M4.OG_IDS if q[f"og_{o}"] >= 0.05], key=lambda t: -t[1])[:6]
        sim = e.IS.loc[sid].drop(sid).nlargest(5)
        al = self.alias[self.alias["std_id"] == sid].sort_values("n_records", ascending=False).head(6)
        cards = self.cards[self.cards["std_id"] == sid]
        ap = self.art_prog[(self.art_prog["std_id"] == sid) & (self.art_prog["confidence"] != "low")]
        ar = self.articles[self.articles["news_id"].isin(ap["news_id"]) & (self.articles["is_representative"] == 1)]
        out = dict(
            std_id=sid, name=p["name"], family=p["family_label"], domain=e.prim_np[j] or None, domain_label=C.NEED.get(e.prim_np[j], "여러 분야"),
            definition=str(p["definition"]).split(": ", 1)[-1], purpose=cb["purpose"].get(p["purpose"], p["purpose"]), targets=lab(p["targets"], "target"),
            resources=lab(p["resources"], "resource"), membership={d: float(v) for d, v in zip(C.NEED_IDS, e.Mm[j])},
            adoption=float(e.pop[j]), n_records=int(q["n_records"]), n_complexes=int(q["n_complexes"]), by_type=by_type, by_deploy=by_dep,
            month_share=[float(x) for x in mon], trend=dict(months=e.months, n=[int(x) for x in trend]),
            requirement=dict(basis="expert" if e.expert else "draft", cost_session=q.get("x_cost_session"), hours_session=q.get("x_staff_hours"), difficulty=q.get("x_difficulty"),
                             payers=str(q.get("x_payers", "")).split("|") if e.expert else [], internal_share=q.get("x_internal_share"), cost_year=float(q["cost_year"]),
                             cost_year_total=q.get("cost_year_total"), hours_year=float(q["staff_load"]), recs_per_year=float(q["recs_per_complex_year"]),
                             essential_places=[M4.PLACE_KO[x] for x in str(q.get("x_places", "")).split("|") if x in M4.PLACE_KO],
                             essential_partners=[og[x] for x in str(q.get("x_partners", "")).split("|") if x in og], self_run=bool(q.get("x_self_run", 0)),
                             needs_welfare_worker=bool(e.needs_ww[j]), welfare_dependent_data=e.dep_data.get(sid, False),
                             draft=dict(cost_year=q.get("cost_year_draft"), staff_tier=q.get("staff_tier_draft"), cost_med=float(q["cost_med"]))),
            observed=dict(partners=[dict(type=og[o], share=s) for o, s in partners], partner_rate=float(q["partner_rate"]), household_visit=float(q["household_visit"]),
                          regular=float(q["regular"]), participants_med=float(q["participants_med"]),
                          places=[dict(label=M4.PLACE_KO[k], share=float(q[f"place_{k}"])) for k in M4.PLACES if q[f"place_{k}"] >= 0.05]),
            top_complexes=[dict(id=cid, name=e.c.at[cid, "name"], n=int(n)) for cid, n in top.items() if n > 0],
            examples=[dict(complex_id=x["complex_id"], complex=e.c.at[x["complex_id"], "name"], month=x["ym"], title=str(x["program_name_masked"])[:70],
                           content=None if pd.isna(x["activity_content_masked"]) else str(x["activity_content_masked"])[:140]) for _, x in ex.iterrows()],
            similar=[dict(std_id=s, name=e.p.at[s, "name"], similarity=float(v)) for s, v in sim.items()],
            aliases=[dict(title=x["canonical_title"], n=int(x["n_records"]), variants=str(x["variants"])[:160]) for _, x in al.iterrows()],
            cards=[self._card(x) for _, x in cards.iterrows()],
            news=[dict(news_id=x["news_id"], date=x["date"], title=x["title"], outlet=x["outlet"], url=x["url"]) for _, x in ar.sort_values("date", ascending=False).iterrows()])
        return clean(out)

    @staticmethod
    def _card(x):
        sp = lambda s: [t.strip() for t in str(s).split(" / ") if t.strip()] if isinstance(s, str) else []
        return dict(card_id=x["card_id"], case_id=x["case_id"], std_id=x["std_id"] if isinstance(x["std_id"], str) else None, std_name=x["std_name"] if isinstance(x["std_name"], str) else None,
                    program_name=x["program_name"], domain=x["domain"], region=x["region"], headline=x["headline"], need=sp(x["need"]), target=x["target"] if isinstance(x["target"], str) else None,
                    partners=sp(x["partners"]), operation=x["operation"] if isinstance(x["operation"], str) else None, how=sp(x["how_it_runs"]), outcomes=sp(x["outcomes"]),
                    obstacles=sp(x["obstacles_and_solutions"]), lessons=x["lessons"] if isinstance(x["lessons"], str) else None, source=x["source"],
                    complex_ids=str(x["complex_ids"]).split("|") if isinstance(x["complex_ids"], str) else [])

    # ───────── 검색 ─────────
    def search(self, q, k=8):
        q = (q or "").strip()[:80]
        if not q:
            return dict(q=q, programs=[], complexes=[], cards=[], news=[])
        e = self.e
        hits = e.search_ix.search(q, k)
        names = e.p["name"]
        direct = [s for s in e.items if q.replace(" ", "") in names[s].replace(" ", "")]
        order = direct + [s for s, _ in hits if s not in direct]
        progs = [dict(std_id=s, name=names[s], domain_label=C.NEED.get(e.prim_np[e.jx[s]], "여러 분야"), adoption=float(e.pop[e.jx[s]]), exact=s in direct) for s in order[:k]]
        cx = [dict(id=cid, name=e.c.at[cid, "name"], branch=e.c.at[cid, "branch"]) for cid in e.ids if q in e.c.at[cid, "name"] or q in str(e.c.at[cid, "addr"])][:10]
        cards = [dict(card_id=x["card_id"], headline=x["headline"], std_id=x["std_id"] if isinstance(x["std_id"], str) else None)
                 for _, x in self.cards.iterrows() if q in str(x["card_text"])][:6]
        news = [dict(news_id=x["news_id"], title=x["title"], date=x["date"], outlet=x["outlet"], url=x["url"]) for _, x in self.articles.iterrows() if q in str(x["title"])][:6]
        return clean(dict(q=q, programs=progs, complexes=cx, cards=cards, news=news))

    # ───────── 사례집·뉴스 ─────────
    def cases(self):
        ob = [dict(case_id=x["case_id"], category=x["obstacle_category"], obstacle=x["obstacle"], solution=x["solution"] if isinstance(x["solution"], str) else None,
                   strategy=x["solution_strategy"] if isinstance(x["solution_strategy"], str) else None, status=x["status"],
                   evidence=x["obstacle_evidence_masked"] if isinstance(x["obstacle_evidence_masked"], str) else None) for _, x in self.obst.iterrows()]
        pb = [dict(category=x["obstacle_category"], strategy=x["solution_strategy"], n=int(x["n"]), cases=str(x["cases"]).split("|"), examples=str(x["examples"]).split(" / "))
              for _, x in self.playbook.sort_values("n", ascending=False).iterrows()]
        cs = [dict(case_id=x["case_id"], title=x["program_title"], domain=x["domain"], region=x["region"], summary=x["summary"] if isinstance(x["summary"], str) else None,
                   n_obstacles=int(x["n_obstacles"])) for _, x in self.cases_tbl.iterrows()]
        ar = self.articles.sort_values("date", ascending=False)
        news = [dict(news_id=x["news_id"], date=x["date"], title=x["title"], outlet=x["outlet"], url=x["url"], std_id=x["primary_std_id"] if isinstance(x["primary_std_id"], str) else None,
                     std_name=x["primary_std_name"] if isinstance(x["primary_std_name"], str) else None, representative=int(x["is_representative"]),
                     partnership=int(x["is_partnership"]) if not pd.isna(x["is_partnership"]) else 0) for _, x in ar.iterrows()]
        return clean(dict(cards=[self._card(x) for _, x in self.cards.iterrows()], obstacles=ob, playbook=pb, cases=cs, news=news,
                          source="주거복지사 활동 사례집 「어느 날 삶에 온기가 돌기 시작했다」(주택관리공단, 2025.7.11.)"))

    # ───────── 해피콜 ─────────
    def happycall(self):
        e = self.e
        ms = e.hc_scores
        link = {}
        for cid, hs in e.hc_by_complex.items():
            for h in hs:
                link.setdefault(h["office"], []).append(cid)
        f = lambda v: None if pd.isna(v) else float(v)
        offices = [dict(office=x["source_name"], branch=x["branch"], n=int(x["n_total"]), small=bool(x["small_sample"]), overall=f(x["overall_satisfaction"]), welfare=f(x["welfare_satisfaction"]),
                        housing=f(x["housing_management_satisfaction"]), rental=f(x["rental_operation_satisfaction"]), major=f(x["major_service_satisfaction"]),
                        complex_ids=link.get(x["source_name"], [])) for _, x in ms.iterrows()]
        hd = D.happycall_demand()
        pops = {"residential_life_support_service_users": "주거생활지원 서비스 이용자", "social_isolation_service_users": "사회적 고립 지원 서비스 이용자"}
        demand = []
        for pk, pl in pops.items():
            h = hd[hd["population"] == pk]
            ov = h[h["scope"] == "overall"].drop_duplicates("metric")
            groups = {}
            for (g, sg), d in h[h["scope"] != "overall"].groupby(["group", "subgroup"]):
                groups.setdefault(g, []).append(dict(subgroup=sg, n=int(d["n"].max()), values={m: float(v) for m, v in zip(d["metric"], d["value"])}))
            demand.append(dict(key=pk, label=pl, n=int(ov["n"].max()), overall=[dict(metric=m, value=float(v)) for m, v in zip(ov["metric"], ov["value"])], groups=groups))
        v = pd.read_csv(C.DATA / "happycall_2025_v1" / "voc.csv")
        voc = [dict(category=re.sub(r"\(\d+\)$", "", str(x["category_raw"])).strip(), cat_n=(lambda m: int(m.group(1)) if m else None)(re.search(r"\((\d+)\)$", str(x["category_raw"]))),
                    text=re.sub(r"\s*\(\d+\)$", "", str(x["text"])), freq=None if pd.isna(x["frequency_explicit"]) else int(x["frequency_explicit"]),
                    tags=x["need_tags_suggested"] if isinstance(x["need_tags_suggested"], str) else "[]") for _, x in v.iterrows()]
        tb = lambda n: pd.read_csv(C.TABLES / f"{n}.csv").to_dict("records") if (C.TABLES / f"{n}.csv").exists() else []
        nat = M1.demand_base("national")
        summary = dict(n_offices=len(ms), n_small=int(ms["small_sample"].sum()), n_welfare=int(ms["welfare_satisfaction"].notna().sum()),
                       mean_overall=f(ms["overall_satisfaction"].mean()), mean_welfare=f(ms["welfare_satisfaction"].mean()), mean_housing=f(ms["housing_management_satisfaction"].mean()))
        return clean(dict(summary=summary, offices=offices, demand=demand, voc=voc, distribution=tb("e6_demand_distribution"), alignment=tb("e6_demand_alignment"),
                          outcome=tb("e6_happycall_outcome"), national_domain={d: float(nat[d]) for d in C.NEED_IDS}))

    # ───────── 분석 ─────────
    def analytics(self):
        e = self.e
        c, pf = e.c, e.prof
        cols = [dict(key=k, label=l, unit=u, group=g) for k, l, u, g in VARS]
        cols += [dict(key=f"need_{d}", label=f"필요: {C.NEED[d]}", unit="백분위", group="필요 지수") for d in C.NEED_IDS]
        cols += [dict(key=f"supply_pct_{d}", label=f"공급: {C.NEED[d]}", unit="백분위", group="공급") for d in C.NEED_IDS]
        cols += [dict(key="n_records", label="활동 기록 수(30개월)", unit="건", group="운영"), dict(key="richness", label="프로그램 종류 수", unit="종", group="운영"),
                 dict(key="active_month_ratio", label="기록 있는 달 비율", unit="%", group="운영"), dict(key="repeat_share", label="반복 프로그램 비중", unit="%", group="운영"),
                 dict(key="hc_overall", label="해피콜 종합 만족도", unit="점", group="해피콜"), dict(key="hc_welfare", label="해피콜 복지 만족도", unit="점", group="해피콜")]
        rows = []
        for u, cid in enumerate(e.ids):
            hc = e.happycall_for(cid)
            r = dict(id=cid, name=c.at[cid, "name"], branch=c.at[cid, "branch"], type=pf.at[cid, "type"], deployed=int(c.at[cid, "deployed"]), supply=c.at[cid, "supply"], region=c.at[cid, "region"])
            for k, _, _, _ in VARS:
                v = c.at[cid, k]
                r[k] = None if pd.isna(v) else float(v) * (100 if k in PCT else 1)
            for d in C.NEED_IDS:
                r[f"need_{d}"] = float(e.need.at[cid, d])
                r[f"supply_pct_{d}"] = pf.at[cid, f"supply_pct_{d}"]
            has = e.has_rec[u]
            r["n_records"], r["richness"] = (pf.at[cid, "n_records"], pf.at[cid, "richness"]) if has else (None, None)
            r["active_month_ratio"] = pf.at[cid, "active_month_ratio"] * 100 if has else None
            r["repeat_share"] = pf.at[cid, "repeat_share"] * 100 if has else None
            ok = hc.get("status") == "ok"
            r["hc_overall"], r["hc_welfare"] = (hc.get("overall"), hc.get("welfare")) if ok else (None, None)
            rows.append(r)
        nat_supply = e.xc[e.has_rec].sum(0) @ e.Mm
        return clean(dict(columns=cols, rows=rows, type_labels=TYPE_LABEL, national_supply={d: float(v) for d, v in zip(C.NEED_IDS, nat_supply / nat_supply.sum())},
                          national_demand={d: float(v) for d, v in M1.demand_base("national").items()},
                          counts=dict(complexes=len(e.ids), with_records=int(e.has_rec.sum()), programs=len(e.items), records=int(len(e.records)), deployed=int(e.deployed.sum()),
                                      months=f"{C.FIRST_MONTH}~{C.LAST_MONTH}")))

