# 전체 파이프라인

import os, json, time
import cv2
import numpy as np
import torch

from app.config import (
    BASE_DIR, RESULT_DIR, RESULT_JSON_LATEST, FAIL_LOG_PATH, FB_LOG_PATH, WEIGHTS_PATH,
    debug_print_paths
)

from app.cv.utils import (
    floor_core,
    candidates_from_mask,
    distance_to_boundary,
    depth_stability,
    occ_v8_depth,
    classify_surface_by_depth,
    cluster_and_pick,
    to_jsonable,
    daily_light_area,
)

from .sam.sam_vit import segment_floor, get_floor_center
from .geometry.window_detect import detect_window_candidate, window_segment_points, base_dir
from .viz import draw_debug
from .depth.depth_midas import get_depth

from app.cv.cv_config import (
    CAND_STEP, MAX_N, CLUSTER_DIST,
    SURFACE_PENALTY, SURFACE_PENALTY_ONLY_IF_HAS_FLOOR,
    WINDOW_SAMPLES, RAY_SAMPLES,
    DEPTH_OCC_THRESHOLD, OCC_MODE, OCCLUSION_WEIGHT_V8, OCCLUSION_STRENGTH_V7,
    W, MIN_WALL, MIN_STAB, PLANT_PENALTY,
    MIN_ORIGIN_DIST_PX, MIN_WALL_FOR_BEST, BEST_STAB_BONUS,
)

print("[PIPELINE FILE]", __file__)


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


        # ✅ 제품형: 스팟 점수는 식물과 분리 (plant_pen 제거)
        raw_score = (
                W["LIGHT"] * float(light_eff) +
                W["WALL"] * s_wall +
                W["STAB"] * s_stab
        )

        meta = {
            "pt": (int(x), int(y)),
            "times": times,
            "light_eff": float(light_eff),
            "occ": float(occ),
            "wall": float(s_wall),
            "stab": float(s_stab),
            "depth": float(dval),
            "surface": surface,

            "raw_score": float(raw_score),
            "surface_penalty": 0.0,
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

            "top_plants": []
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
