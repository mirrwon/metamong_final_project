import { useEffect, useState } from "react";
import { fetchWithSession } from "../../services/session";
import { useNavigate } from "react-router-dom";
import { ROUTES } from "../../constants/routes";
import PlantSelectPage from "./PlantSelectPage";

const API_BASE = "http://localhost:8000/api/chat";
const ANALYZE_API = `${API_BASE}/analyze`;

export default function AnalyzePage() {
  const nav = useNavigate();

  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;

    const run = async () => {
      setStatus("loading");
      setError("");

      // ✅ Analyze 진입 시 "이전 결과 잔재" 정리
      try {
        sessionStorage.removeItem("selected_plant"); // 렌더에서 쓰는 키도 초기화(원하면 유지해도 됨)
        sessionStorage.removeItem("ai_edit_url");
        sessionStorage.removeItem("render_result");
        sessionStorage.removeItem("last_render");
      } catch (e) {}

      try {
        const meta = {
          lat: 37.5665,
          lot: 126.978,
          hhmm: new Date().toTimeString().slice(0, 5).replace(":", ""),
        };

        const res = await fetchWithSession(ANALYZE_API, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ meta, filters: {} }),
        });

        if (!res.ok) throw new Error("analyze_failed");
        await res.json(); // 응답은 받기만 하고 화면에 출력 안함

        if (!alive) return;
        setStatus("done");
      } catch (e) {
        if (!alive) return;
        setStatus("error");
        setError("Failed to analyze space.");
      }
    };

    run();
    return () => {
      alive = false;
    };
  }, []); // ✅ selectedPlant 의존성 제거

  if (status === "loading") return <p className="surveyStatus">공간 분석 중...</p>;
  if (status === "error") return <p className="surveyStatus surveyStatus--error">{error}</p>;

  return (
    <PlantSelectPage
      onPicked={() => nav(ROUTES.RENDER)}
      onRetrySurvey={() => nav(ROUTES.SURVEY)}
    />
  );
}
