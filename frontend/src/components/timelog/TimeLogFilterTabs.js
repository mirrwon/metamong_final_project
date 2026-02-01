/**
필터 탭 컴포넌트
 * - activeTab: 현재 선택된 탭
 * - onChangeTab: 탭 클릭 시 부모 상태 변경
 * - counts: 각 탭에 표시할 숫자(원하면 사용)
 */

const TABS = [
  { key: "all", label: "전체" },
  { key: "water", label: "물주기" },
  { key: "fertilizer", label: "비료" },
  { key: "repot", label: "분갈이" },
  { key: "note", label: "특이사항" },
  { key: "photo", label: "사진" },
  { key: "new", label: "새 식물" },
];

export default function TimeLogFilterTabs({ activeTab, onChangeTab, counts }) {
  /** 탭 눌렀을 때 부모에게 key 전달 */
  const handleClickTab = (key) => {
    onChangeTab(key);
  };

  return (
    <div className="timelog-tabs" role="tablist" aria-label="다이어리 필터">
      {TABS.map((tab) => {
        const isActive = activeTab === tab.key;

        return (
          <button
            key={tab.key}
            type="button"
            className={`timelog-tab ${isActive ? "is-active" : ""}`}
            onClick={() => handleClickTab(tab.key)}
            role="tab"
            aria-selected={isActive}
          >
            <span className="timelog-tab__label">{tab.label}</span>

            <span className="timelog-tab__badge">
              {counts?.[tab.key] ?? 0}
            </span>
          </button>
        );
      })}
    </div>
  );
}
