# -*- coding: utf-8 -*-
"""한국어 조사 선택(받침 유무). 보고서·그림 제목에 자동으로 들어가는 문장의 조사 오류를 막는다."""


def _last_hangul(word):
    for ch in reversed(str(word)):
        if "가" <= ch <= "힣":
            return ch
    return None


def has_batchim(word):
    """마지막 한글 글자에 받침이 있으면 True. 한글이 없으면(숫자·영문) 받침 없음으로 본다."""
    ch = _last_hangul(word)
    return bool(ch) and (ord(ch) - 0xAC00) % 28 != 0


def _rieul(word):
    ch = _last_hangul(word)
    return bool(ch) and (ord(ch) - 0xAC00) % 28 == 8   # ㄹ 받침


def iga(word):
    return "이" if has_batchim(word) else "가"


def eunneun(word):
    return "은" if has_batchim(word) else "는"


def eulreul(word):
    return "을" if has_batchim(word) else "를"


def gwawa(word):
    return "과" if has_batchim(word) else "와"


def wa(word):
    return gwawa(word)


def ro(word):
    """으로/로: 받침이 없거나 ㄹ 받침이면 '로', 그 밖의 받침이면 '으로'."""
    return "로" if (not has_batchim(word) or _rieul(word)) else "으로"


def q(word):
    """따옴표로 감싼 단어."""
    return f"'{word}'"


def qiga(word):
    return f"'{word}'{iga(word)}"


def qeunneun(word):
    return f"'{word}'{eunneun(word)}"


def qgwawa(word):
    return f"'{word}'{gwawa(word)}"
