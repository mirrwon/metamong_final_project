import { useEffect, useState } from "react";
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

const PostView = () => {
  const { id } = useParams();
  const nav = useNavigate();
  const [status, setStatus] = useState("loading");
  const [post, setPost] = useState(null);
  const [isLightboxOpen, setIsLightboxOpen] = useState(false);

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
        setStatus("ready");
      } catch (error) {
        setStatus("error");
      }
    };

    fetchPost();
  }, [id]);

  const handleEdit = () => {
    nav(`/diary/${id}/edit`);
  };

  const handleOpenLightbox = () => {
    if (!imageUrl) return;
    setIsLightboxOpen(true);
  };

  const handleCloseLightbox = () => {
    setIsLightboxOpen(false);
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

  const imageUrl = resolveImageUrl(post);
  const dateLabel = formatDateLabel(getItemDateValue(post));
  const title = post?.title || "제목 없음";
  const content = post?.content || post?.body || "";

  return (
    <div className="">
      <div className="">
        <h1 className="">Post View</h1>
        <div className="" />
      </div>
      <div className="">
        <button
          type="button"
          className=""
          onClick={handleOpenLightbox}
        >
          {imageUrl ? (
            <img src={imageUrl} alt={title} />
          ) : (
            <div className="">No photo available</div>
          )}
        </button>
        <div className="">
          {dateLabel || "No date"}
        </div>
        <div className="">
          <h2 className="">{title}</h2>
          <p className="">
            {content || "No content provided."}
          </p>
        </div>
      </div>
      <div className="">
        <Button text="수정" type="primary" onClick={handleEdit} />
      </div>
      {isLightboxOpen && (
        <div className="" onClick={handleCloseLightbox}>
          <button
            type="button"
            className=""
            onClick={handleCloseLightbox}
          >
            닫기
          </button>
          <div
            className=""
            onClick={(event) => event.stopPropagation()}
          >
            <img src={imageUrl} alt={title} />
          </div>
        </div>
      )}
    </div>
  );
};

export default PostView;
