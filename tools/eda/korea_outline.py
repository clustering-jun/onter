# -*- coding: utf-8 -*-
"""한반도 남측 육지 외곽선 만들기(외부 지도 타일 없이 지도 배경을 그리기 위함).

원리: 국토정책지표 250m 격자(경로당 접근성) shp의 각 격자 bbox 중심을 읽어(UTM-K, EPSG:5179) 위경도로 바꾸고,
약 1km 해상도 육지 마스크를 만든 뒤 등고선(0.5)으로 외곽 다각형을 뽑아 단순화한다.
라이브러리: numpy·matplotlib·shapely만 사용(geopandas·pyproj 없음 → 횡메르카토르 역변환을 직접 구현).
산출: <out>/korea_outline.geojson (육지 다각형, 위경도), <out>/korea_land_mask.npz
사용: python korea_outline.py <출력폴더>
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union

SHP = r"C:/Users/user/Desktop/2026 DRIVE/project/data/raw/(B100)국토통계_국토정책지표-경로당 접근성-250M_2024/41.1 경로당(읍면동격자) 접근성"


def tm_inverse(x, y, lat0=38.0, lon0=127.5, k0=0.9996, fe=1_000_000.0, fn=2_000_000.0, a=6378137.0, f=1 / 298.257222101):
    """횡메르카토르 역변환(Snyder 식). UTM-K → (위도, 경도) 도 단위."""
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    def M(phi):
        return a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * phi - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * np.sin(2 * phi)
                    + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * np.sin(4 * phi) - (35 * e2 ** 3 / 3072) * np.sin(6 * phi))
    m = M(np.radians(lat0)) + (y - fn) / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - np.sqrt(1 - e2)) / (1 + np.sqrt(1 - e2))
    p1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * np.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * np.sin(4 * mu) + (151 * e1 ** 3 / 96) * np.sin(6 * mu) + (1097 * e1 ** 4 / 512) * np.sin(8 * mu)
    c1 = ep2 * np.cos(p1) ** 2
    t1 = np.tan(p1) ** 2
    n1 = a / np.sqrt(1 - e2 * np.sin(p1) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * np.sin(p1) ** 2) ** 1.5
    d = (x - fe) / (n1 * k0)
    lat = p1 - (n1 * np.tan(p1) / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
                                         + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / np.cos(p1)
    return np.degrees(lat), lon0 + np.degrees(lon)


def read_centers():
    shx = np.fromfile(SHP + ".shx", dtype=np.uint8)
    rec = shx[100:].reshape(-1, 8)
    off = (rec[:, :4].copy().view(">i4").ravel().astype(np.int64)) * 2
    shp = np.memmap(SHP + ".shp", dtype=np.uint8, mode="r")
    idx = (off + 12)[:, None] + np.arange(32)[None, :]          # 레코드 헤더 8 + 도형 유형 4 → bbox 4개 double
    bb = np.asarray(shp[idx]).copy().view("<f8").reshape(-1, 4)
    return (bb[:, 0] + bb[:, 2]) / 2, (bb[:, 1] + bb[:, 3]) / 2


def main(out):
    os.makedirs(out, exist_ok=True)
    x, y = read_centers()
    lat, lon = tm_inverse(x, y)
    print("cells", len(x), "lat", lat.min().round(3), lat.max().round(3), "lon", lon.min().round(3), lon.max().round(3))
    res = 0.01                                                   # 약 1km
    lo0, la0 = 124.4, 32.9
    nx, ny = int((132.0 - lo0) / res), int((38.8 - la0) / res)
    grid = np.zeros((ny, nx), dtype=np.uint8)
    ix = ((lon - lo0) / res).astype(int); iy = ((lat - la0) / res).astype(int)
    ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    grid[iy[ok], ix[ok]] = 1
    np.savez_compressed(os.path.join(out, "korea_land_mask.npz"), grid=grid, lon0=lo0, lat0=la0, res=res)
    pad = np.pad(grid, 1)
    xs = lo0 + (np.arange(nx + 2) - 1 + 0.5) * res
    ys = la0 + (np.arange(ny + 2) - 1 + 0.5) * res
    cs = plt.contour(xs, ys, pad.astype(float), levels=[0.5])
    polys = []
    for path in cs.allsegs[0]:
        if len(path) < 4:
            continue
        p = Polygon(path).buffer(0)
        if p.area < 0.0004:                                      # 아주 작은 섬(약 4km² 미만)은 생략
            continue
        polys.append(p.simplify(0.006, preserve_topology=True))
    plt.close("all")
    land = unary_union(polys)
    gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "대한민국 육지(격자 기반 근사)"},
                                                      "geometry": json.loads(json.dumps(mapping(land)))}]}
    def rnd(o):
        if isinstance(o, float):
            return round(o, 4)
        if isinstance(o, (list, tuple)):
            return [rnd(v) for v in o]
        if isinstance(o, dict):
            return {k: rnd(v) for k, v in o.items()}
        return o
    with open(os.path.join(out, "korea_outline.geojson"), "w", encoding="utf-8") as fh:
        json.dump(rnd(gj), fh, ensure_ascii=False, separators=(",", ":"))
    print("polygons", len(polys), "bytes", os.path.getsize(os.path.join(out, "korea_outline.geojson")))


if __name__ == "__main__":
    main(sys.argv[1])
