import { useState } from "react";
import "../../pages/auth/Register.css";

const JoinRegister = ({ onSubmit }) => {
  const [formData, setFormData] = useState({
    profileImage: null,
    username: "",
    password: "",
    confirmPassword: "",
    name: "",
    age: "",
    gender: "",
    birthDate: "",
    phone: "",
    email: "",
  });

  const [previewUrl, setPreviewUrl] = useState("");
  const [formError, setFormError] = useState("");

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
    setFormError("");
  };

  const handleProfileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setFormData((prev) => ({
      ...prev,
      profileImage: file,
    }));

    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    setFormError("");
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (formData.password !== formData.confirmPassword) {
      setFormError("비밀번호가 일치하지 않습니다.");
      return;
    }

    const payload = {
      username: formData.username,
      password: formData.password,
      name: formData.name,
      age: formData.age,
      gender: formData.gender,
      birthDate: formData.birthDate,
      phone: formData.phone,
      email: formData.email,
      profileImage: formData.profileImage,
    };

    onSubmit(payload);
  };

  return (
    <div className="register-container">
      <h2 className="register-title">회원가입</h2>
      <div className="ui-line register-divider" />

      <div className="register-form">
        {/* 프로필 */}
        <span className="register-label">프로필 사진</span>

        <div className="profile-row">
          <div className="profile-preview-box">
            {previewUrl && <img src={previewUrl} alt="프로필 미리보기" />}
          </div>

          <input
            id="profileImage"
            type="file"
            accept="image/*"
            onChange={handleProfileChange}
            className="profile-input"
          />

          <label
            htmlFor="profileImage"
            className="ui-btn ui-btn-primary profile-btn"
          >
            프로필 사진 추가
          </label>
        </div>

        <form onSubmit={handleSubmit}>
          <input
            name="username"
            type="text"
            value={formData.username}
            onChange={handleChange}
            placeholder="아이디"
            className="ui-input"
            required
          />

          <input
            name="password"
            type="password"
            value={formData.password}
            onChange={handleChange}
            placeholder="비밀번호"
            className="ui-input"
            required
          />

          <input
            name="confirmPassword"
            type="password"
            value={formData.confirmPassword}
            onChange={handleChange}
            placeholder="비밀번호 확인"
            className="ui-input"
            required
          />

          <input
            name="name"
            type="text"
            value={formData.name}
            onChange={handleChange}
            placeholder="이름"
            className="ui-input"
            required
          />

          {/* 성별 */}
          <select
            name="gender"
            value={formData.gender}
            onChange={handleChange}
            className="ui-input"
            required
          >
            <option value="">성별 선택</option>
            <option value="male">남성</option>
            <option value="female">여성</option>
            <option value="other">무응답</option>
          </select>

          <input
            name="birthDate"
            type="date"
            value={formData.birthDate}
            onChange={handleChange}
            className="ui-input"
            required
          />

          <input
            name="phone"
            type="tel"
            value={formData.phone}
            onChange={handleChange}
            placeholder="010-0000-0000"
            className="ui-input"
            required
          />

          <input
            name="email"
            type="email"
            value={formData.email}
            onChange={handleChange}
            placeholder="email@example.com"
            className="ui-input"
            required
          />

          {formError && (
            <p className="register-error">{formError}</p>
          )}

          <button
            type="submit"
            className="ui-btn ui-btn-primary register-submit"
          >
            가입
          </button>
        </form>
      </div>
    </div>
  );
};

export default JoinRegister;
