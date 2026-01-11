// src/components/diary/DiaryNewContainer.jsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import DiaryForm from "./DiaryForm";
import { diaryApi } from "../../services/diaryApi";

const DiaryNewContainer = () => {
  const nav = useNavigate();

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState("");

  const [status, setStatus] = useState("idle"); // idle | saving | error

  const handleImageChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setImageFile(file);
    const previewUrl = URL.createObjectURL(file);
    setImagePreview(previewUrl);
  };

  useEffect(() => {
    return () => {
      if (imagePreview && String(imagePreview).startsWith("blob:")) {
        URL.revokeObjectURL(imagePreview);
      }
    };
  }, [imagePreview]);

  const handleSubmit = async (event) => {
    if (event?.preventDefault) event.preventDefault();
    if (!title.trim() || !content.trim()) return;

    setStatus("saving");
    try {
      const formData = new FormData();
      formData.append("title", title);
      formData.append("content", content);
      if (imageFile) formData.append("image", imageFile);

      const res = await diaryApi.create(formData);
      const newId = res?.data?.id;

      nav(newId ? `/diary/${newId}` : "/diary");
    } catch (error) {
      setStatus("error");
    }
  };

  const goDiaryList = () => {
    nav("/diary");
  };

  return (
    <DiaryForm
      mode="create"
      title={title}
      content={content}
      date=""                
      showDate={false}    
      disableDate={true}
      imagePreview={imagePreview}
      isSaving={status === "saving"}
      errorMessage={status === "error" ? "등록에 실패했습니다." : ""}
      onTitleChange={(event) => setTitle(event.target.value)}
      onContentChange={(event) => setContent(event.target.value)}
      onDateChange={() => {}}
      onImageChange={handleImageChange}
      onSubmit={handleSubmit}
      onCancel={goDiaryList}
    />
  );
};

export default DiaryNewContainer;
