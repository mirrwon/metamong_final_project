# 전체 파이프라인

import os, json, time
import cv2
import numpy as np
import torch

from .config import (
    BASE_DIR, RESULT_DIR, RESULT_JSON_LATEST, FAIL_LOG_PATH, FB_LOG_PATH, WEIGHTS_PATH,
    debug_print_paths
)
from .sam_vit import segment_floor, get_floor_center
from .viz import draw_debug
from .window_detect import detect_window_candidate, window_segment_points, base_dir

print("[PIPELINE FILE]", __file__)


# =========================
# CONFIG
# =========================
CAND_STEP = 18
MAX_N = 6
CLUSTER_DIST = 55

# surface penalty (A안)
SURFACE_PENALTY = 25.0          # 시작값: 25 (15~35 사이에서 튜닝)
SURFACE_PENALTY_ONLY_IF_HAS_FLOOR = True  # floor 후보가 하나라도 있으면 other 감점 강화

WINDOW_SAMPLES = 9
RAY_SAMPLES = 22
DEPTH_OCC_THRESHOLD = 0.06
OCC_MODE = "v8"
OCCLUSION_WEIGHT_V8 = 0.55
OCCLUSION_STRENGTH_V7 = 0.65

W = {
    "LIGHT": 0.68,
    "WALL":  0.16,
    "PATH":  0.55,   # (현재 score에 미사용 - 필요시 다음 단계에서 반영)
    "STAB":  0.25,
}

MIN_WALL = 0.15
MIN_STAB = 0.05
PLANT_PENALTY = 0.25

# --- NEW: 창/경계 과근접 후보 제거용 ---
MIN_ORIGIN_DIST_PX = 140   # 창 origin(빛 기준점)과 너무 가까우면 제외(픽셀)
MIN_WALL_FOR_BEST = 0.28   # best_spot은 벽/경계로 너무 붙지 않게(0~1)
BEST_STAB_BONUS = 0.12     # best_spot 선택 시 안정성(stab) 가중 보너스


# =========================
# USER / PLANTS
# =========================
USER = {"pet": False, "is_beginner": True}

PLANTS = [
    {"name":"산세베리아", "min":0.70, "max":1.20, "pet_safe":True,  "care":1, "tags":["초보","저광량"]},
    {"name":"스투키",     "min":0.60, "max":1.10, "pet_safe":True,  "care":1, "tags":["초보","저광량"]},
    {"name":"아레카야자", "min":1.10, "max":1.70, "pet_safe":True,  "care":2, "tags":["공기정화"]},
    {"name":"올리브나무", "min":1.40, "max":2.20, "pet_safe":True,  "care":3, "tags":["고광량","관리어려움"]},
    {"name":"몬스테라",   "min":1.00, "max":1.60, "pet_safe":False, "care":2, "tags":["주의(반려동물)"]},
]

# =========================
# UTILS
# =========================

def classify_surface_by_depth(dval: float, floor_p20: float, floor_p80: float) -> str:
    """
    아주 안전한 1차 분기:
    - floor_p20 ~ floor_p80 안이면 floor
    - 아니면 other (탁자/가구/오인 등 포함)
    """
    if floor_p20 <= dval <= floor_p80:
        return "floor"
    return "other"

def to_jsonable(x):
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.ndarray,)):
        return x.tolist()
    if isinstance(x, dict):
        return {k: to_jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_jsonable(v) for v in x]
    return x

def floor_core(mask01, k=19):
    ker = np.ones((k, k), np.uint8)
    return cv2.erode(mask01.astype(np.uint8), ker, iterations=1)

def candidates_from_mask(mask01, step=CAND_STEP):
    h, w = mask01.shape
    pts=[]
    for y in range(0, h, step):
        for x in range(0, w, step):
            if mask01[y, x]:
                pts.append((x, y))
    return pts

def distance_to_boundary(mask01):
    m = (mask01 > 0).astype(np.uint8) * 255
    dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    return dist / (dist.max() + 1e-6)

def cluster_and_pick(items, cluster_dist=CLUSTER_DIST, max_total=MAX_N):
    clusters = []
    for it in items:
        score, pt, meta = it
        x, y = pt
        placed = False
        for c in clusters:
            cx, cy = c["center"]
            if (x-cx)**2 + (y-cy)**2 < cluster_dist**2:
                c["items"].append(it)
                n = len(c["items"])
                c["center"] = ((cx*(n-1)+x)/n, (cy*(n-1)+y)/n)
                placed = True
                break
        if not placed:
            clusters.append({"center": (x, y), "items": [it]})

    clusters.sort(key=lambda c: max(v[0] for v in c["items"]), reverse=True)

    picked = []
    for c in clusters:
        c["items"].sort(key=lambda v: v[0], reverse=True)
        picked.append(c["items"][0])
        if len(picked) >= max_total:
            break

    picked.sort(key=lambda v: v[0], reverse=True)
    return picked

# =========================
# DEPTH
# =========================
def get_depth(img_bgr, device):
    try:
        midas = torch.hub.load("intel-isl/MiDaS", "MiDaS_small")
        midas.to(device).eval()
        tfm = torch.hub.load("intel-isl/MiDaS", "transforms").small_transform
    except Exception as e:
        print("[WARN] MiDaS load failed:", e)
        return None

    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    inp = tfm(rgb).to(device)
    with torch.no_grad():
        pred = midas(inp)
        pred = torch.nn.functional.interpolate(
            pred.unsqueeze(1),
            size=rgb.shape[:2],
            mode="bicubic",
            align_corners=False
        ).squeeze()
    d = pred.detach().cpu().numpy().astype(np.float32)
    dmin, dmax = np.percentile(d, 2), np.percentile(d, 98)
    depth = (d - dmin) / (dmax - dmin + 1e-6)
    return np.clip(depth, 0, 1)

def depth_stability(depth):
    d = cv2.GaussianBlur(depth.astype(np.float32), (0, 0), 1.2)
    gx = cv2.Sobel(d, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(d, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.sqrt(gx*gx + gy*gy)
    denom = np.percentile(grad, 95) + 1e-6
    return 1.0 - np.clip(grad / denom, 0, 1)

def occ_v8_depth(p0, p1, depth, core_mask01):
    h, w = depth.shape
    x0, y0 = p0
    x1, y1 = p1
    prev = None
    hits = 0
    valid = 0
    for i in range(1, RAY_SAMPLES+1):
        t = i / (RAY_SAMPLES + 1)
        x = int(x0 + (x1 - x0) * t)
        y = int(y0 + (y1 - y0) * t)
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        if core_mask01[y, x] == 0:
            continue
        d = float(depth[y, x])
        if prev is not None and (d - prev) > DEPTH_OCC_THRESHOLD:
            hits += 1
        prev = d
        valid += 1
    if valid == 0:
        return 0.0
    return min(1.0, hits / valid)

# =========================
# LIGHT
# =========================
def rotate2d(vec, deg):
    rad = np.deg2rad(deg)
    c, s = np.cos(rad), np.sin(rad)
    x, y = float(vec[0]), float(vec[1])
    return np.array([c*x - s*y, s*x + c*y], dtype=np.float32)

def daily_light_area(pt, origin, base_dir_vec, img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    p = np.array([pt[0], pt[1]], dtype=np.float32)

    def one_time(dir_deg):
        dvec = rotate2d(base_dir_vec, dir_deg)
        v = p - origin
        dist = np.linalg.norm(v) + 1e-6
        v = v / dist
        align = max(0.0, float(np.dot(v, dvec)))
        decay = 1.0 / (1.0 + dist * 0.01)
        bright = float(gray[int(pt[1]), int(pt[0])])
        return 0.60 * align + 0.25 * decay + 0.15 * bright

    scores = {"morning": one_time(-25), "noon": one_time(0), "evening": one_time(+25)}
    total = float(scores["morning"] + scores["noon"] + scores["evening"])
    return scores, total

# =========================
# PLANT
# =========================
def plant_light_score(light_eff, p):
    mn, mx = float(p["min"]), float(p["max"])
    if mn <= light_eff <= mx:
        return 1.0
    d = (mn - light_eff) if light_eff < mn else (light_eff - mx)
    return float(1.0 / (1.0 + d * 2.0))

def plant_care_penalty(is_beginner, plant_care):
    try:
        c = int(plant_care)
    except Exception:
        c = 2
    if is_beginner:
        return float({1: 0.0, 2: 0.15, 3: 0.35}.get(c, 0.2))
    return 0.0

def recommend_plants(light_eff, topk=5):
    rec = []
    pet = bool(USER.get("pet", False))
    is_beginner = bool(USER.get("is_beginner", True))

    for p in PLANTS:
        if pet and (p.get("pet_safe", True) is False):
            continue

        ls = plant_light_score(float(light_eff), p)
        plant_care = p.get("care", 2) if p.get("care", 2) is not None else 2
        pen = float(plant_care_penalty(is_beginner, plant_care))
        care_score = max(0.0, 1.0 - pen)
        final = 0.70 * ls + 0.30 * care_score

        in_range = (float(p["min"]) <= float(light_eff) <= float(p["max"]))

        rec.append({
            "name": p["name"],
            "score": float(final),
            "in_range": bool(in_range),
            "reason": "광량 적합" if in_range else "광량 근접",
        })

    rec.sort(key=lambda x: x["score"], reverse=True)
    return rec[:topk]

def recommend_floor_large(light_level: str, topk=5):
    res = []
    for p in PLANTS:
        if p["name"] in ("올리브나무",):   # 예: 너무 특수한 건 제외
            continue

        # 바닥 큰 화분은 medium 이상 선호
        if light_level == "dim" and p["min"] > 0.7:
            continue

        res.append({
            "name": p["name"],
            "reason": f"바닥 설치 + {light_level} 광 환경",
        })
    return res[:topk]

def recommend_table_small(light_level: str, topk=5):
    res = []
    for p in PLANTS:
        # 키 작은 식물 위주(임시 규칙)
        if p["max"] > 1.3:
            continue

        res.append({
            "name": p["name"],
            "reason": f"테이블 설치 + {light_level} 광 환경",
        })
    return res[:topk]

def recommend_low_light(topk=5):
    res = []
    for p in PLANTS:
        if p["min"] <= 0.7:
            res.append({
                "name": p["name"],
                "reason": "저광량 환경에 적합",
            })
    return res[:topk]

# =========================
# RUN PIPELINE
# =========================
def run_pipeline(
    image_path: str,
    user_opts: dict | None = None,
    max_n: int | None = None,
    debug_viz: bool = False,
    save_outputs: bool = True,
):
    debug_print_paths()
    os.makedirs(RESULT_DIR, exist_ok=True)

    if user_opts:
        USER["pet"] = bool(user_opts.get("pet", USER["pet"]))
        USER["is_beginner"] = bool(user_opts.get("is_beginner", USER["is_beginner"]))

    img = cv2.imread(image_path)
    if img is None:
        raise RuntimeError(f"image read failed: {image_path}")

    H, Wimg = img.shape[:2]
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # --- FLOOR (SAM) ---
    floor_mask_255, _ = segment_floor(img)
    if floor_mask_255 is None:
        raise RuntimeError("floor segmentation failed (SAM returned None)")

    floor = (floor_mask_255 > 0).astype(np.uint8)

    ratio = float(np.sum(floor > 0)) / float(H * Wimg)
    print(f"[FLOOR] area ratio = {ratio:.3f}")
    if ratio < 0.08:
        raise RuntimeError("Floor mask too small -> SAM floor segmentation fail")

    core = floor_core(floor, 19)
    if core.sum() < 500:
        core = floor

    # --- WINDOW DETECT ---
    win = detect_window_candidate(img, floor, prefer="right", debug=debug_viz)
    window_boxes = None
    if win is not None:
        x, y, ww, hh = win
        window_boxes = [(x, y, x + ww, y + hh)]

    # --- LIGHT ORIGIN / DIR ---
    # floor center (가능하면 SAM 함수 사용, 실패하면 마스크 기반 fallback)
    try:
        fc = get_floor_center(core)  # 기대: (x,y)
        floor_c = np.array([float(fc[0]), float(fc[1])], dtype=np.float32)
    except Exception:
        ys, xs = np.where(core > 0)
        if len(xs) > 0:
            floor_c = np.array([float(np.mean(xs)), float(np.mean(ys))], dtype=np.float32)
        else:
            floor_c = np.array([Wimg * 0.5, H * 0.8], dtype=np.float32)

    if win is not None:
        # 창 기준 origin: 창 아래쪽 중앙
        x, y, ww, hh = win
        origin = np.array([x + ww * 0.5, y + hh * 0.85], dtype=np.float32)
        base_dir_vec = base_dir(origin, floor_c)  # 창 -> 바닥중심 방향
    else:
        # fallback
        origin = np.array([Wimg * 0.8, H * 0.3], dtype=np.float32)
        base_dir_vec = np.array([0.0, 1.0], np.float32)

    # --- DEPTH / STAB ---
    depth = get_depth(img, device)
    if depth is None:
        depth = np.zeros((H, Wimg), np.float32)
        stab_raw = np.ones((H, Wimg), np.float32)
        depth_ok = False
    else:
        stab_raw = depth_stability(depth)
        depth_ok = True

    stab = stab_raw * (core > 0).astype(np.float32)
    dist_wall = distance_to_boundary(core)

    pts = candidates_from_mask(core, step=CAND_STEP)
    scored = []
    MARGIN = 12

    # --- FLOOR DEPTH STATS (for surface classification) ---
    if depth is not None and depth_ok:
        floor_depth = depth[core > 0]
        if floor_depth.size > 0:
            floor_d_mean = float(np.mean(floor_depth))
            floor_d_p20 = float(np.percentile(floor_depth, 20))
            floor_d_p80 = float(np.percentile(floor_depth, 80))
        else:
            floor_d_mean, floor_d_p20, floor_d_p80 = 0.0, 0.0, 1.0
    else:
        floor_d_mean, floor_d_p20, floor_d_p80 = 0.0, 0.0, 1.0


    # 후보점 기반 광량 히트맵
    light_map = np.zeros((H, Wimg), np.float32)

    for (x, y) in pts:
        if x < MARGIN or x >= Wimg - MARGIN or y < MARGIN or y >= H - MARGIN:
            continue

        times, total = daily_light_area((x, y), origin, base_dir_vec, img)

        if depth_ok and (len(scored) < 5):  # 상위 몇 번만 찍기
            floor_depth = depth[core > 0]
            fd_mean = float(np.mean(floor_depth))
            fd_p20 = float(np.percentile(floor_depth, 20))
            fd_p80 = float(np.percentile(floor_depth, 80))
            print("[DEPTHCHK]", "pt=", (x, y), "d=", float(depth[y, x]), "floor_mean=", fd_mean, "p20/p80=", fd_p20,
                  fd_p80)

        # --- NEW: 창 origin 근처 후보 제거 (빛 점수에 끌려 이상한 위치 방지) ---
        od = float(np.hypot(x - float(origin[0]), y - float(origin[1])))
        if od < MIN_ORIGIN_DIST_PX:
            continue

        s_wall = float(dist_wall[y, x])
        s_stab = float(stab[y, x])

        if s_wall < MIN_WALL:
            continue
        if s_stab < MIN_STAB:
            continue

        # occlusion
        if not depth_ok:
            occ = 0.0
        else:
            occ = occ_v8_depth((int(origin[0]), int(origin[1])), (x, y), depth, core)

        light_eff = total * (0.65 + 0.35 * s_stab) * (1.0 - OCCLUSION_WEIGHT_V8 * occ)
        dval = float(depth[y, x]) if (depth is not None and depth_ok) else 0.0
        surface = classify_surface_by_depth(dval, floor_d_p20, floor_d_p80)

        if light_eff > 0:
            light_map[y, x] = max(light_map[y, x], float(light_eff))

        plant_recs = recommend_plants(float(light_eff), topk=5)
        has_in_range = any(r["in_range"] for r in plant_recs)
        plant_pen = 0.0 if has_in_range else PLANT_PENALTY

        # ✅ 여기서는 "raw_score"만 계산하고 일단 저장(패널티는 2-pass로 적용)
        raw_score = (
                W["LIGHT"] * float(light_eff) +
                W["WALL"] * s_wall +
                W["STAB"] * s_stab -
                plant_pen
        )

        meta = {
            "pt": (int(x), int(y)),
            "times": times,
            "light_eff": float(light_eff),
            "occ": float(occ),
            "wall": float(s_wall),
            "stab": float(s_stab),
            "plant_recs": plant_recs,
            "depth": float(dval),
            "surface": surface,

            # ✅ 디버그 필드(나중에 JSON으로도 내보낼 수 있게)
            "raw_score": float(raw_score),
            "surface_penalty": 0.0,  # 2-pass에서 채움
            "final_score": float(raw_score),
        }

        scored.append((float(raw_score), (int(x), int(y)), meta))

    # --- 2-pass: floor 후보가 하나라도 있으면 other 감점 강화 ---
    has_floor_candidate = any(m.get("surface") == "floor" for (_, _, m) in scored)

    scored2 = []
    for (raw_s, pt, meta) in scored:
        surface = meta.get("surface", "floor")

        apply_surface_penalty = (surface == "other")
        if SURFACE_PENALTY_ONLY_IF_HAS_FLOOR:
            apply_surface_penalty = apply_surface_penalty and has_floor_candidate

        surface_pen = float(SURFACE_PENALTY) if apply_surface_penalty else 0.0
        final_s = float(raw_s) - surface_pen

        meta["surface_penalty"] = float(surface_pen)
        meta["final_score"] = float(final_s)

        scored2.append((float(final_s), pt, meta))

    scored = scored2

    if light_map.max() > 0:
        light_map = cv2.GaussianBlur(light_map, (0, 0), 7)

    scored.sort(key=lambda v: v[0], reverse=True)

    use_max = int(max_n) if (max_n is not None) else MAX_N
    chosen = cluster_and_pick(scored, cluster_dist=CLUSTER_DIST, max_total=use_max)

    # --- NEW: relative light level (within this room) ---
    chosen_light = [float(meta.get("light_eff", 0.0)) for (_, _, meta) in chosen]
    if len(chosen_light) >= 3:
        p20 = float(np.percentile(chosen_light, 20))
        p80 = float(np.percentile(chosen_light, 80))
    else:
        p20, p80 = 0.0, 1e9  # fallback: 전부 medium 취급

    def light_level(le: float) -> str:
        if le >= p80:
            return "bright"
        if le <= p20:
            return "dim"
        return "medium"

    def light_bias(times: dict) -> str:
        # times: {"morning": x, "noon": y, "evening": z}
        if not isinstance(times, dict) or not times:
            return "unknown"
        k = max(times, key=lambda kk: float(times.get(kk, 0.0)))
        return str(k)

    if not chosen:
        raise RuntimeError("No spots chosen. Try lowering thresholds.")

    # --- NEW: best_spot 재선정 (빛 쏠림 방지: 벽거리/안정성 우선) ---
    # chosen은 (score, pt, meta)
    best_idx = 0
    best_val = -1e9
    for i, (s, pt, meta) in enumerate(chosen):
        wall = float(meta.get("wall", 0.0))
        stabv = float(meta.get("stab", 0.0))
        # best 후보는 벽/경계 너무 가까우면 제외(단, 전부 제외되면 fallback)
        if wall < MIN_WALL_FOR_BEST:
            continue
        val = float(s) + BEST_STAB_BONUS * stabv + 0.05 * wall
        if val > best_val:
            best_val = val
            best_idx = i

    # best_idx를 0번으로 swap해서 packed[0]이 best_spot이 되게 유지
    if best_idx != 0:
        chosen[0], chosen[best_idx] = chosen[best_idx], chosen[0]

    packed = []
    for idx, (s, pt, meta) in enumerate(chosen, start=1):
        le = float(meta.get("light_eff", 0.0))
        times = meta.get("times", {}) or {}

        # --- NEW: spot usage classification ---
        y_norm = pt[1] / float(H)  # 화면 높이 기준 (0~1)
        stabv = float(meta.get("stab", 0.0))
        lvl = light_level(le)
        surf = meta.get("surface", "floor")

        if surf == "floor" and lvl in ("bright", "medium"):
            spot_usage = "floor_large"

        elif surf != "floor" and stabv > 0.55 and 0.35 < y_norm < 0.75:
            spot_usage = "table_small"

        elif lvl == "dim":
            spot_usage = "low_light"

        else:
            spot_usage = "avoid"

        # --- NEW: plant recommendation by usage ---
        if spot_usage == "floor_large":
            plant_recs = recommend_floor_large(lvl)

        elif spot_usage == "table_small":
            plant_recs = recommend_table_small(lvl)

        elif spot_usage == "low_light":
            plant_recs = recommend_low_light()

        else:
            plant_recs = []  # avoid

        packed.append({
            "rank": idx,
            "score": float(s),
            "raw_score": float(meta.get("raw_score", s)),
            "surface_penalty": float(meta.get("surface_penalty", 0.0)),
            "final_score": float(meta.get("final_score", s)),

            "pt": [int(pt[0]), int(pt[1])],
            "surface": surf,

            "features": {
                "light_eff": le,
                "occ": float(meta["occ"]),
                "wall": float(meta["wall"]),
                "stab": stabv,
                "times": times,
            },

            "light_profile": {
                "total": le,
                "times": times,
                "bias": light_bias(times),
                "level": lvl,
            },

            "spot_usage": spot_usage,

            "top_plants": plant_recs,

        })

    out = {
        "ts": float(time.time()),
        "image": image_path,
        "occ_mode": OCC_MODE,
        "depth_ok": bool(depth_ok),
        "max_n": int(use_max),
        "window_bbox": (list(win) if win is not None else None),
        "light_origin": [float(origin[0]), float(origin[1])],
        "best_spot": packed[0],
        "spots": packed,
    }

    # --- NEW: spot_types summary for UI ---
    type_summary = {"bright": 0, "medium": 0, "dim": 0}
    bias_summary = {"morning": 0, "noon": 0, "evening": 0, "unknown": 0}

    for s in packed:
        lp = s.get("light_profile", {})
        lvl = lp.get("level", "medium")
        bs = lp.get("bias", "unknown")

        type_summary[lvl] = int(type_summary.get(lvl, 0)) + 1
        bias_summary[bs] = int(bias_summary.get(bs, 0)) + 1

    out["spot_types"] = {
        "level_counts": type_summary,
        "bias_counts": bias_summary,
    }

    # --- SAVE JSON (result_latest.json) ---
    if save_outputs:
        try:
            with open(RESULT_JSON_LATEST, "w", encoding="utf-8") as f:
                json.dump(to_jsonable(out), f, ensure_ascii=False, indent=2)
            print("[JSON] saved ->", RESULT_JSON_LATEST)
        except Exception as e:
            print("[WARN] json dump failed:", e)

    # --- DEBUG VIZ ---
    # --- DEBUG VIZ (SAFE) ---
    if debug_viz:
        try:
            best_xy = tuple((out.get("best_spot") or {}).get("pt") or (0, 0))

            draw_debug(
                image=img,
                floor_mask=(core > 0),  # ✅ core는 이미 쓰고 있으니 그대로 OK
                windows=None,  # ✅ 창 감지 아직 안 붙였으면 None
                light_map=None,  # ✅ 라이트맵 없으면 None
                best_point=best_xy,
                save_path=os.path.join(RESULT_DIR, "result_latest_viz.png"),
            )
            print("[VIZ] saved ->", os.path.join(RESULT_DIR, "result_latest_viz.png"))
        except Exception as e:
            print("[WARN] draw_debug failed:", e)
