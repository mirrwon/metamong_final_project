import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Button from "../components/common/Button";
import api from "../services/api";
const API_BASE = "/api/diary";

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

const formatDateLabel = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-CA");
};

const getItemDateValue = (item) => {
  return (
    item?.date ||
    item?.created_at ||
    item?.createdAt ||
    item?.createdDate ||
    item?.created_date ||
    null
  );
};

const EditPost = () => {
  const { id } = useParams();
  const nav = useNavigate();
  const [status, setStatus] = useState("loading");
  const [post, setPost] = useState(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [imagePreview, setImagePreview] = useState("");
  const [imageFile, setImageFile] = useState(null);
  const [saveStatus, setSaveStatus] = useState("idle");

  useEffect(() => {
    const fetchPost = async () => {
      setStatus("loading");
      try {
        const response = await api.get(API_BASE, { baseURL: "" });
        const list = normalizeDiaryItems(response.data);
        const found = list.find(
          (item) => String(item?.id || item?._id) === String(id)
        );
        setPost(found || null);
        setTitle(found?.title || "");
        setContent(found?.content || found?.body || "");
        setImagePreview(resolveImageUrl(found));
        setStatus("ready");
      } catch (error) {
        setStatus("error");
      }
    };

    fetchPost();
  }, [id]);

  const dateLabel = useMemo(() => {
    if (!post) return "";
    return formatDateLabel(getItemDateValue(post));
  }, [post]);

  const handleImageChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setImageFile(file);
    const url = URL.createObjectURL(file);
    setImagePreview(url);
  };

  const handleSave = async () => {
    setSaveStatus("saving");
    try {
      const formData = new FormData();
      formData.append("title", title);
      formData.append("content", content);
      if (imageFile) {
        formData.append("image", imageFile);
      }

      await api.put(`${API_BASE}/${id}`, formData, {
        baseURL: "",
        headers: { "Content-Type": "multipart/form-data" },
      });

      setSaveStatus("done");
      nav(`/diary/${id}`);
    } catch (error) {
      setSaveStatus("error");
    }
  };

  if (status === "loading") {
    return <div className="">Loading post...</div>;
  }

  if (status === "error") {
    return <div className="">Failed to load post.</div>;
  }

  if (!post) {
    return <div className="">Post not found.</div>;
  }

  const resolvedTitle = post?.title || "제목 없음";

  return (
    <div className="">
      <div className="">
        <h1 className="">Edit Post</h1>
        <div className="" />
      </div>
      <div className="">
        <div className="">
          {imagePreview ? (
            <img src={imagePreview} alt={resolvedTitle} />
          ) : (
            <div className="">No photo available</div>
          )}
        </div>
        <div className="">
          {dateLabel || "No date"}
        </div>
        <div className="">
          <label className="">
            사진 변경
            <input type="file" accept="image/*" onChange={handleImageChange} />
          </label>
        </div>
        <div className="">
          <input
            className=""
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="제목 입력"
          />
          <textarea
            className=""
            value={content}
            onChange={(event) => setContent(event.target.value)}
            rows={5}
          />
        </div>
      </div>
      <div className="">
        <Button text="수정 완료" type="primary" onClick={handleSave} />
      </div>
      {saveStatus === "error" && (
        <div className="">저장에 실패했습니다.</div>
      )}
    </div>
  );
};

export default EditPost;
