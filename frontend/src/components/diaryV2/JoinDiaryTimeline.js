 import JoinDiaryItemCard from "./JoinDiaryItemCard";



export default function DiaryTimeline({ groups, onDelete, showPlantTag }) {

  if (!groups || groups.length === 0) {
    return <div className="dv2-empty">해당 기록이 없어요.</div>;
  }

  return (
    <div className="dv2-timeline">
      {groups.map((group) => (
        <section key={group.date} className="dv2-day">
          <div className="dv2-day__title">{formatKoreanDate(group.date)}</div>

          <div className="dv2-day__list">
            {group.items.map((item) => (
              <JoinDiaryItemCard
                key={item.id} 
                item={item} 
                onDelete={onDelete} 
                showPlantTag={showPlantTag}/>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}


function formatKoreanDate(isoDate) {
  if (!isoDate) return "";
  const [y, m, d] = isoDate.split("-");
  return `${y}년 ${m}월 ${d}일`;
}
