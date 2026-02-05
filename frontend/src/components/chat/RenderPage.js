import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchWithSession } from "../../services/session";
import { ROUTES } from "../../constants/routes";
import Button from "../common/Button";
import "./Survey.css"; // 기존 Survey 스타일 재사용 (원하면 별도 css로 분리)

const API_ORIGIN = "http://localhost:8000";
const RENDER_API = `${API_ORIGIN}/api/chat/render`;

const SELECTED_PLANT_KEY = "selected_plant";

const resolveImageUrl = (url) => {
  if (!url) return null;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  if (url.startsWith("/")) return `${API_ORIGIN}${url}`;
  return url;
};

const pickAiEditUrlFromResponse = (data) => {
  // 1) messages[].images[] 형태
  const msgs = Array.isArray(data?.messages) ? data.messages : [];
  for (const m of msgs) {
    const imgs = Array.isArray(m?.images) ? m.images : [];
    for (const img of imgs) {
      const name = String(img?.name || "");
      const url = String(img?.url || "");
      if (!url) continue;
      if (name === "ai_edit" || name.includes("ai_edit") || url.includes("ai_edit")) {
        return resolveImageUrl(url);
      }
    }
  }

  // 2) 혹시 data.images 로 바로 오는 케이스
  const imgs2 = Array.isArray(data?.images) ? data.images : [];
  for (const img of imgs2) {
    const name = String(img?.name || "");
    const url = String(img?.url || "");
    if (!url) continue;
    if (name === "ai_edit" || name.includes("ai_edit") || url.includes("ai_edit")) {
      return resolveImageUrl(url);
    }
  }

  return null;
};

export default function RenderPage() {
  const nav = useNavigate();

  const [selectedPlant, setSelectedPlant] = useState(null);

  const [regen, setRegen] = useState(false);
  const [spotIndex, setSpotIndex] = useState(0);

  const [status, setStatus] = useState("idle"); // idle | loading | ready | error
  const [error, setError] = useState("");
  const [aiEditUrl, setAiEditUrl] = useState(null);

  const [rawResponse, setRawResponse] = useState(null);

  useEffect(() => {
    // 선택한 식물 불러오기
    const raw = sessionStorage.getItem(SELECTED_PLANT_KEY);
    if (!raw) {
      setError("선택한 식물 정보가 없습니다. (selected_plant 없음) 3페이지에서 식물을 먼저 선택해주세요.");
      setStatus("error");
      return;
    }

    try {
      const parsed = JSON.parse(raw);
      setSelectedPlant(parsed);
      setStatus("idle");
    } catch (e) {
      setError("selected_plant를 읽을 수 없습니다. sessionStorage 값이 깨졌습니다.");
      setStatus("error");
    }
  }, []);

  const plantName = useMemo(() => {
    // 백엔드에서 받을 이름 기준: name
    const n = selectedPlant?.name || selectedPlant?.displayName || selectedPlant?.name_ko || selectedPlant?.name_en;
    return String(n || "").trim();
  }, [selectedPlant]);

  const plantImage = useMemo(() => resolveImageUrl(selectedPlant?.image), [selectedPlant]);

  const callRender = async (idx) => {
    if (!plantName) {
      setError("선택된 식물 이름이 없습니다. selected_plant 저장 구조를 확인하세요.");
      setStatus("error");
      return;
    }

    setSpotIndex(idx);
    setStatus("loading");
    setError("");
    setAiEditUrl(null);

    const payload = {
      spot_index: idx,
      plant_name: plantName,
      regen: !!regen,
    };

    try {
      const res = await fetchWithSession(RENDER_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const text = await res.text();
      let data = null;
      try {
        data = JSON.parse(text);
      } catch {
        data = { _raw: text };
      }

      setRawResponse(data);

      if (!res.ok) {
        setError(`render 실패: HTTP ${res.status}`);
        setStatus("error");
        return;
      }

      const url = pickAiEditUrlFromResponse(data);
      if (!url) {
        setError("응답은 받았지만 ai_edit 이미지 URL을 찾지 못했습니다. (messages/images 구조 확인 필요)");
        setStatus("error");
        return;
      }

      setAiEditUrl(url);
      setStatus("ready");
    } catch (e) {
      setError("render 요청 중 네트워크/서버 오류가 발생했습니다.");
      setStatus("error");
    }
  };

  const goBack = () => {
    // 너 라우트 구조에 맞게 수정 가능
    // 보통 3페이지(ANALYZE)로 되돌아감
    nav(ROUTES.ANALYZE);
  };

  return (
    <div className="surveyPage">
      <div className="surveyShell">
        <div className="surveyCard">
          <header className="surveyHeader">
            <h2 className="surveyTitle">4페이지 - 렌더</h2>
            <p className="surveyDesc">선택한 식물을 후보 위치(spot)에 합성합니다.</p>
          </header>

          {selectedPlant && (
            <div style={{ display: "flex", gap: 16, alignItems: "center", marginBottom: 12 }}>
              <div style={{ width: 120, height: 120, borderRadius: 12, overflow: "hidden", background: "#eee" }}>
                {plantImage ? (
                  <img src={plantImage} alt={plantName} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                ) : (
                  <div style={{ padding: 12, fontSize: 12, opacity: 0.8 }}>식물 이미지 없음</div>
                )}
              </div>

              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>{plantName || "식물"}</div>

                <label style={{ display: "flex", gap: 8, alignItems: "center", userSelect: "none" }}>
                  <input
                    type="checkbox"
                    checked={regen}
                    onChange={(e) => setRegen(e.target.checked)}
                  />
                  같은 spot 다시 누르면 이미지 재생성(regen)
                </label>

                <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                  <Button type="option" onClick={() => callRender(0)} text="spot 1" />
                  <Button type="option" onClick={() => callRender(1)} text="spot 2" />
                  <Button type="option" onClick={() => callRender(2)} text="spot 3" />
                  <Button type="primary" onClick={goBack} text="3페이지로 돌아가기" />
                </div>
              </div>
            </div>
          )}

          {status === "loading" && <p className="surveyStatus">렌더링 중...</p>}
          {status === "error" && <p className="surveyStatus surveyStatus--error">{error}</p>}

          {aiEditUrl && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>
                결과 (spot #{spotIndex + 1})
              </div>
              <div style={{ borderRadius: 12, overflow: "hidden", background: "#111" }}>
                <img
                  src={aiEditUrl}
                  alt="ai_edit"
                  style={{ width: "100%", display: "block" }}
                  onError={() => {
                    setError("ai_edit 이미지 로드 실패. URL 또는 서버 static 라우팅(results) 확인 필요");
                    setStatus("error");
                  }}
                />
              </div>
              <div style={{ marginTop: 8, fontSize: 12, opacity: 0.85, wordBreak: "break-all" }}>
                {aiEditUrl}
              </div>
            </div>
          )}

          {/* 디버깅: raw 응답 */}
          {rawResponse && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>DEBUG: render 응답(raw)</div>
              <pre style={{ fontSize: 12, background: "#f4f4f4", padding: 12, borderRadius: 8, overflow: "auto" }}>
                {JSON.stringify(rawResponse, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
