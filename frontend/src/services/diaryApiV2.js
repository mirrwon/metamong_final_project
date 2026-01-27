import { useEffect, useMemo, useState } from "react";
import DiarySummary from "../components/diaryV2/DiarySummary";
import DiaryFilterTabs from "../components/diaryV2/DiaryFilterTabs";
import DiaryTimeline from "../components/diaryV2/DiaryTimeline";
import "./DiaryV2.css";

/** ✅ 더미 식물(백 붙이면 여기만 fetch로 바꾸면 됨) */
const MOCK_PLANTS = [
  { id: "p_1", name: "금스타티라" },
  { id: "p_2", name: "스투키" },
  { id: "p_3", name: "테이블야자" },
];

/** ✅ 더미 로그(백 붙이면 서버 데이터로 교체) */
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

export default function DiaryV2() {
  const [activeTab, setActiveTab] = useState("all");

  /** ✅ (중요) 선택된 식물 */
  const [activePlantId, setActivePlantId] = useState("");

  /** ✅ 백 없이: 로컬 로그 상태 */
  const [logs, setLogs] = useState([]);

  /** ✅ 처음 들어오면 더미 로그 세팅 */
  useEffect(() => {
    setLogs(MOCK_LOGS);
  }, []);

  /** ✅ 선택된 식물 객체 */
  const activePlant = useMemo(() => {
    return MOCK_PLANTS.find((p) => p.id === activePlantId) || null;
  }, [activePlantId]);

  /** ✅ 식물 선택 전엔 버튼 비활성 */
  const isPlantSelected = Boolean(activePlantId);

  /** ✅ 액션바: 로컬에 로그 추가(= 나중에 API로 교체할 자리) */
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

    // ✅ 최신이 위로 오게 앞에 추가
    setLogs((prev) => [newItem, ...prev]);
  };

  /** ✅ 탭 + 식물 필터(선택 식물이 있으면 그 식물 로그만 보여주게) */
  const filteredLogs = useMemo(() => {
    let base = logs;

    // (1) 식물 선택 필터
    if (activePlantId) base = base.filter((log) => log.plantId === activePlantId);

    // (2) 탭 필터
    if (activeTab === "all") return base;
    return base.filter((log) => log.type === activeTab);
  }, [activeTab, logs, activePlantId]);

  /** ✅ counts (현재 선택 식물 기준으로 요약 보여주는 게 더 자연스러움) */
  const counts = useMemo(() => {
    const base = { all: 0, water: 0, fertilizer: 0, move: 0, note: 0, photo: 0, new: 0 };

    const target = activePlantId ? logs.filter((l) => l.plantId === activePlantId) : logs;

    base.all = target.length;
    target.forEach((log) => {
      if (base[log.type] !== undefined) base[log.type] += 1;
    });

    return base;
  }, [logs, activePlantId]);

  /** ✅ 날짜 그룹핑 */
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
    <div className="diaryV2">
      <div className="diaryV2__header">
        <h1 className="diaryV2__title">나의 다이어리 🌿</h1>
      </div>

      {/* ✅ 식물 선택(필수) */}
      <div className="dv2-plant">
        <label className="dv2-plant__label">식물 선택</label>
        <select
          className="dv2-plant__select"
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

      <DiarySummary counts={counts} />

      <DiaryFilterTabs activeTab={activeTab} counts={counts} onChangeTab={setActiveTab} />

      <div className="diaryV2__sectionTitle">오늘의 타임라인</div>
      <DiaryTimeline groups={groups} />

      {/* ✅ 하단 액션바(프론트만: 로컬 추가) */}
      <div className="dv2-actions">
        <div className="dv2-actions__row">
          <button type="button" className="dv2-actionBtn" onClick={() => addDiaryLog("water")} disabled={!isPlantSelected}>
            💧 물 줬어요
          </button>
          <button type="button" className="dv2-actionBtn" onClick={() => addDiaryLog("fertilizer")} disabled={!isPlantSelected}>
            🧪 비료 줬어요
          </button>
          <button type="button" className="dv2-actionBtn" onClick={() => addDiaryLog("move")} disabled={!isPlantSelected}>
            🪴 위치 옮겼어요
          </button>
          <button type="button" className="dv2-actionBtn" onClick={() => addDiaryLog("note")} disabled={!isPlantSelected}>
            📝 특이사항
          </button>
          <button type="button" className="dv2-actionBtn" onClick={() => addDiaryLog("photo")} disabled={!isPlantSelected}>
            🖼️ 사진 저장
          </button>
        </div>
      </div>
    </div>
  );
}

/** ✅ type별 UI 텍스트 만들기 */
function buildLocalLog({ type, date, time, plant }) {
  const base = {
    id: `tmp_${Date.now()}`,
    type,
    date,
    time,
    plantId: plant.id,
    plantName: plant.name,
    title: "",
    detail: "",
  };

  switch (type) {
    case "water":
      return { ...base, title: "물 줌", detail: plant.name };
    case "fertilizer":
      return { ...base, title: "비료 줌", detail: plant.name };
    case "move":
      return { ...base, title: "위치 이동", detail: "거실 → 베란다" }; // 나중에 입력받기
    case "note":
      return { ...base, title: "특이사항", detail: "메모를 추가해보세요." }; // 나중에 입력받기
    case "photo":
      return {
        ...base,
        title: "배치 사진 저장",
        detail: "사진은 나중에 업로드로 연결",
        imageUrl:
          "https://images.unsplash.com/photo-1505693314120-0d443867891c?auto=format&fit=crop&w=900&q=60",
      };
    case "new":
      return { ...base, title: "새 식물 추가", detail: plant.name };
    default:
      return { ...base, title: "기록", detail: "" };
  }
}
