# -*- coding: utf-8 -*-
"""단지통합 엑셀(사용자가 정리한 최신 단지 ID)을 읽어 커뮤니티 분석의 단지 기준표로 쓴다.

- 단지 고유 ID는 통합표의 complex_id(예: KOH_1)를 따른다. 단지명으로 연결하며 통합표 안에서 단지명·ID는 모두 유일해야 한다.
- 통합표에 없는 단지는 커뮤니티 분석에서 제외한다(행 번호 source_row는 원본 엑셀 행 번호 그대로 둔다).
"""
import pandas as pd

SHEET = "단지통합"


def load_integrated(path, sheet=SHEET):
    df = pd.read_excel(path, sheet_name=sheet)
    for c in ("complex_id", "단지명"):
        if c not in df.columns:
            raise ValueError(f"통합표에 '{c}' 열이 없다")
    if df["complex_id"].isna().any() or df["단지명"].isna().any():
        raise ValueError("complex_id·단지명에 빈 값이 있다")
    if df["complex_id"].duplicated().any() or df["단지명"].duplicated().any():
        raise ValueError("complex_id 또는 단지명이 중복된다")
    return df


def id_table(df):
    """(complex_id, 단지명) 기준표."""
    return df[["complex_id", "단지명"]].copy()
