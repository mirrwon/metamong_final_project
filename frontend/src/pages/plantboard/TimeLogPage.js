import { useMemo, useState } from "react";
import TimeLogSummary from "../../components/timelog/TimeLogSummary";
import TimeLogFilterTabs from "../../components/timelog/TimeLogFilterTabs";
import TimeLogPlantSelector from "../../components/timelog/TimeLogPlantSelector";
import AddPlantModal from "../../components/timelog/AddPlantModal";
import TimeLogActionBar from "../../components/timelog/TimeLogActionBar";
import TimeLogTimelineSection from "../../components/timelog/TimeLogTimelineSection";
import useTimeLogData from "../../hooks/useTimeLogData";
import useTimeLogComputed from "../../hooks/useTimeLogComputed";
import useTimeLogHandlers from "../../hooks/useTimeLogHandlers";

import "./TimeLog.css";

export default function TimeLogPage({ onEnterDecorate, decoratedData }) {
  const [activeTab, setActiveTab] = useState("all");
  const username = "test_user";
  const [activePlantId, setActivePlantId] = useState("");
  const [isAddPlantOpen, setIsAddPlantOpen] = useState(false);
  const [newPlantName, setNewPlantName] = useState("");
  const [newPlantFile, setNewPlantFile] = useState(null);

  const { plants, logs, createLog, createPlant, deleteLog } = useTimeLogData(username);
  const activePlant = useMemo(() => plants.find((p) => p.id === activePlantId) || null, [plants, activePlantId]);
  const isPlantSelected = Boolean(activePlantId);
  const { counts, groups } = useTimeLogComputed({ logs, activePlantId, activeTab });
  const { addPlantManually, addDiaryLog, handleUploadPhoto, deleteDiaryLog } = useTimeLogHandlers({
    plants,
    activePlant,
    activePlantId,
    setActivePlantId,
    newPlantName,
    newPlantFile,
    setNewPlantName,
    setNewPlantFile,
    setIsAddPlantOpen,
    createLog,
    createPlant,
    deleteLog,
    decoratedData,
  });

  return (
    <div className="timelog">
      <div className="timelog__header">
        <div className="timelog__title">TIME LOG</div>
      </div>

      <div className="timelog-inner">
        <TimeLogPlantSelector
          plants={plants}
          activePlantId={activePlantId}
          onChange={(e) => setActivePlantId(e.target.value)}
        />

        <div className="timelog-summaryRow">
          <TimeLogSummary counts={counts} />
          <div className="timelog-topActions">
            <button
              type="button"
              className="timelog-addPlantBtn"
              onClick={() => setIsAddPlantOpen(true)}
            >
              + 새 식물 추가
            </button>
          </div>
        </div>

        <AddPlantModal
          open={isAddPlantOpen}
          onClose={() => setIsAddPlantOpen(false)}
          newPlantName={newPlantName}
          onChangeName={(e) => setNewPlantName(e.target.value)}
          onChangeFile={(e) => setNewPlantFile(e.target.files?.[0] || null)}
          onSubmit={addPlantManually}
        />

        <TimeLogFilterTabs
          activeTab={activeTab}
          counts={counts}
          onChangeTab={setActiveTab}
        />

        <TimeLogTimelineSection
          groups={groups}
          onDelete={deleteDiaryLog}
          showPlantTag={!activePlantId}
          onEnterDecorate={onEnterDecorate}
        />
      </div>

      <TimeLogActionBar
        isPlantSelected={isPlantSelected}
        onAddDiaryLog={addDiaryLog}
        onUploadPhoto={handleUploadPhoto}
      />
    </div>
  );
}
