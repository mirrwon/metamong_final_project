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
from .geometry.window_detect import detect_window_candidate, base_dir
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

from .pnp_pose import solve_pnp_from_4pts, window_normal_world
from .window_mask import extract_window_corners_edge, extract_window_corners_hough
from app.cv.camera_intrinsics import make_K_from_fov

print("[PIPELINE FILE]", __file__)


def _bbox_to_corners4(win_bbox):
    x, y, w, h = [float(v) for v in win_bbox]
    return np.array([
        [x,     y],
        [x + w, y],
        [x + w, y + h],
        [x,     y + h],
    ], dtype=np.float32)


def _is_bbox_like(c4, bbox4, eps=3.0) -> bool:
    if c4 is None:
        return False
    c4 = np.array(c4, dtype=np.float32).reshape(4, 2)
    bbox4 = np.array(bbox4, dtype=np.float32).reshape(4, 2)
    for p in c4:
        d = np.min(np.linalg.norm(bbox4 - p[None, :], axis=1))
        if d > eps:
            return False
    return True


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

    # =========================
    # FLOOR (SAM)
    # =========================
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

    # =========================
    # WINDOW DETECT + REFINE (ONE PASS)
    # =========================
    win = detect_window_candidate(img, floor, prefer="right", debug=debug_viz)

    window_info = None
    corners4_edge = None
    corners4_h = None

    if win is not None:
        x, y, w, h = win
        bbox4 = _bbox_to_corners4(win)

        # 1) EDGE refine
        corners4_edge = extract_window_corners_edge(
            img, win, debug_dir=RESULT_DIR, tag="window"
        )

        corners4 = corners4_edge
        source = "edge"

        # edge 결과가 bbox랑 거의 같으면 실패로 간주 -> hough 시도
        if corners4 is None or _is_bbox_like(corners4, bbox4, eps=3.0):
            print("[WIN] edge failed or bbox-like -> try hough")
            corners4 = None
            source = "edge_looks_like_bbox"

            corners4_h = extract_window_corners_hough(
                img, win, debug_dir=RESULT_DIR, tag="window"
            )
            if corners4_h is not None:
                corners4 = corners4_h
                source = "hough"

        # 3) fallback
        if corners4 is None:
            corners4 = bbox4
            source = "bbox_fallback"

        window_info = {
            "bbox_xywh": [int(x), int(y), int(w), int(h)],
            "corners_4": np.array(corners4, dtype=np.float32).reshape(4, 2).tolist(),
            "source": source,
        }

        # 안전한 디버그 출력
        print("[WIN] win bbox:", win)
        print("[WIN] edge corners:", None if corners4_edge is None else np.array(corners4_edge).reshape(4, 2))
        print("[WIN] edge bbox-like?:", _is_bbox_like(corners4_edge, bbox4, eps=3.0) if corners4_edge is not None else None)
        print("[WIN] hough corners:", None if corners4_h is None else np.array(corners4_h).reshape(4, 2))

    # =========================
    # LIGHT ORIGIN / DIR
    # =========================
    try:
        fc = get_floor_center(core)
        floor_c = np.array([float(fc[0]), float(fc[1])], dtype=np.float32)
    except Exception:
        ys, xs = np.where(core > 0)
        if len(xs) > 0:
            floor_c = np.array([float(np.mean(xs)), float(np.mean(ys))], dtype=np.float32)
        else:
            floor_c = np.array([Wimg * 0.5, H * 0.8], dtype=np.float32)

    if win is not None:
        x, y, ww, hh = win
        origin = np.array([x + ww * 0.5, y + hh * 0.85], dtype=np.float32)
        base_dir_vec = base_dir(origin, floor_c)
    else:
        origin = np.array([Wimg * 0.8, H * 0.3], dtype=np.float32)
        base_dir_vec = np.array([0.0, 1.0], np.float32)

    # =========================
    # DEPTH / STAB
    # =========================
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

    # floor depth stats for surface
    if depth_ok:
        floor_depth = depth[core > 0]
        if floor_depth.size > 0:
            floor_d_p20 = float(np.percentile(floor_depth, 20))
            floor_d_p80 = float(np.percentile(floor_depth, 80))
        else:
            floor_d_p20, floor_d_p80 = 0.0, 1.0
    else:
        floor_d_p20, floor_d_p80 = 0.0, 1.0

    light_map = np.zeros((H, Wimg), np.float32)

    for (x, y) in pts:
        if x < MARGIN or x >= Wimg - MARGIN or y < MARGIN or y >= H - MARGIN:
            continue

        times, total = daily_light_area((x, y), origin, base_dir_vec, img)

        od = float(np.hypot(x - float(origin[0]), y - float(origin[1])))
        if od < MIN_ORIGIN_DIST_PX:
            continue

        s_wall = float(dist_wall[y, x])
        s_stab = float(stab[y, x])

        if s_wall < MIN_WALL:
            continue
        if s_stab < MIN_STAB:
            continue

        occ = 0.0 if not depth_ok else occ_v8_depth((int(origin[0]), int(origin[1])), (x, y), depth, core)

        light_eff = total * (0.65 + 0.35 * s_stab) * (1.0 - OCCLUSION_WEIGHT_V8 * occ)
        dval = float(depth[y, x]) if depth_ok else 0.0
        surface = classify_surface_by_depth(dval, floor_d_p20, floor_d_p80)

        if light_eff > 0:
            light_map[y, x] = max(light_map[y, x], float(light_eff))

        raw_score = (
            W["LIGHT"] * float(light_eff) +
            W["WALL"]  * s_wall +
            W["STAB"]  * s_stab
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

    # surface penalty pass
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
    if not chosen:
        raise RuntimeError("No spots chosen. Try lowering thresholds.")

    # relative light level
    chosen_light = [float(meta.get("light_eff", 0.0)) for (_, _, meta) in chosen]
    if len(chosen_light) >= 3:
        p20 = float(np.percentile(chosen_light, 20))
        p80 = float(np.percentile(chosen_light, 80))
    else:
        p20, p80 = 0.0, 1e9

    def light_level(le: float) -> str:
        if le >= p80:
            return "bright"
        if le <= p20:
            return "dim"
        return "medium"

    def light_bias(times: dict) -> str:
        if not isinstance(times, dict) or not times:
            return "unknown"
        k = max(times, key=lambda kk: float(times.get(kk, 0.0)))
        return str(k)

    # best spot reselect
    best_idx = 0
    best_val = -1e9
    for i, (s, pt, meta) in enumerate(chosen):
        wall = float(meta.get("wall", 0.0))
        stabv = float(meta.get("stab", 0.0))
        if wall < MIN_WALL_FOR_BEST:
            continue
        val = float(s) + BEST_STAB_BONUS * stabv + 0.05 * wall
        if val > best_val:
            best_val = val
            best_idx = i

    if best_idx != 0:
        chosen[0], chosen[best_idx] = chosen[best_idx], chosen[0]

    packed = []
    for idx, (s, pt, meta) in enumerate(chosen, start=1):
        le = float(meta.get("light_eff", 0.0))
        times = meta.get("times", {}) or {}
        y_norm = pt[1] / float(H)
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

    # =========================
    # PNP (ONLY ONE)
    # =========================
    pnp_result = None
    try:
        if isinstance(window_info, dict) and window_info.get("corners_4"):
            img_corners_2d = np.array(window_info["corners_4"], dtype=np.float32)  # TL,TR,BR,BL

            # 3D window rectangle model (meters) - 임시(71765 매칭 전)
            Wm = 1.8
            Hm = 1.5
            obj_corners_3d = np.array([
                [-Wm / 2, +Hm / 2, 0.0],  # TL
                [+Wm / 2, +Hm / 2, 0.0],  # TR
                [+Wm / 2, -Hm / 2, 0.0],  # BR
                [-Wm / 2, -Hm / 2, 0.0],  # BL
            ], dtype=np.float32)

            K = make_K_from_fov(Wimg, H, fov_deg=65.0)
            dist = np.zeros((4, 1), dtype=np.float32)

            rvec, tvec, R = solve_pnp_from_4pts(
                obj_corners_3d.tolist(),
                img_corners_2d.tolist(),
                K.tolist(),
                dist=dist
            )

            n = window_normal_world(R, face_axis="z")

            pnp_result = {
                "K": K.tolist(),
                "rvec": [float(x) for x in rvec.reshape(-1)],
                "tvec": [float(x) for x in tvec.reshape(-1)],
                "window_normal": [float(x) for x in n.reshape(-1)],
                "model": {"Wm": Wm, "Hm": Hm, "plane": "z=0"},
                "note": f"FOV_K + rectangle_3d_model + {window_info.get('source')}",
            }
        else:
            pnp_result = {"error": "window_info.corners_4 missing"}

    except Exception as e:
        pnp_result = {"error": str(e), "note": "solvePnP failed"}

    # =========================
    # OUT
    # =========================
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
        "window": window_info,     # ✅ 여기 1번만
        "pnp": pnp_result,         # ✅ PNP도 1번만
    }

    # =========================
    # WINDOW VIZ (FORCE SAVE)
    # =========================
    try:
        viz2 = img.copy()
        if win is not None:
            x, y, ww, hh = win
            cv2.rectangle(viz2, (int(x), int(y)), (int(x + ww), int(y + hh)), (0, 255, 255), 4)

            if isinstance(window_info, dict) and window_info.get("corners_4"):
                poly = np.array(window_info["corners_4"], dtype=np.int32).reshape(-1, 1, 2)
                cv2.polylines(viz2, [poly], True, (0, 255, 255), 3)

        viz_path2 = os.path.join(RESULT_DIR, "result_latest_viz_window.png")
        ok = cv2.imwrite(viz_path2, viz2)
        print("[VIZ_WINDOW] saved ->", viz_path2, "ok=", ok)
    except Exception as e:
        print("[WARN] VIZ_WINDOW save failed:", e)

    # =========================
    # spot_types summary
    # =========================
    type_summary = {"bright": 0, "medium": 0, "dim": 0}
    bias_summary = {"morning": 0, "noon": 0, "evening": 0, "unknown": 0}

    for s in packed:
        lp = s.get("light_profile", {})
        lvl = lp.get("level", "medium")
        bs = lp.get("bias", "unknown")
        type_summary[lvl] = int(type_summary.get(lvl, 0)) + 1
        bias_summary[bs] = int(bias_summary.get(bs, 0)) + 1

    out["spot_types"] = {"level_counts": type_summary, "bias_counts": bias_summary}

    # =========================
    # SAVE JSON
    # =========================
    if save_outputs:
        try:
            with open(RESULT_JSON_LATEST, "w", encoding="utf-8") as f:
                json.dump(to_jsonable(out), f, ensure_ascii=False, indent=2)
            print("[JSON] saved ->", RESULT_JSON_LATEST)
        except Exception as e:
            print("[WARN] json dump failed:", e)

    # =========================
    # DEBUG VIZ
    # =========================
    if debug_viz:
        try:
            best_xy = tuple((out.get("best_spot") or {}).get("pt") or (0, 0))
            draw_debug(
                image=img,
                floor_mask=(core > 0),
                windows=None,
                light_map=None,
                best_point=best_xy,
                save_path=os.path.join(RESULT_DIR, "result_latest_viz.png"),
            )
            print("[VIZ] saved ->", os.path.join(RESULT_DIR, "result_latest_viz.png"))
        except Exception as e:
            print("[WARN] draw_debug failed:", e)

    return out
