# -*- coding: utf-8 -*-
"""사례집 OCR 통합본을 사례 18개와 앞부분(기관 소개·입주민 현황·배치 단지 목록)으로 나눈다.

규칙: 사례는 '[영역]' 줄 다음(또는 같은 줄)에 '#지역' 표기가 오면 시작한다. 4부(협업 현장)는 영역 표기 없이 '#지역'으로 시작한다.
목차 줄('[영역] 지역 | 프로그램명')과 부 제목 줄에서 앞 사례가 끝난다. 각 사례에는 소속 부(part)와 목차에서 가져온 지역·프로그램명을 붙인다.
"""
import re

DOMAINS = ("주거환경", "문화", "공동체", "돌봄", "건강")
PARTS = [("P1", "주거복지사와 입주민이 더불어 살아가는 이야기"), ("P2", "주거복지사가 들려주는 우리 단지의 이모저모"),
         ("P3", "주거복지사의 하루를 걷다"), ("P4", "살기 좋은 마을을 위한 주거복지사의 협업 현장")]
TOC_RX = re.compile(r"^\[(주거환경|문화|공동체|돌봄|건강)\]\s+([^|#\[]+?)\s*\|\s*(.+)$")
DOM_RX = re.compile(r"^\[(주거환경|문화|공동체|돌봄|건강)\]\s*(#.*)?$")
P4_TOC = [("전북 군산나운4", "행복나눔 공유곳간"), ("대전·충남권역", "소소숲여행"), ("인천 부천권역", "돌봄플러그")]


def segment(text):
    L = text.split("\n")
    toc = []                                      # (영역, 지역, 프로그램명) 순서대로(중복 제거)
    for l in L:
        m = TOC_RX.match(l.strip())
        if m and (m.group(1), m.group(2).strip()) not in [(a, b) for a, b, _ in toc]:
            toc.append((m.group(1), m.group(2).strip(), m.group(3).strip()))
    starts = []
    p4_line = next(i for i, l in enumerate(L) if l.startswith(PARTS[3][1]) and i > 200)
    for i, l in enumerate(L):
        s = l.strip()
        m = DOM_RX.match(s)
        if m and (m.group(2) or (i + 1 < len(L) and L[i + 1].strip().startswith("#"))):
            starts.append((i, m.group(1)))
        elif i > p4_line and s.startswith("#") and not DOM_RX.match(L[i - 1].strip()):
            starts.append((i, "협업"))
    # 끝 경계: 목차 줄, 부 제목(줄바꿈으로 쪼개진 '주거복지사의' 포함), 뒤표지 인용문, 판권
    stop_rx = re.compile(r"^(주거복지사의$|영구임대주택 주거복지사 배치사업$|\"오늘이 일흔 살)")
    stops = {i for i, l in enumerate(L) if TOC_RX.match(l.strip()) or any(l.strip().startswith(p) for _, p in PARTS) or stop_rx.match(l.strip())}
    cases = []
    for k, (i, dom) in enumerate(starts):
        nxt = starts[k + 1][0] if k + 1 < len(starts) else len(L)
        end = min([j for j in stops if i < j < nxt] + [nxt])
        body = "\n".join(L[i:end]).strip()
        part = "P1" if k < 5 else "P2" if k < 10 else "P3" if k < 15 else "P4"     # 1~3부 5개씩, 4부 3개(목차 구성)
        cases.append(dict(seq=k + 1, domain=dom, part=part, line_from=i + 1, line_to=end, text=body))
    # 목차와 맞추기: 1~3부는 영역별 등장 순서, 4부는 고정 목차
    by_dom = {d: [t for t in toc if t[0] == d] for d in DOMAINS}
    used = {d: 0 for d in DOMAINS}
    p4 = 0
    for c in cases:
        if c["domain"] == "협업":
            c["region"], c["program_title"] = P4_TOC[p4]
            p4 += 1
        else:
            t = by_dom[c["domain"]][used[c["domain"]]]
            used[c["domain"]] += 1
            c["region"], c["program_title"] = t[1], t[2]
        c["case_id"] = f"CB{c['seq']:02d}"
    intro = "\n".join(L[: starts[0][0]])
    return cases, intro
