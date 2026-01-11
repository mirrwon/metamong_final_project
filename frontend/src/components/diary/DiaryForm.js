// src/components/diary/DiaryForm.jsx
import Button from "../common/Button";

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
    <div className="">
      <div className="">
        <h1 className="">{formTitle}</h1>
        <div className="" />
      </div>

      <form className="" onSubmit={onSubmit}>
        {showDate && (
          <label className="">
            날짜
            <input
              className=""
              type="date"
              value={date}
              onChange={onDateChange}
              disabled={disableDate}
            />
          </label>
        )}

        <div className="">
          <div className="">
            {imagePreview ? (
              <img src={imagePreview} alt="preview" />
            ) : (
              <div className="">이미지{"\n"}업로드</div>
            )}

            <label className="">
              파일 선택
              <input type="file" accept="image/*" onChange={onImageChange} />
            </label>
          </div>

          <input
            className=""
            value={title}
            onChange={onTitleChange}
            placeholder="제목을 입력하세요..."
          />

          <textarea
            className=""
            value={content}
            onChange={onContentChange}
            placeholder="내용을 입력하세요..."
            rows={5}
          />
        </div>

        <div className="">
          <Button
            text={isSaving ? "저장 중..." : "저장"}
            type="primary"
            onClick={onSubmit}
          />
          <Button text="취소" type="option" onClick={onCancel} />
        </div>

        {errorMessage && <div className="">{errorMessage}</div>}
      </form>
    </div>
  );
};

export default DiaryForm;
