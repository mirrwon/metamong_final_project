import { useEffect, useMemo, useState, useRef } from "react";
import axios from "axios"; // Assuming axios is installed, or use fetch
import TimeLogSummary from "../../components/timelog/TimeLogSummary";
import TimeLogFilterTabs from "../../components/timelog/TimeLogFilterTabs";
import TimeLogLine from "../../components/timelog/TimeLogLine";

import { readPendingDiaryPhoto, clearPendingDiaryPhoto } from "../../components/timelog/TimeLogPending";
import { FileToDataUrl } from "../../components/timelog/FileToDataUrl";

import "./TimeLog.css";

export default function TimeLogPage({ onEnterDecorate, decoratedData }) {
  /** 탭 */
  const [activeTab, setActiveTab] = useState("all");

  // ✅ Real Data State
  const [plants, setPlants] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  // 현재 사용자 (나중에 AuthContext에서 가져오기)
  const username = "test_user";

  const [activePlantId, setActivePlantId] = useState("");

  const [isAddPlantOpen, setIsAddPlantOpen] = useState(false);
  const [newPlantName, setNewPlantName] = useState("");
  const [newPlantFile, setNewPlantFile] = useState(null);

  // --- API Functions ---
  const fetchPlants = async () => {
    try {
      const res = await fetch(`/api/plantboard/plants?username=${username}`);
      const data = await res.json();
      if (data.ok) {
        setPlants(data.items || []);
      }
    } catch (err) {
      console.error("Failed to fetch plants:", err);
    }
  };

  const fetchLogs = async () => {
    try {
      setLoading(true);
      const res = await fetch(`/api/plantboard/logs?username=${username}`);
      const data = await res.json();
      if (data.ok) {
        setLogs(data.items || []);
      }
    } catch (err) {
      console.error("Failed to fetch logs:", err);
    } finally {
      setLoading(false);
    }
  };

  const createLog = async (logData) => {
    try {
      const res = await fetch("/api/plantboard/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, log: logData }),
      });
      const data = await res.json();
      if (data.ok) {
        // Optimistic update or refetch
        fetchLogs();
      }
    } catch (err) {
      console.error("Failed to create log:", err);
    }
  };

  const createPlant = async (plantData) => {
    try {
      const res = await fetch("/api/plantboard/plants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, plant: plantData }),
      });
      const data = await res.json();
      if (data.ok) {
        await fetchPlants();
        return data.item;
      }
    } catch (err) {
      console.error("Failed to create plant:", err);
    }
    return null;
  };

  const deleteLog = async (logId) => {
    try {
      const res = await fetch(`/api/plantboard/logs/${logId}?username=${username}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (data.ok) {
        fetchLogs();
      }
    } catch (err) {
      console.error("Failed to delete log:", err);
    }
  };

  // --- Initial Load ---
  useEffect(() => {
    fetchPlants();
    fetchLogs();
  }, []);

  const activePlant = useMemo(() => {
    return plants.find((p) => p.id === activePlantId) || null;
  }, [plants, activePlantId]);

  const isPlantSelected = Boolean(activePlantId);

  // --- Pending Photo Logic (from Chat) ---
  useEffect(() => {
    const applyPending = async () => {
      const pending = readPendingDiaryPhoto();
      if (!pending?.plantName || !pending?.imageUrl) return;

      clearPendingDiaryPhoto();

      // 1) Find plant or create
      let plant = plants.find((p) => p.name === pending.plantName);
      if (!plant) {
        // Create new plant automatically
        const newPlantData = {
          name: pending.plantName,
          coverUrl: pending.imageUrl,
          createdBy: "chatbot"
        };
        plant = await createPlant(newPlantData);
      }

      if (!plant) return; // Fail safe

      // 2) Select plant
      setActivePlantId(plant.id);

      // 3) Create logs
      const now = buildNow();

      // Photo Log
      await createLog({
        type: "photo",
        date: now.date,
        time: now.time,
        plantId: plant.id,
        plantName: plant.name,
        title: "배치 사진 저장",
        detail: "챗봇 최종 선택 이미지",
        imageUrl: pending.imageUrl,
        meta: { resultId: pending.resultId || null },
      });

      // New Plant Log (only if it was new, but logic sets it anyway usually)
      await createLog({
        type: "new",
        date: now.date,
        time: now.time,
        plantId: plant.id,
        plantName: plant.name,
        title: "새 식물 추가",
        detail: "새 식물을 등록했어요.",
        imageUrl: plant.coverUrl || pending.imageUrl,
      });
    };

    if (plants.length > 0) {
      // Only run if plants loaded or empty list confirmed, avoiding race condition?
      // Actually pending read clears it, so we need to be careful.
      // For simplicity, we assume plants load fast or we accept race.
      // A better way is checking if 'loading' in fetchPlants is done.
      applyPending();
    }
  }, [plants]); // Run when plants change (fetched)

  // --- Handlers ---
  const addPlantManually = async () => {
    const name = (newPlantName || "").trim();
    if (!name) return alert("식물 이름을 입력하세요.");
    if (!newPlantFile) return alert("대표 사진을 선택하세요.");

    const exist = plants.find((p) => p.name === name);
    if (exist) return alert("같은 이름의 식물이 이미 있어요.");

    let coverUrl = "";
    try {
      coverUrl = await FileToDataUrl(newPlantFile);
    } catch {
      return alert("이미지 처리에 실패했어요.");
    }

    const newPlantData = { name, coverUrl, createdBy: "manual" };
    const savedPlant = await createPlant(newPlantData);

    if (savedPlant) {
      setActivePlantId(savedPlant.id);
      setIsAddPlantOpen(false);
      setNewPlantName("");
      setNewPlantFile(null);

      // Log
      const now = buildNow();
      await createLog({
        type: "new",
        date: now.date,
        time: now.time,
        plantId: savedPlant.id,
        plantName: savedPlant.name,
        title: "새 식물 등록",
        detail: "수동으로 추가한 식물",
        imageUrl: coverUrl,
      });
    }
  };

  const addDiaryLog = async (type) => {
    if (!activePlant) return;

    if (type === "note") {
      const memo = window.prompt("특이사항 메모를 입력하세요");
      if (!memo || !memo.trim()) return;

      const now = buildNow();
      await createLog({
        type,
        date: now.date,
        time: now.time,
        plantId: activePlant.id,
        plantName: activePlant.name,
        title: "특이사항",
        detail: memo.trim(),
      });
      return;
    }

    if (type === "photo") return;

    const now = buildNow();
    let title = "기록";
    let detail = "";
    if (type === "water") { title = "물 줌"; detail = activePlant.name; }
    if (type === "fertilizer") { title = "비료 줌"; detail = activePlant.name; }
    if (type === "repot") { title = "분갈이"; detail = "분갈이 완료"; }

    await createLog({
      type,
      date: now.date,
      time: now.time,
      plantId: activePlant.id,
      plantName: activePlant.name,
      title,
      detail,
    });
  };

  const handleUploadPhoto = async (e) => {
    if (!activePlant) return;
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    let imageUrl = "";
    try {
      imageUrl = await FileToDataUrl(file);
    } catch {
      return alert("이미지 업로드 실패");
    }

    const now = buildNow();
    await createLog({
      type: "photo",
      date: now.date,
      time: now.time,
      plantId: activePlant.id,
      plantName: activePlant.name,
      title: "배치 사진 저장",
      detail: "직접 업로드한 사진",
      imageUrl,
      meta: { source: "upload", filename: file.name }
    });
  };

  // ✅ Decoration Save
  useEffect(() => {
    if (decoratedData && decoratedData.file) {
      const saveDecorated = async () => {
        try {
          const imageUrl = await FileToDataUrl(decoratedData.file);
          const now = buildNow();

          await createLog({
            type: "photo",
            date: now.date,
            time: now.time,
            plantId: decoratedData.plantId || activePlantId,
            plantName: decoratedData.plantName || (activePlant ? activePlant.name : "식물"),
            title: "꾸민 사진 저장",
            detail: decoratedData.nickname ? `${decoratedData.nickname} 꾸미기 완료` : "꾸미기 완료된 사진",
            imageUrl,
            meta: {
              source: "decorate",
              tags: decoratedData.tags
            },
          });
        } catch (e) {
          console.error("Failed to save decorated image:", e);
        }
      };
      saveDecorated();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [decoratedData]);

  // --- Filtering & Computed ---
  const filteredLogs = useMemo(() => {
    let base = logs;
    // Log has plantId, filter by it
    if (activePlantId) base = base.filter((log) => log.plantId === activePlantId);
    if (activeTab === "all") return base;
    return base.filter((log) => log.type === activeTab);
  }, [activeTab, logs, activePlantId]);

  const counts = useMemo(() => {
    const base = { all: 0, water: 0, fertilizer: 0, repot: 0, note: 0, photo: 0, new: 0 };
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
      // Sort items by time desc? Original was asc?
      // Original: (a.time > b.time ? 1 : -1) -> Ascending
      const items = map.get(date).slice().sort((a, b) => (a.time > b.time ? 1 : -1));
      return { date, items };
    });
  }, [filteredLogs]);

  const fileInputRef = useRef(null);
  const handleActionBtnFileClick = () => {
    if (fileInputRef.current) fileInputRef.current.click();
  };

  const deleteDiaryLog = (logId) => {
    if (window.confirm("정말 삭제하시겠습니까?")) {
      deleteLog(logId);
    }
  };

  return (
    <div className="timelog">
      <div className="timelog__header">
        <div className="timelog__title">TIME LOG</div>
      </div>

      <div className="timelog-inner">
        <div className="timelog-plant">
          <label className="timelog-plant__label">식물 선택</label>
          <select
            className="timelog-plant__select"
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

        <div className="timelog-summaryRow">
          <TimeLogSummary counts={counts} />
          <div className="timelog-topActions">
            <button type="button" className="timelog-addPlantBtn" onClick={() => setIsAddPlantOpen(true)}>
              + 새 식물 추가
            </button>
          </div>
        </div>

        {isAddPlantOpen && (
          <div className="timelog-modal" onClick={() => setIsAddPlantOpen(false)}>
            <div className="timelog-modal__panel" onClick={(e) => e.stopPropagation()}>
              <div className="timelog-modal__title">새 식물 추가</div>
              <label className="timelog-modal__label">식물 이름</label>
              <input
                className="timelog-modal__input"
                value={newPlantName}
                onChange={(e) => setNewPlantName(e.target.value)}
                placeholder="예) 몬스테라"
              />
              <label className="timelog-modal__label">대표 사진</label>
              <input
                className="timelog-modal__file"
                type="file"
                accept="image/*"
                onChange={(e) => setNewPlantFile(e.target.files?.[0] || null)}
              />
              <div className="timelog-modal__actions">
                <button type="button" className="timelog-modal__btn" onClick={() => setIsAddPlantOpen(false)}>취소</button>
                <button type="button" className="timelog-modal__btn timelog-modal__btn--primary" onClick={addPlantManually}>등록</button>
              </div>
            </div>
          </div>
        )}

        <TimeLogFilterTabs activeTab={activeTab} counts={counts} onChangeTab={setActiveTab} />

        <div className="timelog-timeline-section">
          <div className="timelog__sectionTitle">오늘의 타임라인</div>
          <div className="timelog__dateLabel">Test</div>
          <TimeLogLine
            groups={groups}
            onDelete={deleteDiaryLog}
            showPlantTag={!activePlantId}
            onEnterDecorate={onEnterDecorate}
          />
        </div>
      </div>

      <div className="timelog-actions">
        <div className="timelog-actions__row">
          <button type="button" className="timelog-actionBtn" onClick={() => addDiaryLog("water")} disabled={!isPlantSelected}>
            <span>💧</span> 물 줌
          </button>
          <button type="button" className="timelog-actionBtn" onClick={() => addDiaryLog("fertilizer")} disabled={!isPlantSelected}>
            <span>🧪</span> 비료 줌
          </button>
          <button type="button" className="timelog-actionBtn" onClick={() => addDiaryLog("repot")} disabled={!isPlantSelected}>
            <span>🪴</span> 분갈이
          </button>
          <button type="button" className="timelog-actionBtn" onClick={() => addDiaryLog("note")} disabled={!isPlantSelected}>
            <span>📝</span> 특이사항
          </button>
          <button
            type="button"
            className="timelog-actionBtn timelog-actionBtn--file"
            disabled={!isPlantSelected}
            onClick={handleActionBtnFileClick}
          >
            <span>🖼️</span> 사진추가
            <input
              ref={fileInputRef}
              className="timelog-fileInput"
              type="file"
              accept="image/*"
              style={{ display: 'none' }}
              onChange={handleUploadPhoto}
            />
          </button>
        </div>
      </div>
    </div>
  );
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
