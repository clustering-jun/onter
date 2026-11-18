"""전문가 정답 요청 엑셀을 만든다(expert_request/온터_전문가_검토요청.xlsx).

설계: 여러 알고리즘의 상위 후보를 합쳐(pooling) 무작위 순서로 내고, 어느 알고리즘이 낸 후보인지는 엑셀에 싣지 않는다
(expert_request/pool_key.csv에만 남긴다). 한 알고리즘에 유리한 정답이 되지 않게 하기 위해서다.
"""
import sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from onter import config as C, data as D, features as F, m1_profile as M1, m2_cases as M2, m3_rank as R, m4_feasibility as M4, evalx as E

sys.stdout.reconfigure(encoding="utf-8")
OUT = C.ROOT / "expert_request"
N_COMPLEX, PER_ALGO, N_RANDOM = 24, 5, 2
HEAD, ASK = PatternFill("solid", fgColor="DDE6F3"), PatternFill("solid", fgColor="FFF4D6")
thin = Side(style="thin", color="C9CED8")


def sheet(wb, title, df, ask_cols, widths, note=None):
    ws = wb.create_sheet(title)
    r0 = 1
    if note:
        ws.cell(1, 1, note).font = Font(bold=True, color="1F5FAE")
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(df.columns))
        r0 = 2
    for j, col in enumerate(df.columns, 1):
        cell = ws.cell(r0, j, col)
        cell.font, cell.fill = Font(bold=True), (ASK if col in ask_cols else HEAD)
        cell.alignment, cell.border = Alignment(wrap_text=True, vertical="center", horizontal="center"), Border(top=thin, bottom=thin, left=thin, right=thin)
        ws.column_dimensions[get_column_letter(j)].width = widths.get(col, 14)
    for i, row in enumerate(df.itertuples(index=False), r0 + 1):
        for j, v in enumerate(row, 1):
            cell = ws.cell(i, j, None if (isinstance(v, float) and np.isnan(v)) else v)
            cell.alignment, cell.border = Alignment(wrap_text=True, vertical="top"), Border(top=thin, bottom=thin, left=thin, right=thin)
            if df.columns[j - 1] in ask_cols:
                cell.fill = ASK
    ws.freeze_panes = ws.cell(r0 + 1, 3)
    ws.row_dimensions[r0].height = 42
    return ws, r0


def validate(ws, r0, df, col, formula):
    dv = DataValidation(type="list", formula1=formula, allow_blank=True)
    ws.add_data_validation(dv)
    L = get_column_letter(list(df.columns).index(col) + 1)
    dv.add(f"{L}{r0 + 1}:{L}{r0 + len(df)}")


def main():
    if (OUT / "온터_전문가_검토요청(완료).xlsx").exists() and "--force" not in sys.argv:
        sys.exit("응답 파일이 이미 있습니다. 다시 만들면 평가ID가 달라질 수 있어 멈춥니다(--force로 강제).")
    OUT.mkdir(exist_ok=True)
    rng = np.random.default_rng(C.SEED)
    c, p = D.complexes(), D.programs()
    Xb = F.interactions(C.FIRST_MONTH, C.LAST_MONTH)
    M, T = F.need_membership(), F.target_membership()
    need, Q = M1.need_table("S"), M1.target_distribution()
    S_h = M2.sim_matrix("hybrid")
    cand = (Xb == 0).to_numpy()
    ev = R.fuse({"p": R.userknn(Xb, S_h), "e": R.ease(Xb), "o": R.pop(Xb)}, cand=cand)
    nf = R.need_fit(Xb, M, T=T)
    algos = {"pop": E.topk(R.pop(Xb).to_numpy(), cand, PER_ALGO), "evidence": E.topk(ev.to_numpy(), cand, PER_ALGO), "need_fit": E.topk(nf.to_numpy(), cand, PER_ALGO),
             "onter": R.calibrated_topk(R.onter_scores(Xb, S_h, M, T, cand=cand), cand, M, Q, PER_ALGO, R.DEFAULT["lam"])}
    # 단지 표본: 구조 유형 × 주거복지사 배치로 층화(기록 있는 단지)
    lab = M1.typology(k=3)[0]
    pool = c[c.index.isin(F.active_complexes(C.FIRST_MONTH, C.LAST_MONTH, 20))].assign(type=lab)
    picks = []
    for (t, dpl), g in pool.groupby(["type", "deployed"]):
        n = max(2, round(N_COMPLEX * len(g) / len(pool)))
        picks += list(rng.choice(g.index, min(n, len(g)), replace=False))
    picks = picks[:N_COMPLEX] if len(picks) >= N_COMPLEX else picks
    hist = M1.history()
    items = list(Xb.columns)
    rows, key = [], []
    for cid in picks:
        u = c.index.get_loc(cid)
        src = {}
        for a, top in algos.items():
            for j in top[u]:
                src.setdefault(items[j], []).append(a)
        free = [i for i in np.where(cand[u])[0] if items[i] not in src]
        for j in rng.choice(free, N_RANDOM, replace=False):
            src.setdefault(items[j], []).append("random")
        desc = (f"{c.at[cid, 'supply']} · {int(c.at[cid, 'hh']):,}세대 · {c.at[cid, 'region']} · 60세 이상 {c.at[cid, 'age60']:.0%}, 80세 이상 {c.at[cid, 'age80']:.0%}, "
                f"20세 미만 {c.at[cid, 'age_u20']:.0%} · 입주 {c.at[cid, 'years']:.0f}년 · 주거복지사 {'배치' if c.at[cid, 'deployed'] else '미배치'}")
        for sid in rng.permutation(list(src)):
            eid = f"E{len(rows) + 1:04d}"
            rows.append({"평가ID": eid, "단지": c.at[cid, "name"], "지사": c.at[cid, "branch"], "단지 요약": desc, "최근 많이 한 프로그램": hist.at[cid, "top_programs"],
                         "검토 후보 프로그램": p.at[sid, "name"], "프로그램 설명": str(p.at[sid, "definition"]).split(": ", 1)[-1][:120],
                         "① 이 단지에 필요한가 (0~3)": None, "② 이 단지에서 실행할 수 있는가 (0~3)": None, "③ 올해 우선 추천하겠는가 (Y/N)": None, "의견(선택)": None})
            key.append(dict(eval_id=eid, complex_id=cid, std_id=sid, sources="|".join(src[sid])))
    A = pd.DataFrame(rows)
    pd.DataFrame(key).to_csv(OUT / "pool_key.csv", index=False, encoding="utf-8-sig")
    # B 실행 요건: 데이터에서 뽑은 초안을 보여 주고 고쳐 달라고 한다
    req = M4.requirements()
    og, tier = D.codebook()["partner_org"], {1: "10만 원 미만", 2: "10~50만 원", 3: "50~200만 원", 4: "200~1,000만 원", 5: "1,000만 원 이상"}
    B = pd.DataFrame({"프로그램ID": req.index, "프로그램": req["name"], "분야": [C.NEED.get(x, "여러 분야") for x in p["need_primary"]],
                      "[초안] 연간 비용 등급": req["cost_tier"].map(tier), "[초안] 인력 부담(1~5)": req["staff_tier"],
                      "[초안] 주 장소": [" / ".join(M4.PLACE_KO[k] for k in M4.PLACES if q[f"place_{k}"] >= 0.25) for _, q in req.iterrows()],
                      "[초안] 주 협력기관": [" / ".join(og[o] for o in sorted(M4.OG_IDS, key=lambda o: -q[f"og_{o}"])[:2] if q[f"og_{o}"] >= 0.08) for _, q in req.iterrows()],
                      "1회 실제 비용(만 원)": None, "비용 부담 주체(단지/공단/LH/외부)": None, "필요 인력(명×시간)": None, "꼭 필요한 공간": None, "꼭 필요한 협력기관": None,
                      "주거복지사 없이 가능한가 (Y/N)": None, "실행 난이도(1 쉬움~5 어려움)": None, "초안이 틀린 곳(선택)": None})
    # C 지표 → 필요 분야
    Crows = [{"필요 분야": C.NEED[d], "지표": lab_, "방향": "높을수록 필요" if sign > 0 else "낮을수록 필요", "구분": "구조 지표(기본)" if v == "S" else "이용 실적(참고)",
              "현재 가중치": w, "적절한가 (0 무관 ~ 3 매우 관련)": None, "의견(선택)": None}
             for d in C.NEED_IDS for v in ("S", "E") for col, sign, w, lab_ in M1.INDICATORS[d][v]]
    Cdf = pd.DataFrame(Crows)
    # D 단지별 필요 분야 배분
    Ddf = pd.DataFrame([{"단지": c.at[cid, "name"], "단지 요약": A.loc[A["단지"] == c.at[cid, "name"], "단지 요약"].iloc[0], **{f"{C.NEED[d]} (점)": None for d in C.NEED_IDS},
                         "합계(100)": None, "가장 시급한 문제(한 줄)": None} for cid in picks])
    wb = Workbook()
    ws = wb.active
    ws.title = "안내"
    guide = ["온터 프로그램 추천 알고리즘 검토 요청", "", "목적: 단지별 프로그램 추천 알고리즘이 현장 판단과 맞는지 확인하고, 데이터로 알 수 없는 실행 요건을 보완합니다.",
             "노란 칸만 채워 주시면 됩니다. 모르는 칸은 비워 두셔도 됩니다. 예상 소요 시간: A 60~80분, B 40분, C 10분, D 15분.", "",
             f"A_단지프로그램평가: 단지 {len(picks)}곳 × 후보 프로그램 약 {len(A) // len(picks)}개. 후보는 여러 방식으로 뽑아 섞었고 순서는 무작위입니다(좋은 후보와 그렇지 않은 후보가 섞여 있습니다).",
             "   ① 필요: 0 필요 없음 / 1 낮음 / 2 필요함 / 3 매우 필요.  ② 실행: 0 불가 / 1 어려움 / 2 가능 / 3 쉽게 가능.  ③ 올해 우선 추천: Y 또는 N.",
             "B_프로그램실행요건: 활동 기록에서 추정한 초안(비용 등급·인력 부담·장소·협력기관)을 보시고 실제 값을 적어 주십시오. 비용 초안은 집행액이 아니라 가정에 따른 추정입니다.",
             "C_필요지표: 필요 분야를 재는 데 쓴 지표가 적절한지 0~3으로 표시해 주십시오. 빠진 지표가 있으면 의견란에 적어 주십시오.",
             "D_단지필요분야: 같은 단지에 대해 여섯 분야에 100점을 나눠 주십시오(많이 필요한 분야에 높은 점수).", "",
             "가능하면 A와 D는 두 분 이상이 따로 작성해 주십시오(평가자 간 일치도를 보기 위함). 평가자 구분: 파일 이름 끝에 이름 머리글자를 붙여 주십시오.",
             "자료: 주택관리공단 단지 통합표·커뮤니티 활동 기록(2024-01~2026-06). 단지 요약의 수치는 통합표 기준입니다."]
    for i, t in enumerate(guide, 1):
        ws.cell(i, 1, t).font = Font(bold=(i == 1), size=14 if i == 1 else 11)
    ws.column_dimensions["A"].width = 150
    wA, r0 = sheet(wb, "A_단지프로그램평가", A, {"① 이 단지에 필요한가 (0~3)", "② 이 단지에서 실행할 수 있는가 (0~3)", "③ 올해 우선 추천하겠는가 (Y/N)", "의견(선택)"},
                   {"단지": 13, "단지 요약": 46, "최근 많이 한 프로그램": 40, "검토 후보 프로그램": 30, "프로그램 설명": 46, "의견(선택)": 24})
    validate(wA, r0, A, "① 이 단지에 필요한가 (0~3)", '"0,1,2,3"')
    validate(wA, r0, A, "② 이 단지에서 실행할 수 있는가 (0~3)", '"0,1,2,3"')
    validate(wA, r0, A, "③ 올해 우선 추천하겠는가 (Y/N)", '"Y,N"')
    askB = set(B.columns[7:])
    wB, r0 = sheet(wb, "B_프로그램실행요건", B, askB, {"프로그램": 34, "[초안] 주 장소": 26, "[초안] 주 협력기관": 30, "초안이 틀린 곳(선택)": 24, "꼭 필요한 공간": 18, "꼭 필요한 협력기관": 20})
    validate(wB, r0, B, "주거복지사 없이 가능한가 (Y/N)", '"Y,N"')
    validate(wB, r0, B, "실행 난이도(1 쉬움~5 어려움)", '"1,2,3,4,5"')
    wC, r0 = sheet(wb, "C_필요지표", Cdf, {"적절한가 (0 무관 ~ 3 매우 관련)", "의견(선택)"}, {"필요 분야": 20, "지표": 40, "의견(선택)": 40})
    validate(wC, r0, Cdf, "적절한가 (0 무관 ~ 3 매우 관련)", '"0,1,2,3"')
    sheet(wb, "D_단지필요분야", Ddf, set(Ddf.columns[2:]), {"단지": 13, "단지 요약": 50, "가장 시급한 문제(한 줄)": 36})
    wb.save(OUT / "온터_전문가_검토요청.xlsx")
    print("rows A", len(A), "complexes", len(picks), "B", len(B), "C", len(Cdf), "sources:", pd.DataFrame(key)["sources"].str.split("|").explode().value_counts().to_dict())


if __name__ == "__main__":
    main()
