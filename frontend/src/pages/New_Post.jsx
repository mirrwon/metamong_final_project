import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Button from "../components/common/Button";
import api from "../services/api";
const API_BASE = "/api/diary";

const NewPost = () => {
  const nav = useNavigate();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState("");
  const [status, setStatus] = useState("idle");

  const handleImageChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setImageFile(file);
    setImagePreview(URL.createObjectURL(file));
  };

  const handleSubmit = async () => {
    if (!title.trim() || !content.trim()) return;
    setStatus("saving");
    try {
      const formData = new FormData();
      formData.append("title", title);
      formData.append("content", content);
      if (imageFile) {
        formData.append("image", imageFile);
      }

      const response = await api.post(API_BASE, formData, {
        baseURL: "",
        headers: { "Content-Type": "multipart/form-data" },
      });

      const newId = response?.data?.id;
      nav(newId ? `/diary/${newId}` : "/diary");
    } catch (error) {
      setStatus("error");
    }
  };

  return (
    <div className="">
      <div className="">
        <h1 className="">New Post</h1>
        <div className="" />
      </div>

      <div className="">
        <div className="">
          {imagePreview ? (
            <img src={imagePreview} alt="preview" />
          ) : (
            <div className="">이미지{"\n"}업로드</div>
          )}
          <label className="">
            파일 선택
            <input type="file" accept="image/*" onChange={handleImageChange} />
          </label>
        </div>
        <input
          className=""
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="제목을 입력하세요..."
        />
        <textarea
          className=""
          value={content}
          onChange={(event) => setContent(event.target.value)}
          placeholder="내용을 입력하세요..."
          rows={5}
        />
      </div>

      <div className="">
        <Button text="등록" type="primary" onClick={handleSubmit} />
      </div>
      {status === "error" && (
        <div className="">등록에 실패했습니다.</div>
      )}
    </div>
  );
};

export default NewPost;
