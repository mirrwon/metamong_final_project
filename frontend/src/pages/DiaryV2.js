// src/pages/DiaryV2.js (혹은 네 프로젝트 경로에 맞게)
// ✅ 너가 분리해둔 파일들(Join*.)에 맞춰서 DiaryV2 최종 정리본

import { useEffect, useMemo, useState } from "react";

import JoinDiarySummary from "../components/diaryV2/JoinDiarySummary";
import JoinDiaryFilterTabs from "../components/diaryV2/JoinDiaryFilterTabs";
import JoinDiaryTimeline from "../components/diaryV2/JoinDiaryTimeline";

import { JoinDiaryStorage } from "../components/diaryV2/JoinDiaryStorage";
import { readPendingDiaryPhoto, clearPendingDiaryPhoto } from "../components/diaryV2/JoinDiaryPending";
import { JoinFileToDataUrl } from "../components/diaryV2/JoinFileToDataUrl";

import "./DiaryV2.css";

/** =========================
 *  MOCK (백 붙이면 여기만 교체)
 *  ========================= */
const MOCK_PLANTS = [
  { id: "p_1", name: "금스타티라", coverUrl: "" },
  { id: "p_2", name: "스투키", coverUrl: "" },
  { id: "p_3", name: "테이블야자", coverUrl: "" },
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
    imageUrl: "https://images.unsplash.com/photo-1505693314120-0d443867891c?auto=format&fit=crop&w=900&q=60",
  },
  { id: "6", plantId: "p_3", plantName: "테이블야자", type: "new", date: "2026-01-18", time: "15:10", title: "새 식물 추가", detail: "" },
];

export default function DiaryV2() {
  /** 탭 */
  const [activeTab, setActiveTab] = useState("all");

  /** ✅ plants/logs: localStorage 저장/복원은 훅에서 처리 */
  const { plants, setPlants, logs, setLogs } = JoinDiaryStorage({
    plantsKey: "plants_v2",
    logsKey: "logs_v2",
    initialPlants: MOCK_PLANTS,
    initialLogs: MOCK_LOGS,
  });
  
  const [activePlantId, setActivePlantId] = useState("");


  const [isAddPlantOpen, setIsAddPlantOpen] = useState(false);
  const [newPlantName, setNewPlantName] = useState("");
  const [newPlantFile, setNewPlantFile] = useState(null);

 
  const activePlant = useMemo(() => {
    return plants.find((p) => p.id === activePlantId) || null;
  }, [plants, activePlantId]);


  const isPlantSelected = Boolean(activePlantId);


  const showPlantTag = !activePlantId;


  useEffect(() => {
    const applyPending = async () => {
      const pending = readPendingDiaryPhoto();
      if (!pending?.plantName || !pending?.imageUrl) return;

      clearPendingDiaryPhoto();

      // 1) plantName으로 식물 찾기, 없으면 자동 생성
      const exist = findPlantByName(plants, pending.plantName);
      const plant = exist || createPlantLocal(setPlants, pending.plantName, pending.imageUrl);

      // 2) 해당 식물 자동 선택
      setActivePlantId(plant.id);

      // 3) photo 로그 자동 추가
      const now = buildNow();
      const newLog = {
        id: `tmp_${Date.now()}`,
        type: "photo",
        date: now.date,
        time: now.time,
        plantId: plant.id,
        plantName: plant.name,
        title: "배치 사진 저장",
        detail: "챗봇 최종 선택 이미지",
        imageUrl: pending.imageUrl,
        meta: { resultId: pending.resultId || null },
      };

      setLogs((prev) => [
        {
          id: `tmp_${Date.now()}`,
          type: "new",
          date: now.date,
          time: now.time,
          plantId: id,
          plantName: name,     
          title: "새 식물 추가",    
          detail: "새 식물을 등록했어요.", 
          imageUrl: coverUrl,    
        },
        ...prev,
      ]);
    };

    applyPending();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  //수동 새 식물 추가 
  const addPlantManually = async () => {
    const name = (newPlantName || "").trim();
    if (!name) return alert("식물 이름을 입력하세요.");
    if (!newPlantFile) return alert("대표 사진을 선택하세요.");

    const exist = findPlantByName(plants, name);
    if (exist) return alert("같은 이름의 식물이 이미 있어요.");

    let coverUrl = "";
    try {
      coverUrl = await JoinFileToDataUrl(newPlantFile);
    } catch {
      return alert("이미지 처리에 실패했어요. 다른 파일로 다시 시도해 주세요.");
    }

    const id = `p_${Date.now()}`;
    const newPlant = { id, name, coverUrl, createdBy: "manual" };

    setPlants((prev) => [newPlant, ...prev]);
    setActivePlantId(id);

    // 모달 닫고 초기화
    setIsAddPlantOpen(false);
    setNewPlantName("");
    setNewPlantFile(null);

    // 새 식물 등록 로그
    const now = buildNow();
    setLogs((prev) => [
      {
        id: `tmp_${Date.now()}`,
        type: "new",
        date: now.date,
        time: now.time,
        plantId: id,
        plantName: name,
        title: "새 식물 등록",
        detail: "수동으로 추가한 식물",
        imageUrl: coverUrl,
      },
      ...prev,
    ]);
  };

  /** =========================
   *  하단 액션: 로컬 로그 추가
   *  ========================= */
  const addDiaryLog = (type) => {
    if (!activePlant) return;

    // note
    if (type === "note") {
      const memo = window.prompt("특이사항 메모를 입력하세요");
      if (!memo || !memo.trim()) return;

      const now = buildNow();
      const newItem = buildLocalLog({
        type,
        date: now.date,
        time: now.time,
        plant: activePlant,
        detailOverride: memo.trim(),
      });

      setLogs((prev) => [newItem, ...prev]);
      return;
    }

    // photo는 업로드 핸들러에서 처리
    if (type === "photo") return;

    const now = buildNow();
    const newItem = buildLocalLog({
      type,
      date: now.date,
      time: now.time,
      plant: activePlant,
    });

    setLogs((prev) => [newItem, ...prev]);
  };

  /** =========================
   *  사진 업로드 로그 추가 (✅ 새로고침 유지)
   *  ========================= */
  const handleUploadPhoto = async (e) => {
    if (!activePlant) return;

    const file = e.target.files?.[0];
    if (!file) return;

    e.target.value = "";

    let imageUrl = "";
    try {
      imageUrl = await JoinFileToDataUrl(file);
    } catch {
      return alert("이미지 업로드에 실패했어요. 다른 파일로 다시 시도해 주세요.");
    }

    const now = buildNow();
    const newLog = {
      id: `tmp_${Date.now()}`,
      type: "photo",
      date: now.date,
      time: now.time,
      plantId: activePlant.id,
      plantName: activePlant.name,
      title: "배치 사진 저장",
      detail: "직접 업로드한 사진",
      imageUrl,
      meta: {
        source: "upload",
        filename: file.name,
        size: file.size,
        mime: file.type,
      },
    };

    setLogs((prev) => [newLog, ...prev]);
  };

  /** =========================
   *  필터링/요약/그룹핑
   *  ========================= */
  const filteredLogs = useMemo(() => {
    let base = logs;

    // (1) 식물 선택 필터
    if (activePlantId) base = base.filter((log) => log.plantId === activePlantId);

    // (2) 탭 필터
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

  /** 삭제 */
  const deleteDiaryLog = (logId) => {
    setLogs((prev) => prev.filter((log) => log.id !== logId));
  };

  /** =========================
   *  Render
   *  ========================= */
  return (
    <div className="diaryV2">
      <div className="diaryV2__header">
        <h1 className="diaryV2__title">나의 다이어리 🌿</h1>
      </div>

      {/* ✅ 식물 선택 */}
      <div className="dv2-plant">
        <label className="dv2-plant__label">식물 선택</label>
        <select
          className="dv2-plant__select"
          value={activePlantId}
          onChange={(e) => setActivePlantId(e.target.value)}
        >
          <option value="">식물을 선택하세요</option>
          {plants.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      <div className="dv2-summaryRow">
        <JoinDiarySummary counts={counts} />
        <div className="dv2-topActions">
          <button type="button" className="dv2-addPlantBtn" onClick={() => setIsAddPlantOpen(true)}>
            + 새 식물 추가
          </button>
        </div>
      </div>

      {isAddPlantOpen && (
        <div className="dv2-modal" onClick={() => setIsAddPlantOpen(false)}>
          <div className="dv2-modal__panel" onClick={(e) => e.stopPropagation()}>
            <div className="dv2-modal__title">새 식물 추가</div>

            <label className="dv2-modal__label">식물 이름</label>
            <input
              className="dv2-modal__input"
              value={newPlantName}
              onChange={(e) => setNewPlantName(e.target.value)}
              placeholder="예) 몬스테라"
            />

            <label className="dv2-modal__label">대표 사진</label>
            <input
              className="dv2-modal__file"
              type="file"
              accept="image/*"
              onChange={(e) => setNewPlantFile(e.target.files?.[0] || null)}
            />

            <div className="dv2-modal__actions">
              <button type="button" className="dv2-modal__btn" onClick={() => setIsAddPlantOpen(false)}>
                취소
              </button>
              <button type="button" className="dv2-modal__btn dv2-modal__btn--primary" onClick={addPlantManually}>
                등록
              </button>
            </div>
          </div>
        </div>
      )}

      <JoinDiaryFilterTabs activeTab={activeTab} counts={counts} onChangeTab={setActiveTab} />

      <div className="diaryV2__sectionTitle">오늘의 타임라인</div>
      <JoinDiaryTimeline groups={groups} onDelete={deleteDiaryLog} showPlantTag={showPlantTag} />

      {/* ✅ 하단 액션바 */}
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

          <button type="button" className="dv2-actionBtn dv2-actionBtn--file" disabled={!isPlantSelected}>
            🖼️ 사진추가
            <input
              className="dv2-fileInput"
              type="file"
              accept="image/*"
              onChange={handleUploadPhoto}
              disabled={!isPlantSelected}
            />
          </button>
        </div>
      </div>
    </div>
  );
}


function buildLocalLog({ type, date, time, plant, detailOverride }) {
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
      return { ...base, title: "위치 이동", detail: "거실 → 베란다" };
    case "note":
      return { ...base, title: "특이사항", detail: detailOverride || "" };
    case "new":
      return { ...base, title: "새 식물 추가", detail: plant.name };
    default:
      return { ...base, title: "기록", detail: "" };
  }
}

function buildNow() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const hh = String(now.getHours()).padStart(2, "0");
  const min = String(now.getMinutes()).padStart(2, "0");
  return { date: `${yyyy}-${mm}-${dd}`, time: `${hh}:${min}` };
}

function findPlantByName(plants, plantName) {
  if (!plantName) return null;
  const n = plantName.trim();
  return plants.find((p) => p.name === n) || null;
}

function createPlantLocal(setPlants, plantName, coverUrl = "") {
  const name = (plantName || "").trim();
  const id = `p_${Date.now()}`;
  const newPlant = { id, name, coverUrl, createdBy: "chatbot" };
  setPlants((prev) => [newPlant, ...prev]);
  return newPlant;
}
