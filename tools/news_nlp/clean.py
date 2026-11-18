# -*- coding: utf-8 -*-
"""본문 정제: 사이트 껍데기(메뉴·저작권·기자 표기·댓글·다른 기사 목록)를 걷어내고 기사 본문 덩어리만 남긴다.

방법(줄 단위 분류 + 본문 덩어리 확장)
1) 줄을 정리한다: 유니코드 정규화, 표 테두리(|) 제거, 줄머리 언론사·기자 표기 제거, 강제 줄바꿈 이어 붙이기, 같은 줄 중복 제거.
2) 줄마다 '버림·사진설명·부제·목록·본문·기타'로 분류한다(규칙).
3) 제목과 글자 2-gram 겹침이 가장 큰 본문 줄(앞쪽 우선)을 기준점으로 잡는다.
4) 기준점에서 앞뒤로 본문·목록 줄을 이어 붙이되, 그 밖의 줄이 3줄 이상 연달아 나오면 멈춘다(다른 기사·메뉴로 넘어간 것으로 본다).
5) 끝부분에 붙은 짧은 무관 줄(다른 기사 제목 등)과 해시태그·연관 뉴스 꼬리를 잘라 낸다.
"""
import re
import unicodedata

BOILER = re.compile(
    r"ⓒ|©|저작권자|무단\s*전재|재배포|글자크기|기사의 본문 내용은|이 기사를 공유|기자페이지|기사제보|독자투고|구독신청|신문구독|로그인|회원가입|"
    r"PDF 지면|개인정보\s*취급|이용약관|광고안내|^추천$|조회수|^-?\s*작성자|^-?\s*작성일|^-?\s*등록\s*\d|^-?\s*수정\s*\d|^-?\s*보도자료\s*\||담당부서|연락처\s*:|"
    r"자세한 사항은 붙임|^게시일:|^URL:|^이용 조건|공공누리|직접 확인하세요|언론사로 이동|본문 보기를 권장|전문은 해당|댓글|답글과 추천수|내 댓글|"
    r"jcttbgeditor|^\d{4}[.\-]\d{2}[.\-]\d{2}( \d{2}:\d{2}(:\d{2})?)?$|^\s*ㆍ\s*$|무단복제|Copyright|All rights reserved|관련기사|연관 뉴스|많이 본 뉴스|인기기사|"
    r"^사진=|발행일|^입력\s*\d{4}|보도시점|배포 즉시|사업자등록번호|^-?\s*[가-힣]{2,4}\s*(보도)?기자$|기사등록시간|^상세보기$|매체명\s*:|보도일\s*:|전화번호\s*:|팩스\s*:|^\[?[가-힣A-Za-z ]{2,12}\]?$")
EMAIL = re.compile(r"[\w.\-]+@[\w\-]+\.[\w.]+")
BYLINES = [re.compile(p) for p in (
    r"^\s*\[[^\]]{0,30}[=＝ᅵ|]\s*[가-힣]{2,4}\s*(기자|통신원|객원기자)?\s*\]\s*",       # [OO일보(지역)=홍길동 기자]
    r"^\s*\[[^\]]{0,30}\s[가-힣]{2,4}\s*기자\s*\]\s*",                                  # [아이뉴스24 홍길동 기자]
    r"^\s*\[[^\]]{2,20}\]\s*[가-힣]{2,4}\s*기자\s*[=＝]?\s*",                            # [창원=뉴시스]홍길동 기자 =
    r"^\s*[가-힣A-Za-z0-9·]{2,12}\s*[=＝]\s*[가-힣]{2,4}\s*기자\s*[|\]]?\s*",            # 매일일보 = 홍길동 기자 |
    r"^\s*\[(뉴스서치|단신|포토뉴스|동네뉴스|사진)\]\s*",
    r"^\s*[가-힣]{2,4}\s*기자\s*[=＝]\s*",                                           # (앞 패턴 뒤 남은) 홍길동 기자 =
)]
TAIL_NAME = re.compile(r"(?<=[.다!?”\"])\s+/?\s*[가-힣]{2,4}\s*(기자)?\s*$")
CAPTION = re.compile(r"^\s*(▲|△|◇|<사진|\(사진)|\(사진\s*[=:]|사진\s*[=:]\s*[가-힣]")
ITEM = re.compile(r"^\s*([-·•○■□◆◇◎※▶▷►➤✔✅]|\d+[.)]\s|[①-⑳]|[\U0001F300-\U0001FAFF☀-➿])")
END = re.compile(r"(다|요|음|함|됨|임|니다|었다|였다|했다)\s*[.。!?”\"'’)]*\s*$|[.。!?]\s*[”\"'’)]*\s*$")
HANGUL = re.compile(r"[가-힣]")


def norm(s):
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = s.replace("​", "").replace("\xa0", " ").replace("ᅲ", "|")
    return re.sub(r"[ \t]+", " ", s).strip()


def ngrams(s, n=2):
    s = re.sub(r"\s+", "", s)
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def overlap(a, b):
    A, B = ngrams(a), ngrams(b)
    return len(A & B) / max(1, min(len(A), len(B)))


def strip_byline(line):
    for rx in BYLINES:
        line = rx.sub("", line, count=1)
    return TAIL_NAME.sub("", line).strip()


def table_cells(line):
    """크롤러가 남긴 마크다운 표 줄: 칸이 여러 개면(다른 글 목록) 버리고, 한 칸이면 내용만 남긴다."""
    if not line.startswith("|"):
        return line
    cells = [c.strip() for c in line.strip("|").split("|")]
    cells = [c for c in cells if c and not re.fullmatch(r"-+", c)]
    if len(cells) >= 3:
        return ""
    return " ".join(cells)


def classify_line(line):
    if not line or (not HANGUL.search(line) and len(line) < 40):
        return "boilerplate"
    if EMAIL.search(line) and len(line) < 80:
        return "boilerplate"
    if BOILER.search(line):
        return "boilerplate"
    if CAPTION.search(line):
        return "caption"
    if ITEM.search(line) and len(line) >= 8:
        return "item"
    if len(line) >= 25 and (END.search(line) or line.endswith((",", "며", "고"))):
        return "content"
    if len(line) >= 60:
        return "content"
    if 6 <= len(line) <= 45 and not END.search(line):
        return "subtitle"
    return "other"


def reflow(lines):
    """강제 줄바꿈 이어 붙이기: 25자 이상인데 문장이 끝나지 않은 줄 + 목록 기호로 시작하지 않는 다음 줄."""
    out = []
    for x in lines:
        if out and len(out[-1]) >= 25 and not END.search(out[-1]) and not out[-1].endswith((",", ":")) and not ITEM.search(x) \
                and re.match(r"^[가-힣0-9A-Za-z(“\"'‘]", x) and not BOILER.search(x) and not BOILER.search(out[-1]):
            out[-1] = out[-1] + ("" if out[-1].endswith(("(", "‘", "“")) else " ") + x
        else:
            out.append(x)
    return out


def clean_article(title, body):
    """returns dict(body_clean, lead, captions, subtitles, n_lines, n_kept, cut_tail, is_snippet)"""
    raw = [table_cells(norm(x)) for x in str(body or "").split("\n")]
    raw = [strip_byline(x) for x in raw if x]
    snippet_marker = any(re.search(r"전문은 해당|본문 보기를 권장|직접 확인하세요", x) for x in raw)
    raw = [x for x in raw if x]
    # 강제 줄바꿈 기사(20~60자 줄이 문장 끝 없이 이어지는 비율이 높음)에만 이어 붙이기를 한다
    mid = [x for x in raw if 20 <= len(x) <= 60 and HANGUL.search(x) and not BOILER.search(x)]
    longest = max((len(x) for x in raw if HANGUL.search(x) and not BOILER.search(x)), default=0)
    hardwrapped = len(mid) >= 4 and sum(1 for x in mid if not END.search(x)) / len(mid) >= 0.6 and longest <= 80
    if hardwrapped:
        raw = reflow(raw)
    lines, seen = [], set()
    for x in raw:
        x = re.split(r"\s#[가-힣A-Za-z0-9]|\s연관 뉴스\s", x)[0].strip()   # 해시태그·연관 뉴스 꼬리
        key = re.sub(r"\s+", "", x)
        if not x or key in seen:
            continue
        seen.add(key)
        lines.append(x)
    cls = [classify_line(x) for x in lines]
    tnorm = re.sub(r"\s+", "", norm(title))
    for i, x in enumerate(lines):
        if re.sub(r"\s+", "", x) == tnorm:
            cls[i] = "boilerplate"
    content_idx = [i for i, c in enumerate(cls) if c == "content"] or [i for i, c in enumerate(cls) if c == "item"]
    caps = [re.sub(r"^[▲△◇\s]+", "", l) for l, c in zip(lines, cls) if c == "caption"]
    if not content_idx:
        return dict(body_clean="", lead="", captions=caps, subtitles=[], n_lines=len(lines), n_kept=0, cut_tail=False, is_snippet=True)
    front = content_idx[: max(3, len(content_idx) // 2 + 1)]
    anchor = max(front, key=lambda i: (overlap(title, lines[i]) + (0.15 if i == content_idx[0] else 0), -i))
    keep = {anchor}
    gap, j = 0, anchor + 1
    while j < len(lines):
        if cls[j] in ("content", "item"):
            gap = 0
            keep.add(j)
        else:
            gap += 1
            if gap >= 3:
                break
        j += 1
    j2, gap = anchor - 1, 0
    while j2 >= 0:
        if cls[j2] in ("content", "item"):
            keep.add(j2)
            gap = 0
        else:
            gap += 1
            if gap >= 3:
                break
        j2 -= 1
    ks = sorted(keep)
    # 끝에 붙은 짧은 무관 줄 자르기(제목·첫 문장과 겹침이 낮은 70자 미만 줄)
    ref = title + " " + lines[ks[0]]
    while len(ks) > 1 and len(lines[ks[-1]]) < 70 and overlap(ref, lines[ks[-1]]) < 0.12 and cls[ks[-1]] != "item":
        ks.pop()
    cut_tail = any(cls[k] == "content" and overlap(ref, lines[k]) < 0.12 for k in range(ks[-1] + 1, len(lines)))
    lo = ks[0]
    subtitles = [lines[k] for k in range(max(0, lo - 3), lo) if cls[k] == "subtitle"]
    body_lines = [lines[k] for k in ks]
    body_clean = "\n".join(body_lines)
    return dict(body_clean=body_clean, lead=body_lines[0], captions=caps, subtitles=subtitles, n_lines=len(lines), n_kept=len(body_lines),
                cut_tail=cut_tail, is_snippet=snippet_marker or len(body_clean) < 200, hardwrapped=hardwrapped)
