import { useEffect, useState } from "react";
import { fetchWithSession } from "../../services/session";
import { useNavigate } from "react-router-dom";
import { ROUTES } from "../../constants/routes";
import PlantSelectPage from "./PlantSelectPage";

const API_BASE = "http://localhost:8000/api/chat";
const ANALYZE_API = `${API_BASE}/analyze`; // ✅ analyze로 고정

export default function AnalyzePage() {
  const nav = useNavigate();

  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;

    const run = async () => {
      setStatus("loading");
      setError("");

      // ✅ Analyze 진입 시 "이전 결과 잔재"용 키들 싹 정리 (있으면만)
      try {
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
        await res.json(); // 응답은 받아두기만 하고 UI에 표시 안함

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
  }, []);

  // ✅ PlantSelectPage가 이미 Survey.css 레이아웃을 가지고 있으므로
  // AnalyzePage에서 surveyPage/surveyShell 같은 wrapper를 또 씌우지 말 것!
  if (status === "loading") return <p className="surveyStatus">공간 분석 중...</p>;
  if (status === "error") return <p className="surveyStatus surveyStatus--error">{error}</p>;

  return (
    <PlantSelectPage
      onPicked={() => nav(ROUTES.RENDER)}
      onRetrySurvey={() => nav(ROUTES.SURVEY)}
    />
  );
}
