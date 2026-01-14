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

# =========================
# CONFIG
# =========================
CAND_STEP = 18
MAX_N = 6
CLUSTER_DIST = 55

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

    # 후보점 기반 광량 히트맵
    light_map = np.zeros((H, Wimg), np.float32)

    for (x, y) in pts:
        if x < MARGIN or x >= Wimg - MARGIN or y < MARGIN or y >= H - MARGIN:
            continue

        times, total = daily_light_area((x, y), origin, base_dir_vec, img)
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

        if light_eff > 0:
            light_map[y, x] = max(light_map[y, x], float(light_eff))

        plant_recs = recommend_plants(float(light_eff), topk=5)
        has_in_range = any(r["in_range"] for r in plant_recs)
        plant_pen = 0.0 if has_in_range else PLANT_PENALTY

        score = (
            W["LIGHT"] * float(light_eff) +
            W["WALL"]  * s_wall +
            W["STAB"]  * s_stab -
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
        }

        scored.append((float(score), (int(x), int(y)), meta))

    if light_map.max() > 0:
        light_map = cv2.GaussianBlur(light_map, (0, 0), 7)

    scored.sort(key=lambda v: v[0], reverse=True)

    use_max = int(max_n) if (max_n is not None) else MAX_N
    chosen = cluster_and_pick(scored, cluster_dist=CLUSTER_DIST, max_total=use_max)
    if not chosen:
        raise RuntimeError("No spots chosen. Try lowering thresholds.")

    packed = []
    for idx, (s, pt, meta) in enumerate(chosen, start=1):
        packed.append({
            "rank": idx,
            "score": float(s),
            "pt": [int(pt[0]), int(pt[1])],
            "features": {
                "light_eff": float(meta["light_eff"]),
                "occ": float(meta["occ"]),
                "wall": float(meta["wall"]),
                "stab": float(meta["stab"]),
                "times": meta["times"],
            },
            "top_plants": meta["plant_recs"],
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

