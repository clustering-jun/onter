"""근거 문장. 기본은 템플릿(숫자를 근거 사전에서 그대로 옮김)이고, LLM은 선택 사항으로 문장을 다듬는 데만 쓴다.

LLM을 붙일 때의 규칙(06_llm_plan.md)
- 입력은 이 모듈이 만든 근거 사전뿐이다. 원자료·주민 정보는 보내지 않는다.
- 출력은 check_grounded를 통과해야 한다: 근거 사전에 없는 숫자, 효과를 단정하는 표현이 있으면 버리고 템플릿 문장을 쓴다.
"""
import re
from . import config as C

BANNED = ["예방할 수 있", "막을 수 있", "효과가 입증", "반드시", "해결됩니다", "고독사를 줄", "정확도"]


def facts(rec):
    """추천 1건의 근거 사전에서 문장에 쓸 사실만 뽑는다."""
    return dict(program=rec["name"], domain=C.NEED.get(rec.get("domain"), "여러 분야"), need_pct=round(100 * rec["need_pct"]),
                peer_n=rec["peer_n"], peer_k=rec["peer_k"], adopt_pct=round(100 * rec["pop"]), months=rec["check"]["peak_months"].replace("|", "·"),
                partners=[p["type"] for p in rec["check"]["partners"][:2]], cost=rec["check"]["cost_year_est"], staff=rec["check"]["staff_tier"],
                n_cases=len(rec["evidence"]["peer_records"]), n_cards=len(rec["evidence"]["casebook"]),
                expert=rec["check"].get("basis") == "expert", welfare_gap=bool(rec["check"].get("welfare_gap", False)))


def template(rec):
    f = facts(rec)
    s = [f"{f['program']}: 이 단지는 '{f['domain']}' 분야의 필요 지표가 전체 단지 중 상위 {max(1, 100 - f['need_pct'])}%에 있습니다."
         if f["need_pct"] >= 60 else f"{f['program']}: '{f['domain']}' 분야 프로그램입니다."]
    s.append(f"비슷한 단지 {f['peer_k']}곳 가운데 {f['peer_n']}곳이 운영했고, 전체 단지의 {f['adopt_pct']}%가 운영한 적이 있습니다.")
    if f["partners"]:
        s.append(f"주로 {', '.join(f['partners'])}와(과) 함께 합니다.")
    if f["expert"]:
        cost = f"공단 쪽 연간 비용은 약 {f['cost'] // 10000:,}만 원(전문가 검토값으로 계산한 추정)" if f["cost"] >= 10000 else "공단 쪽 비용 부담은 거의 없고(전문가 검토값 기준)"
        s.append(f"기록상 {f['months']}월에 많이 열렸고, {cost}, 실행 난이도는 5단계 중 {f['staff']}입니다.")
    else:
        s.append(f"기록상 {f['months']}월에 많이 열렸고, 연간 비용은 약 {f['cost'] // 10000:,}만 원(유형별 가정에 따른 추정), 인력 부담은 5단계 중 {f['staff']}입니다.")
    if f["welfare_gap"]:
        s.append("주거복지사가 있어야 하는 프로그램으로 검토되었는데 이 단지는 미배치여서, 맡을 사람을 먼저 정해야 합니다.")
    if f["n_cases"] or f["n_cards"]:
        s.append(f"참고할 사례: 비슷한 단지 기록 {f['n_cases']}건" + (f", 사례집 카드 {f['n_cards']}장" if f["n_cards"] else "") + ".")
    return " ".join(s)


def check_grounded(text, rec):
    """문장 검사: (1) 금지 표현 없음 (2) 문장 속 숫자가 모두 근거 사전에 있음."""
    f = facts(rec)
    allowed = {str(v) for v in [f["need_pct"], 100 - f["need_pct"], f["peer_n"], f["peer_k"], f["adopt_pct"], f["cost"] // 10000, f["staff"], f["n_cases"], f["n_cards"], 5]}
    allowed |= set(re.findall(r"\d+", f["months"])) | set(re.findall(r"\d+", f["program"]))
    nums = {n.replace(",", "") for n in re.findall(r"\d[\d,]*", text)}
    bad = [b for b in BANNED if b in text]
    return dict(ok=not bad and nums <= allowed, unknown_numbers=sorted(nums - allowed), banned=bad)


def check_form(text):
    """형식 검사: 비어 있지 않고, 너무 길지 않고, 한자·가나·목록 기호가 없다."""
    why = []
    if len(text) < 30:
        why.append("too_short")
    if len(text) > 420:
        why.append("too_long")
    if re.search("[一-鿿぀-ヿ]", text):
        why.append("foreign_script")
    return why


INVENTED = ["참여율", "규모", "중간 수준", "높은 수준", "낮은 수준", "최고", "최저", "운영 중", "진행 중", "시행 중", "상대적으로", "비교적", "충족", "통찰", "효과", "성공", "인기", "월부터", "월까지", "분기", "절반", "대부분", "과반"]


def check_binding(text, rec):
    """숫자가 제 뜻에 붙어 있는지 검사한다. 숫자만 맞고 뜻이 바뀐 문장(예: 전체 단지 비율을 비슷한 단지 비율로 씀)을 거른다.

    - N%: '상위 N%'(필요 지표)이거나, 바로 앞 구절에 '전체'가 있고 그 뒤에 '비슷한·유사'가 없는 운영 비율이어야 한다.
    - N곳은 비슷한 단지 수·운영한 곳 수, N건은 사례 기록 수, N장은 사례집 카드 수, N만 원은 비용, N단계는 인력 부담, N월은 기록상 많이 열린 달이어야 한다.
    - 사실에 없는 해석(참여율, 규모, 중간 수준 등)이 없어야 하고, '후보'라는 말이 있어야 하며, 5문장 이내여야 한다.
    """
    f, why = facts(rec), []
    top = max(1, 100 - f["need_pct"])
    for m in re.finditer(r"(\d+)\s*%", text):
        n, pre = int(m.group(1)), text[max(0, m.start() - 28):m.start()]
        if "상위" in pre[-8:]:
            if not (f["need_pct"] >= 60 and n == top):
                why.append(f"pct_top:{n}")
        elif n != f["adopt_pct"] or "전체" not in pre or re.search(r"비슷한|유사", pre[pre.rindex("전체"):]):
            why.append(f"pct_adopt:{n}")
    units = [("곳", {f["peer_k"], f["peer_n"]}), ("건", {f["n_cases"]}), ("장", {f["n_cards"]}), ("단계", {5, f["staff"]}),
             ("월", {int(x) for x in re.findall(r"\d+", f["months"])})]
    for u, ok in units:
        for n in re.findall(r"(\d+)\s*" + u, text):
            if int(n) not in ok:
                why.append(f"{u}:{n}")
    for n in re.findall(r"(\d[\d,]*)\s*만\s*원", text):
        if int(n.replace(",", "")) != f["cost"] // 10000:
            why.append(f"만원:{n}")
    ok_words = set()
    if f["expert"]:                                           # 전문가 난이도는 척도가 정해져 있어 그 척도와 맞는 말은 해석이 아니다
        ok_words = {1: {"낮은 수준", "최저"}, 2: {"낮은 수준"}, 3: {"중간 수준"}, 4: {"높은 수준"}, 5: {"높은 수준", "최고"}}.get(f["staff"], set())
    why += [f"invented:{w}" for w in INVENTED if w in text and w not in f["program"] and w not in ok_words]
    if f["need_pct"] < 60 and "필요" in text and "필요" not in f["program"]:   # 필요 지표 사실을 주지 않았는데 필요를 말함
        why.append("invented:필요")
    if "후보" not in text:
        why.append("no_candidate")
    if len(re.findall(r"[.!?](?:\s|$)", text)) > 5 + int(f["welfare_gap"]):
        why.append("too_many_sentences")
    return why


EASE_WORD = {1: "쉬움", 2: "쉬운 편", 3: "보통", 4: "어려운 편", 5: "어려움"}     # 전문가 난이도 척도의 말(모델이 제멋대로 '중간 수준'이라고 쓰지 않게 사실로 준다)


def facts_text(rec):
    """LLM에 보낼 사실 목록. 단위를 붙인 한국어 줄로 써서 숫자를 다시 계산할 일이 없게 한다."""
    f = facts(rec)
    rows = [f"프로그램: {f['program']}", "분야: 여러 분야에 걸친 프로그램" if f["domain"] == "여러 분야" else f"분야: {f['domain']}"]
    if f["need_pct"] >= 60:
        rows.append(f"이 단지의 해당 분야 필요 지표: 전체 단지 중 상위 {max(1, 100 - f['need_pct'])}%")
    rows += [f"비슷한 단지 {f['peer_k']}곳 가운데 운영한 곳: {f['peer_n']}곳", f"전체 단지 중 운영한 적이 있는 비율: {f['adopt_pct']}%"]
    if f["partners"]:
        rows.append(f"주로 함께 하는 기관: {', '.join(f['partners'])}")
    rows += [f"기록상 많이 열린 달: {f['months']}월", (f"공단 쪽 연간 비용: 약 {f['cost'] // 10000:,}만 원(추정)" if f["cost"] >= 10000 else "공단 쪽 연간 비용: 거의 없음") if f["expert"] else f"연간 비용: 약 {f['cost'] // 10000:,}만 원(추정)",
             f"실행 난이도: 5단계 중 {f['staff']}({EASE_WORD.get(f['staff'], '보통')})" if f["expert"] else f"인력 부담: 5단계 중 {f['staff']}"]
    if f["welfare_gap"]:
        rows.append("주의: 주거복지사가 있어야 하는 프로그램인데 이 단지는 미배치")
    if f["n_cases"] or f["n_cards"]:
        rows.append(f"참고할 사례: 비슷한 단지 기록 {f['n_cases']}건" + (f", 사례집 카드 {f['n_cards']}장" if f["n_cards"] else ""))
    return "\n".join("- " + r for r in rows)


def clean(out):
    """모델 출력 정리: 머리말·따옴표·마크다운·줄바꿈 제거."""
    t = re.sub(r"[*#`]+", "", out or "")
    t = re.sub(r"^\s*(다듬은 문장|수정본|수정된 문장|답변|문장)\s*[::]\s*", "", t.strip())
    t = re.sub(r"\s+", " ", t).strip().strip("\"“”'")
    return t


SYSTEM = """당신은 공공임대 단지 관리소 직원에게 프로그램 검토 후보를 설명하는 문장을 다듬습니다.
규칙:
1. '사실'에 있는 내용과 숫자만 씁니다. 사실에 없는 숫자·기관·사례를 만들지 않습니다.
2. 숫자는 사실에 적힌 뜻 그대로 옮깁니다. 두 숫자를 합치거나 비율을 다시 계산하지 않습니다. '비슷한 단지 중 운영한 곳 수'와 '전체 단지 중 운영 비율(%)'은 서로 다른 사실이므로 따로 씁니다. 달은 적힌 달만 나열하고 기간으로 바꾸지 않습니다.
3. 숫자를 평가하거나 해석하지 않습니다. 난이도는 사실에 적힌 괄호 안의 말(쉬움·쉬운 편·보통·어려운 편·어려움)만 씁니다('중간 수준', '높은 참여율', '최고 수준', '비슷한 규모' 같은 말을 붙이지 않습니다). 과거 기록이므로 '운영 중'이 아니라 '운영했다'로 씁니다. 사실에 '필요 지표' 줄이 없으면 예시 2처럼 분야만 밝힙니다. 효과를 단정하지 않습니다.
4. 첫 문장을 프로그램 이름으로 시작하고, 이 프로그램이 '검토 후보'임을 한 번 밝힙니다.
5. 존댓말 5문장 이내(주의 사항이 있으면 6문장), 한 문단으로 씁니다. '통찰', '참고하시면 도움이 될 것' 같은 군말을 붙이지 않습니다. 머리말·목록·따옴표 없이 문장만 출력합니다.

예시 1
사실:
- 프로그램: 명절 나눔 행사
- 분야: 안부와 관계
- 이 단지의 해당 분야 필요 지표: 전체 단지 중 상위 12%
- 비슷한 단지 20곳 가운데 운영한 곳: 11곳
- 전체 단지 중 운영한 적이 있는 비율: 58%
- 주로 함께 하는 기관: 사회복지관·복지센터
- 기록상 많이 열린 달: 9·1·2월
- 공단 쪽 연간 비용: 약 40만 원(추정)
- 실행 난이도: 5단계 중 3(보통)
- 참고할 사례: 비슷한 단지 기록 3건
출력:
명절 나눔 행사는 이 단지의 '안부와 관계' 분야 필요 지표가 전체 단지 중 상위 12%인 점을 고려해 검토 후보로 올린 프로그램입니다. 비슷한 단지 20곳 가운데 11곳이 운영했고, 전체 단지로 보면 58%가 운영한 적이 있습니다. 주로 사회복지관·복지센터와 함께 하며, 기록상 9월, 1월, 2월에 많이 열렸습니다. 공단 쪽 연간 비용은 약 40만 원으로 추정되고 실행 난이도는 5단계 중 3(보통)이며, 비슷한 단지 기록 3건을 참고하실 수 있습니다.

예시 2
사실:
- 프로그램: 찾아가는 법률 상담
- 분야: 생활과 경제
- 비슷한 단지 20곳 가운데 운영한 곳: 6곳
- 전체 단지 중 운영한 적이 있는 비율: 31%
- 기록상 많이 열린 달: 4·10·6월
- 공단 쪽 연간 비용: 약 2만 원(추정)
- 실행 난이도: 5단계 중 1(쉬움)
- 주의: 주거복지사가 있어야 하는 프로그램인데 이 단지는 미배치
- 참고할 사례: 비슷한 단지 기록 2건, 사례집 카드 1장
출력:
찾아가는 법률 상담은 '생활과 경제' 분야의 검토 후보입니다. 비슷한 단지 20곳 가운데 6곳이 운영했고, 전체 단지로 보면 31%가 운영한 적이 있습니다. 기록상 4월, 10월, 6월에 많이 열렸습니다. 공단 쪽 연간 비용은 약 2만 원으로 추정되고 실행 난이도는 5단계 중 1(쉬움)입니다. 다만 주거복지사가 있어야 하는 프로그램인데 이 단지는 미배치이므로 맡을 사람을 먼저 정해야 하며, 비슷한 단지 기록 2건과 사례집 카드 1장을 참고하실 수 있습니다."""

PROMPT = """사실:
{facts}
출력:"""

RETRY = """

(앞서 쓴 문장은 검사에서 떨어졌습니다: {why}. 규칙을 지켜 다시 쓰십시오.)
출력:"""


def explain(rec, llm_fn=None, retries=1):
    """llm_fn(prompt)->str 을 주면 다듬은 문장을 검사해 통과할 때만 쓴다. 없으면 템플릿 문장.

    검사에서 떨어지면 이유를 붙여 retries번 다시 시킨다. 끝까지 떨어지면 템플릿 문장을 쓴다.
    """
    draft = template(rec)
    if llm_fn is None:
        return dict(text=draft, source="template")
    prompt, tries = PROMPT.format(facts=facts_text(rec)), []
    for i in range(retries + 1):
        out = clean(llm_fn(prompt if i == 0 else prompt + RETRY.format(why=why)))
        chk = check_grounded(out, rec)
        chk["form"], chk["binding"] = check_form(out), check_binding(out, rec)
        chk["ok"] = chk["ok"] and not chk["form"] and not chk["binding"]
        tries.append(dict(text=out, check=chk))
        if chk["ok"]:
            return dict(text=out, source="llm", attempts=i + 1, check=chk, tries=tries)
        why = "; ".join(filter(None, ["사실에 없는 숫자 " + ", ".join(chk["unknown_numbers"]) if chk["unknown_numbers"] else "",
                                      "금지 표현 " + ", ".join(chk["banned"]) if chk["banned"] else "", "형식 " + ", ".join(chk["form"]) if chk["form"] else "",
                                      "뜻이 바뀐 숫자·해석 " + ", ".join(chk["binding"]) if chk["binding"] else ""]))
    return dict(text=draft, source="template_fallback", attempts=retries + 1, check=chk, tries=tries)
