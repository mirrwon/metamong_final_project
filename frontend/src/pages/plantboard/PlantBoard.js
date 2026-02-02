import { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";
import DiaryMainPage from "./DiaryMainPage";
import TimeLogPage from "./TimeLogPage";
import "./PlantBoard.css";
import DecorateContainer from "../../components/decorate/DecorateContainer";

const PlantBoard = () => {
  const location = useLocation();
  const [activeView, setActiveView] = useState("timelog"); // 'timelog' | 'tamagotchi' | 'diary' | 'decorate'
  const [diaryKey, setDiaryKey] = useState(0);

  // Decoration state
  const [decorateItem, setDecorateItem] = useState(null);
  const [decoratedResult, setDecoratedResult] = useState(null);

  // Reset to timelog when entering the plantboard route (e.g. from Header)
  useEffect(() => {
    setActiveView("timelog");
    setDecorateItem(null);
    setDecoratedResult(null);
  }, [location]);

  // handleDiaryClick is no longer used directly, its logic is inlined in the onClick handler

  return (
    <div className="plantboard-container">
      {/* Sidebar Area */}
      <aside className="plantboard-sidebar">
        {/* Compact Log Tab at the very top */}
        <div
          className={`sidebar-compact-tab ${activeView === "timelog" ? "active" : ""}`}
          onClick={() => {
            setActiveView("timelog");
            setDecorateItem(null);
          }}
        >
          LOG
        </div>

        <div
          className={`sidebar-section ${activeView === "tamagotchi" ? "active" : ""}`}
          onClick={() => {
            setActiveView("tamagotchi");
            setDecorateItem(null);
          }}
        >
          <div className="sidebar-label">TAMAGOTCHI</div>
          <div className="sidebar-content tamagotchi-placeholder">
            <div className="placeholder-box">TAMAGOTCHI AREA</div>
          </div>
        </div>

        <div
          className={`sidebar-section ${activeView === "diary" ? "active" : ""}`}
          onClick={() => {
            if (activeView === "diary") {
              setDiaryKey(prev => prev + 1);
            }
            setActiveView("diary");
            setDecorateItem(null);
          }}
        >
          <div className="sidebar-label">DIARY</div>
          <div className="sidebar-content diary-placeholder">
            <div className="placeholder-box">DIARY AREA</div>
          </div>
        </div>

        {/* Optional: Add a Time Log dedicated tab if needed,
            but for now clicking TAMAGOTCHI or somewhere else returns to Time Log */}
      </aside>

      {/* Main Content Area */}
      <main className="plantboard-main">
        {activeView === "timelog" && (
          <TimeLogPage
            onEnterDecorate={(item) => {
              setDecorateItem(item);
              setActiveView("decorate");
              setDecoratedResult(null);
            }}
            decoratedData={decoratedResult}
          />
        )}
        {activeView === "tamagotchi" && (
          <div className="tamagotchi-view-placeholder">
            <h2>Tamagotchi Main View</h2>
            <p>준비 중입니다...</p>
          </div>
        )}
        {activeView === "diary" && <DiaryMainPage key={diaryKey} />}
        {activeView === "decorate" && (
          <DecorateContainer
            item={decorateItem}
            onCancel={() => {
              setActiveView("timelog");
              setDecorateItem(null);
            }}
            onSave={(decoratedData) => {
              setDecoratedResult({
                ...decoratedData,
                plantId: decorateItem?.plantId,
                plantName: decorateItem?.plantName
              });
              setActiveView("timelog");
              setDecorateItem(null);
            }}
          />
        )}
      </main>
    </div>
  );
};

export default PlantBoard;
