import React, { useMemo, useState } from "react";

const API_BASE = "http://localhost:8000"; 

export default function Test() {
  const [file, setFile] = useState(null);
  const [isBeginner, setIsBeginner] = useState(true);
  const [pet, setPet] = useState(false);
  const [gptOn, setGptOn] = useState(false);

  const [loading, setLoading] = useState(false);
  const [resp, setResp] = useState(null);
  const [err, setErr] = useState("");

  const bestSpot = useMemo(() => resp?.pipeline?.best_spot, [resp]);
  const topPlants = useMemo(() => bestSpot?.top_plants || [], [bestSpot]);

  const vizSrc = useMemo(() => {
    if (!resp?.viz_url) return "";
    // 서버에서 이미 ?t=... 붙여줌. 그래도 추가로 캐시 깨고 싶으면 Date.now() 더해도 됨.
    return `${API_BASE}${resp.viz_url}`;
  }, [resp]);

  async function onRun() {
    setErr("");
    setResp(null);

    if (!file) {
      setErr("이미지를 먼저 업로드해줘.");
      return;
    }

    const fd = new FormData();
    fd.append("image", file);
    fd.append("is_beginner", String(isBeginner));
    fd.append("pet", String(pet));
    fd.append("gpt_on", String(gptOn));

    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/run`, {
        method: "POST",
        body: fd,
      });
      const data = await r.json();
      if (!data.ok) throw new Error("Server returned ok=false");
      setResp(data);
    } catch (e) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 980, margin: "24px auto", padding: 16 }}>
      <h2>Ditto /test</h2>

      <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="file"
            accept="image/*"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </label>

        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={isBeginner}
            onChange={(e) => setIsBeginner(e.target.checked)}
          />
          초보
        </label>

        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={pet}
            onChange={(e) => setPet(e.target.checked)}
          />
          반려동물 있음
        </label>

        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={gptOn}
            onChange={(e) => setGptOn(e.target.checked)}
          />
          GPT 판단 ON
        </label>

        <button onClick={onRun} disabled={loading} style={{ padding: "8px 14px" }}>
          {loading ? "RUNNING..." : "RUN"}
        </button>
      </div>

      {err && (
        <div style={{ marginTop: 12, color: "crimson" }}>
          {err}
        </div>
      )}

      {resp && (
        <div style={{ marginTop: 18, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
          <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
            <h3>Debug Overlay</h3>
            {vizSrc ? (
              <img
                src={vizSrc}
                alt="viz"
                style={{ width: "100%", borderRadius: 8, border: "1px solid #eee" }}
              />
            ) : (
              <div>viz_url 없음</div>
            )}
            <div style={{ marginTop: 10, fontSize: 12, color: "#555" }}>
              {resp.viz_url}
            </div>
          </div>

          <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
            <h3>Best Spot & Plants</h3>
            <div style={{ fontSize: 14 }}>
              <div><b>pt:</b> {JSON.stringify(bestSpot?.pt)}</div>
              <div><b>score:</b> {bestSpot?.score}</div>
              <div style={{ marginTop: 10 }}><b>TOP Plants</b></div>
              <ol>
                {topPlants.map((p, i) => (
                  <li key={i}>
                    {p.name} — score: {p.score?.toFixed?.(3) ?? p.score} — {p.reason}
                    {p.in_range ? " ✅" : ""}
                  </li>
                ))}
              </ol>
            </div>

            {resp.gpt && (
              <>
                <hr style={{ margin: "14px 0" }} />
                <h3>GPT Judge Result</h3>
                <div><b>summary:</b> {resp.gpt.final_recommendation?.summary}</div>
                <div style={{ marginTop: 6 }}><b>why_here:</b> {resp.gpt.final_recommendation?.why_here}</div>
                <div style={{ marginTop: 6 }}><b>care_tip:</b> {resp.gpt.final_recommendation?.care_tip}</div>
                <div style={{ marginTop: 10 }}>
                  <div><b>image_prompt</b></div>
                  <pre style={{ whiteSpace: "pre-wrap", background: "#fafafa", border: "1px solid #eee", padding: 10, borderRadius: 8 }}>
                    {resp.gpt.image_prompt}
                  </pre>
                </div>
              </>
            )}
          </div>

          <div style={{ gridColumn: "1 / -1", border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
            <h3>Raw JSON</h3>
            <pre style={{ whiteSpace: "pre-wrap", background: "#fafafa", border: "1px solid #eee", padding: 10, borderRadius: 8 }}>
              {JSON.stringify(resp, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
