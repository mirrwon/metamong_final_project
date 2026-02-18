import { useEffect, useMemo, useState } from "react";
import TimeLogSummary from "../components/timelog/TimeLogSummary";
import TimeLogFilterTabs from "../components/timelog/TimeLogFilterTabs";
import TimeLogLine from "../components/timelog/TimeLogLine";
import "./TimeLog.css";

const MOCK_PLANTS = [
  { id: "p_1", name: "금스타티라" },
  { id: "p_2", name: "스투키" },
  { id: "p_3", name: "테이블야자" },
];

const MOCK_LOGS = [
  { id: "1", plantId: "p_1", plantName: "금스타티라", type: "water", date: "2026-01-25", time: "09:10", title: "물 줌", detail: "" },
  { id: "2", plantId: "p_1", plantName: "금스타티라", type: "move", date: "2026-01-25", time: "13:40", title: "위치 이동", detail: "거실 → 베란다" },
  { id: "3", plantId: "p_1", plantName: "금스타티라", type: "note", date: "2026-01-25", time: "20:05", title: "특이사항", detail: "잎 끝이 갈변했어요." },
  { id: "4", plantId: "p_2", plantName: "스투키", type: "fertilizer", date: "2026-01-23", time: "10:30", title: "비료 줌", detail: "" },
  {
    id: "5",
    plantId: "p_2",
    plantName: "스투키",
    type: "photo",
    date: "2026-01-23",
    time: "21:00",
    title: "배치 사진 저장",
    detail: "거실 배치 기록",
    imageUrl:
      "https://images.unsplash.com/photo-1505693314120-0d443867891c?auto=format&fit=crop&w=900&q=60",
  },
  { id: "6", plantId: "p_3", plantName: "테이블야자", type: "new", date: "2026-01-18", time: "15:10", title: "새 식물 추가", detail: "" },
];

export default function TimeLogPage() {
  const [activeTab, setActiveTab] = useState("all");
  const [activePlantId, setActivePlantId] = useState("");
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    setLogs(MOCK_LOGS);
  }, []);

  const activePlant = useMemo(() => {
    return MOCK_PLANTS.find((p) => p.id === activePlantId) || null;
  }, [activePlantId]);

  const isPlantSelected = Boolean(activePlantId);

  const addDiaryLog = (type) => {
    if (!activePlant) return;

    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const dd = String(now.getDate()).padStart(2, "0");
    const hh = String(now.getHours()).padStart(2, "0");
    const min = String(now.getMinutes()).padStart(2, "0");

    const date = `${yyyy}-${mm}-${dd}`;
    const time = `${hh}:${min}`;

    const newItem = buildLocalLog({
      type,
      date,
      time,
      plant: activePlant,
    });

    setLogs((prev) => [newItem, ...prev]);
  };

  const filteredLogs = useMemo(() => {
    let base = logs;

    if (activePlantId) base = base.filter((log) => log.plantId === activePlantId);
    if (activeTab === "all") return base;

    return base.filter((log) => log.type === activeTab);
  }, [activeTab, logs, activePlantId]);

  const counts = useMemo(() => {
    const base = { all: 0, water: 0, fertilizer: 0, move: 0, note: 0, photo: 0, new: 0 };
    const target = activePlantId ? logs.filter((l) => l.plantId === activePlantId) : logs;

    base.all = target.length;
    target.forEach((log) => {
      if (base[log.type] !== undefined) base[log.type] += 1;
    });

    return base;
  }, [logs, activePlantId]);

  const groups = useMemo(() => {
    const map = new Map();

    filteredLogs.forEach((log) => {
      const dateKey = (log.date || "").trim();
      if (!dateKey) return;

      if (!map.has(dateKey)) map.set(dateKey, []);
      map.get(dateKey).push(log);
    });

    const sortedDates = Array.from(map.keys()).sort((a, b) => (a < b ? 1 : -1));

    return sortedDates.map((date) => {
      const items = map
        .get(date)
        .slice()
        .sort((a, b) => (a.time > b.time ? 1 : -1));

      return { date, items };
    });
  }, [filteredLogs]);

  return (
    <div className="timelog">
      <div className="timelog__header">
        <h1 className="timelog__title">나의 타임로그 🌿</h1>
      </div>

      <div className="timelog-plant">
        <label className="timelog-plant__label">식물 선택</label>
        <select
          className="timelog-plant__select"
          value={activePlantId}
          onChange={(e) => setActivePlantId(e.target.value)}
        >
          <option value="">식물을 선택하세요</option>
          {MOCK_PLANTS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      <TimeLogSummary counts={counts} />
      <TimeLogFilterTabs activeTab={activeTab} counts={counts} onChangeTab={setActiveTab} />

      <div className="timelog__sectionTitle">오늘의 타임라인</div>
      <TimeLogLine groups={groups} />

      <div className="timelog-actions">
        <div className="timelog-actions__row">
          <button type="button" className="timelog-actionBtn" onClick={() => addDiaryLog("water")} disabled={!isPlantSelected}>
            💧 물 줬어요
          </button>
          <button type="button" className="timelog-actionBtn" onClick={() => addDiaryLog("fertilizer")} disabled={!isPlantSelected}>
            🧪 비료 줬어요
          </button>
          <button type="button" className="timelog-actionBtn" onClick={() => addDiaryLog("move")} disabled={!isPlantSelected}>
            🪴 위치 옮겼어요
          </button>
          <button type="button" className="timelog-actionBtn" onClick={() => addDiaryLog("note")} disabled={!isPlantSelected}>
            📝 특이사항
          </button>
          <button type="button" className="timelog-actionBtn" onClick={() => addDiaryLog("photo")} disabled={!isPlantSelected}>
            🖼️ 사진 저장
          </button>
        </div>
      </div>
    </div>
  );
}
