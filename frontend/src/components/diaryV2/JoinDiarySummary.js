
export default function DiarySummary({ counts }) {
  return (
    <div className="dv2-summary">
      <div className="dv2-summary__item">
        <div className="dv2-summary__label">물 준 횟수</div>
        <div className="dv2-summary__value">💧 {counts?.water ?? 0}</div>
      </div>

      <div className="dv2-summary__item">
        <div className="dv2-summary__label">비료 준 횟수</div>
        <div className="dv2-summary__value">🧪 {counts?.fertilizer ?? 0}</div>
      </div>

      <div className="dv2-summary__item">
        <div className="dv2-summary__label">특이사항</div>
        <div className="dv2-summary__value">📝 {counts?.note ?? 0}</div>
      </div>
    </div>
  );
}
