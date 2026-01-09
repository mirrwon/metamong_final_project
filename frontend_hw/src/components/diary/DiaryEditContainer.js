import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DiaryForm from "./DiaryForm";
import { diaryApi } from "../../services/diaryApi";

const normalizeDiaryItems = (payload) => {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  return payload.items || payload.data || [];
};

const resolveImageUrl = (item) => {
  return (
    item?.imageUrl ||
    item?.image_url ||
    item?.photoUrl ||
    item?.photo_url ||
    item?.photo ||
    item?.image ||
    ""
  );
};

const toDateInputValue = (value) => {
  if (!value) return "";
  return String(value).slice(0, 10);
};

const DiaryEditContainer = () => {
  const { id } = useParams();
  const nav = useNavigate();

  const [loadStatus, setLoadStatus] = useState("loading"); // loading | ready | error | notfound
  const [saveStatus, setSaveStatus] = useState("idle"); // idle | saving | error

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [date, setDate] = useState(""); // 표시용

  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState("");

  useEffect(() => {
    const loadPost = async () => {
      setLoadStatus("loading");
      try {
        const res = await diaryApi.getList();
        const list = normalizeDiaryItems(res?.data);

        const found = list.find(
          (item) => String(item?.id || item?._id) === String(id)
        );

        if (!found) {
          setLoadStatus("notfound");
          return;
        }

        setTitle(found?.title || "");
        setContent(found?.content || found?.body || "");
        setDate(toDateInputValue(found?.date));
        setImagePreview(resolveImageUrl(found));
        setLoadStatus("ready");
      } catch (error) {
        setLoadStatus("error");
      }
    };

    if (id) loadPost();
  }, [id]);

  useEffect(() => {
    return () => {
      if (imagePreview && String(imagePreview).startsWith("blob:")) {
        URL.revokeObjectURL(imagePreview);
      }
    };
  }, [imagePreview]);

  const handleImageChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setImageFile(file);
    const previewUrl = URL.createObjectURL(file);
    setImagePreview(previewUrl);
  };

  const handleSubmit = async (event) => {
    if (event?.preventDefault) event.preventDefault();
    if (!title.trim() || !content.trim()) return;

    setSaveStatus("saving");
    try {
      const formData = new FormData();
      formData.append("title", title);
      formData.append("content", content);
      if (imageFile) formData.append("image", imageFile);

      await diaryApi.update(id, formData);
      nav(`/diary/${id}`);
    } catch (error) {
      setSaveStatus("error");
    }
  };

  const goDiaryDetail = () => {
    nav(`/diary/${id}`);
  };

  if (loadStatus === "loading") return <div className="">Loading post...</div>;
  if (loadStatus === "error") return <div className="">Failed to load post.</div>;
  if (loadStatus === "notfound") return <div className="">Post not found.</div>;

  return (
    <DiaryForm
      mode="edit"
      title={title}
      content={content}
      date={date}
      showDate={true}      
      disableDate={true} 
      imagePreview={imagePreview}
      isSaving={saveStatus === "saving"}
      errorMessage={saveStatus === "error" ? "저장에 실패했습니다." : ""}
      onTitleChange={(event) => setTitle(event.target.value)}
      onContentChange={(event) => setContent(event.target.value)}
      onDateChange={(event) => setDate(event.target.value)} // 실제로는 disabled라 호출 거의 없음
      onImageChange={handleImageChange}
      onSubmit={handleSubmit}
      onCancel={goDiaryDetail}
    />
  );
};

export default DiaryEditContainer;
