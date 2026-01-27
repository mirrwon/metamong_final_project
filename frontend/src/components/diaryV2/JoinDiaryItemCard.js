export default function DiaryItemCard({ item, onDelete, showPlantTag = false }) {
  const icon = getTypeIcon(item?.type);
  const plantLabel = item?.plantName || item?.plant?.name || "";

  const handleDelete = () => {
    if (!item?.id) return;
    const ok = window.confirm("이 기록을 삭제할까요?");
    if (!ok) return;
    if (typeof onDelete === "function") onDelete(item.id);
  };

  const hasImage = Boolean(item?.imageUrl);
  const showImageBlock = hasImage && (item?.type === "photo" || item?.type === "new");

  return (
    <div className="dv2-item">
      <div className="dv2-item__time">{item?.time}</div>

      <div className="dv2-item__card">
        <div className="dv2-item__top">
          <div className="dv2-item__topLeft">
            <span className="dv2-item__icon" aria-hidden>
              {icon}
            </span>

            <span className="dv2-item__title">{item?.title}</span>

            {showPlantTag && plantLabel ? (
              <span className="dv2-item__plantTag">{plantLabel}</span>
            ) : null}
          </div>

          <button
            type="button"
            className="dv2-item__more"
            onClick={handleDelete}
            aria-label="기록 삭제"
            title="삭제"
          >
            ⋯
          </button>
        </div>

        {item?.detail ? <div className="dv2-item__detail">{item.detail}</div> : null}

        {showImageBlock ? (
          <div className="dv2-item__image">
            <img
              className="dv2-item__img"
              src={item.imageUrl}
              alt={plantLabel || item?.title || "image"}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function getTypeIcon(type) {
  switch (type) {
    case "water":
      return "💧";
    case "fertilizer":
      return "🧪";
    case "move":
      return "🪴";
    case "note":
      return "📝";
    case "photo":
      return "🖼️";
    case "new":
      return "🌱";
    default:
      return "•";
  }
}
