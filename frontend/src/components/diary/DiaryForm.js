import Button from "../common/Button";
import "./DiaryForm.css";

const DiaryForm = ({
  mode, // "create" | "edit"
  title,
  content,
  date,
  showDate,
  disableDate,
  imagePreview,
  isSaving,
  errorMessage,
  onTitleChange,
  onContentChange,
  onDateChange,
  onImageChange,
  onSubmit,
  onCancel,
}) => {
  const formTitle = mode === "edit" ? "Edit Post" : "New Post";

  return (
    <div className="diary-form">
      <div className="diary-form__head">
        <h1 className="diary-form__title">{formTitle}</h1>
        <div className="ui-line diary-form__line" />
      </div>

      <form className="diary-form__body" onSubmit={onSubmit}>
        {showDate && (
          <label className="diary-form__date">
            <input
              className="ui-input diary-form__date-input"
              type="date"
              value={date}
              onChange={onDateChange}
              disabled={disableDate}
            />
          </label>
        )}

        <div className="diary-form__content">
          <div className="diary-form__image">
            {imagePreview ? (
              <img
                className="diary-form__image-img"
                src={imagePreview}
                alt="preview"
              />
            ) : (
              <div className="diary-form__image-empty">
                이미지<br />업로드
              </div>
            )}

            <label className="diary-form__file-btn ui-btn ui-btn-primary">
              파일 선택
              <input
                className="diary-form__file-input"
                type="file"
                accept="image/*"
                onChange={onImageChange}
              />
            </label>
          </div>

          <input
            className="ui-input diary-form__input"
            value={title}
            onChange={onTitleChange}
            placeholder="제목을 입력하세요..."
          />

          <textarea
            className="diary-form__textarea"
            value={content}
            onChange={onContentChange}
            placeholder="내용을 입력하세요..."
            rows={5}
          />
        </div>

        <div className="diary-form__actions">
          <Button
            text={isSaving ? "저장 중..." : "저장"}
            type="primary"
            onClick={onSubmit}
          />
          <Button
            text="취소"
            type="option"
            onClick={onCancel}
          />
        </div>

        {errorMessage && (
          <div className="diary-form__error">
            {errorMessage}
          </div>
        )}
      </form>
    </div>
  );
};

export default DiaryForm;
