import { useEffect, useState } from "react";
import { fetchWithSession } from "../../services/session";

const API_BASE = "http://localhost:8000/api/chat";
const RENDER_API = `${API_BASE}/render`;
const RESULT_BASE = "http://localhost:8000";

export default function RenderPage() {
  const [loading, setLoading] = useState(true);
  const [spotImages, setSpotImages] = useState([]); // [{spot_index, url}]
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;

    (async () => {
      try {
        setLoading(true);
        setError(null);

        // =========================================================
        // 1) 최신 분석 결과에서 spots 3개 가져오기
        // =========================================================
        const latestRes = await fetchWithSession(
          `${RESULT_BASE}/results/result_latest.json?t=${Date.now()}`,
          { method: "GET" }
        );
        if (!latestRes.ok) throw new Error("failed_to_load_result_latest");

        const latest = await latestRes.json();
        const spots = Array.isArray(latest?.spots) ? latest.spots : [];
        if (spots.length < 3) throw new Error("spots<3");

        // spots: result_latest.json의 latest.spots
        // render_plan: 백엔드(analyze)에서 넣어준 정책 { count, spot_indexes }
        const plan = latest?.render_plan;

        // 1) 기본은 기존처럼 3개
        let spotIndexes = spots.slice(0, 3).map((s, i) => {
          const v = s?.spot_index ?? s?.index ?? i;
          const n = Number(v);
          return Number.isFinite(n) ? n : i;
        });

        // 2) 테이블/바닥 정책이 있으면 plan 우선 적용
        if (plan?.count === 1 && Array.isArray(plan?.spot_indexes) && plan.spot_indexes.length >= 1) {
          const n = Number(plan.spot_indexes[0]);
          spotIndexes = [Number.isFinite(n) ? n : 0];
        }

        if (plan?.count === 3 && Array.isArray(plan?.spot_indexes) && plan.spot_indexes.length >= 3) {
          spotIndexes = plan.spot_indexes.slice(0, 3).map((v, i) => {
            const n = Number(v);
            return Number.isFinite(n) ? n : i;
          });
        }


        // =========================================================
        // 2) 선택한 식물 고정 (sessionStorage.selected_plant)
        //    너 스샷 기준: { id:"136", name:"...", image:"https://..." }
        // =========================================================
        const plantRaw = sessionStorage.getItem("selected_plant");
        if (!plantRaw) throw new Error("missing selected_plant");

        const plant = JSON.parse(plantRaw);
        const plant_id = plant?.id;
        if (!plant_id) throw new Error("missing plant_id");

        // sid는 있으면 같이 보내고, 없으면 생략
        const sid = localStorage.getItem("sid");

        console.log("render payload", { plant_id, plant_name: plant?.name, plant_image_url: plant?.image });

        // =========================================================
        // 3) render 3번 호출 (같은 plant_id + spot_index만 다르게)
        // =========================================================
        const imgs = await Promise.all(
          spotIndexes.map(async (spot_index) => {
            const r = await fetchWithSession(RENDER_API, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                ...(sid ? { sid } : {}),
                spot_index,
                plant_id,
                plant_image_url: plant?.image,
                plant_name: plant?.name,
                regen: true,   
                // mode: "gemini",
                // mode: "composite",
                mode: "ai_edit",
              }),
            });

            // render 응답이 에러일 때도 json일 수 있으니 읽고 체크
            const j = await r.json().catch(() => null);
            if (!r.ok) {
              const msg = j?.detail || j?.message || "render_failed";
              throw new Error(`${msg} (spot_index=${spot_index})`);
            }

            // 응답 구조 여러 형태 대응 (composite / ai_edit 둘 다 안전)
            const imagesMsg = j?.messages?.find((m) => m?.type === "images");
            const imagesArr = Array.isArray(imagesMsg?.images) ? imagesMsg.images : [];

            // 우선순위: ai_edit -> composite -> marker -> 첫번째
            const picked =
              imagesArr.find((it) => it?.name === "ai_edit") ||
              imagesArr.find((it) => it?.name === "composite") ||
              imagesArr.find((it) => it?.name === "marker") ||
              imagesArr[0];

            const rawUrl =
              picked?.url ||
              j?.image_url ||
              j?.url ||
              j?.result?.url;

            if (!rawUrl) {
              console.log("render response json =", j);
              throw new Error(`missing image_url for spot ${spot_index}`);
            }

            const url = rawUrl.startsWith("http") ? rawUrl : `${RESULT_BASE}${rawUrl}`;
            return { spot_index, url };
          })
        );

        if (!mounted) return;
        setSpotImages(imgs);
      } catch (e) {
        if (!mounted) return;
        setError(String(e?.message || e));
      } finally {
        if (!mounted) return;
        setLoading(false);
      }
    })();

    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="render-page">
      <h2>AI 추천 스팟 3개</h2>

      {loading && <div>이미지 생성 중...</div>}
      {error && <div style={{ color: "red" }}>{error}</div>}

      {!loading && !error && (
        <div className="spot-grid">
          {spotImages.map((it) => (
            <div className="spot-card" key={it.spot_index}>
              <div className="spot-title">Spot #{it.spot_index + 1}</div>
              <img
                src={it.url}
                alt={`spot-${it.spot_index}`}
                style={{ width: "100%", borderRadius: 12 }}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
