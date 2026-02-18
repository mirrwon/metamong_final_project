import { useState } from "react";

const DecorateForm = ({
    baseImageUrl,
    plant,
    nickname,
    dday,
    fixedTags,
    customTags,
    onChangeNickname,
    onChangeDday,
    onToggleFixedTag,
    onAddCustomTag,
    onRemoveCustomTag,
    onGenerate,
    status,
}) => {
    const [tagInput, setTagInput] = useState("");

    const isGenerating = status === "generating";

    const submitTag = () => {
        const raw = tagInput.trim();
        if (!raw) return;
        onAddCustomTag(raw);
        setTagInput("");
    };

    const handleTagKeyDown = (e) => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        submitTag();
    };

    return (
        <div className="decorate-panel">
            <div className="decorate-panel__section">
                <div className="decorate-panel__label">선택된 이미지</div>
                {baseImageUrl ? (
                    <img className="decorate-panel__thumb" src={baseImageUrl} alt="picked" />
                ) : (
                    <div className="decorate-panel__empty">꾸밀 이미지를 먼저 선택해주세요.</div>
                )}
            </div>

            <div className="decorate-panel__section">
                <div className="decorate-panel__label">식물이 별명</div>
                <input
                    className="decorate-input"
                    value={nickname}
                    onChange={(e) => onChangeNickname(e.target.value)}
                    placeholder="예: 초록이"
                />
            </div>

            <div className="decorate-panel__section">
                <div className="decorate-panel__label">함께한 날 (D+)</div>
                <input
                    className="decorate-input"
                    value={dday}
                    onChange={(e) => onChangeDday(e.target.value)}
                    placeholder="예: 100"
                    inputMode="numeric"
                />
            </div>


            <div className="decorate-panel__section">
                <div className="decorate-panel__label">태그 추가</div>

                <div className="tag-add">
                    <input
                        className="decorate-input"
                        value={tagInput}
                        onChange={(e) => setTagInput(e.target.value)}
                        onKeyDown={handleTagKeyDown}
                        placeholder="예: 거실에서 (Enter)"
                    />
                    <button type="button" className="tag-add__btn" onClick={submitTag}>
                        추가
                    </button>
                </div>

                {customTags.length ? (
                    <div className="tag-row">
                        {customTags.map((tag) => (
                            <button
                                type="button"
                                key={tag}
                                className="tag-chip is-on"
                                onClick={() => onRemoveCustomTag(tag)}
                                title="클릭하면 삭제"
                            >
                                {tag} <span className="tag-x">×</span>
                            </button>
                        ))}
                    </div>
                ) : (
                    <div className="decorate-panel__hint">추가된 태그가 없습니다.</div>
                )}
            </div>

            <div className="decorate-panel__actions">
                <button
                    className="timelog-actionBtn"
                    style={{ width: '100%', height: '50px', fontSize: '16px' }}
                    onClick={onGenerate}
                    disabled={isGenerating || !baseImageUrl}
                >
                    {isGenerating ? "이미지 생성 중..." : "✨ 꾸미기 완료"}
                </button>
            </div>

            <div className="decorate-panel__note">
                * '꾸미기 완료'를 누르면 태그가 사진 주변에 자동 배치되어 이미지가 생성됩니다.
            </div>
        </div>
    );
};

const toLabelTags = (plant) => {
    if (!plant) return [];
    const tags = [
        plant.name ? `#${plant.name}` : null,
        plant.type ? `#${plant.type}` : null,
        plant.mood ? `#${plant.mood}` : null,
        plant.difficulty ? `#${plant.difficulty}` : null,
        plant.light ? `#${plant.light}` : null,
    ].filter(Boolean);

    return Array.from(new Set(tags));
};

export default DecorateForm;
