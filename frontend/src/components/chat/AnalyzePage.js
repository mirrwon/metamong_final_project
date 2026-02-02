import { useEffect, useState } from "react";
import { fetchWithSession } from "../../services/session";
import "./Survey.css";

const API_BASE = "http://localhost:8000/api/chat";
const ANALYZE_API = `${API_BASE}/analyze`;
const API_ORIGIN = "http://localhost:8000";
<<<<<<< HEAD
=======
const SELECTED_PLANT_KEY = "selected_plant";
>>>>>>> f0a1531 (chat plant 2026-02-02)

const resolveImageUrl = (url) => {
  if (!url) return null;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  if (url.startsWith("/")) return `${API_ORIGIN}${url}`;
  return url;
};

export default function AnalyzePage() {
  const [status, setStatus] = useState("idle"); // idle|loading|done|error
  const [error, setError] = useState("");
  const [images, setImages] = useState([]);
<<<<<<< HEAD
=======
  const [selectedPlant, setSelectedPlant] = useState(null);

  useEffect(() => {
    const raw = sessionStorage.getItem(SELECTED_PLANT_KEY);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw);
      setSelectedPlant(parsed);
    } catch (e) {
      // ignore parse errors
    }
  }, []);
>>>>>>> f0a1531 (chat plant 2026-02-02)

  useEffect(() => {
    let alive = true;

    const run = async () => {
      setStatus("loading");
      setError("");
      setImages([]);

      try {
        // ✅ 지금은 목데이터(filters 비워도 백엔드가 동작하도록 설계돼있음)
<<<<<<< HEAD
        const res = await fetchWithSession(ANALYZE_API, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filters: {} }),
=======
        const filters = selectedPlant ? { selectedPlant } : {};
        const res = await fetchWithSession(ANALYZE_API, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filters }),
>>>>>>> f0a1531 (chat plant 2026-02-02)
        });

        if (!res.ok) throw new Error("analyze_failed");
        const data = await res.json();

        const imgs = Array.isArray(data?.images) ? data.images : [];
        const normalized = imgs
          .map((x) => ({
            name: x?.name || "image",
            url: resolveImageUrl(x?.url),
          }))
          .filter((x) => x.url);

        if (!alive) return;
        setImages(normalized);
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

  return (
    <div className="surveyPage">
      <div className="surveyShell">
        <div className="surveyCard">
          <header className="surveyHeader">
            <h2 className="surveyTitle">공간 분석</h2>
            <p className="surveyDesc">분석 결과 및 Gemini 이미지 생성 결과를 표시합니다.</p>
          </header>

<<<<<<< HEAD
=======
          {selectedPlant?.name && (
            <p className="surveyStatus">선택한 식물: {selectedPlant.name}</p>
          )}
>>>>>>> f0a1531 (chat plant 2026-02-02)
          {status === "loading" && <p className="surveyStatus">공간 분석 중...</p>}
          {error && <p className="surveyStatus surveyStatus--error">{error}</p>}

          {images.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <h3 className="surveyGroup__title">결과 이미지</h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 12, marginTop: 8 }}>
                {images.map((img) => (
                  <div key={img.url}>
                    <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>{img.name}</div>
                    <img src={img.url} alt={img.name} style={{ width: "100%", borderRadius: 8 }} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {status === "done" && images.length === 0 && (
            <p className="surveyStatus surveyStatus--error">
              analyze는 성공했는데 images가 비어있음. 백엔드 응답(images 배열) 확인 필요.
            </p>
          )}
        </div>
      </div>
    </div>
  );
<<<<<<< HEAD
}
=======
}
>>>>>>> f0a1531 (chat plant 2026-02-02)
