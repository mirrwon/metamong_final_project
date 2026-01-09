import { useState } from "react";
// import "./JoinRegister.css";

const JoinRegister = ({ onSubmit }) => {

  const [formData, setFormData] = useState({
    profileImage: null, // File 객체 (서버에 보낼 때 사용 가능)
    username: "",
    password: "",
    confirmPassword: "",
    name: "",
    age: "",
    birthDate: "", // yyyy-mm-dd
    phone: "",
    email: "",
  });

  //프로필 사진 미리보기 URL (UI용)
  const [previewUrl, setPreviewUrl] = useState("");

  //폼 내부 검증 에러(예: 비번 불일치 등)
  const [formError, setFormError] = useState("");

  //input 텍스트/날짜 변경 처리
  const handleChange = (e) => {
    const { name, value } = e.target;

    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));

    setFormError("");
  };

  //프로필 이미지 변경
  const handleProfileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setFormData((prev) => ({
      ...prev,
      profileImage: file,
    }));

    //미리보기 URL 생성 (나중에 필요 없으면 삭제 가능)
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);

    setFormError("");
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    //비밀번호 확인 검증
    if (formData.password !== formData.confirmPassword) {
      setFormError("비밀번호가 일치하지 않습니다.");
      return;
    }

    //페이지에 넘길 payload 만들기
    //백엔드에 confirmPassword는 보통 안 보내서 제외)
    const payload = {
      username: formData.username,
      password: formData.password,
      name: formData.name,
      age: formData.age, // 백엔드에서 숫자 원하면 Number 변환은 페이지에서 해도 됨
      birthDate: formData.birthDate,
      phone: formData.phone,
      email: formData.email,
      profileImage: formData.profileImage,// 파일 업로드를 백엔드가 지원할 때 사용
    };

    //Register(페이지)로 넘김 → 거기서 API 호출
    onSubmit(payload);
  };

  return (
    <div className="register-container">
      <h2>회원가입</h2>

      {/* 프로필 사진 */}
      <div className="form-group">
        <label htmlFor="profileImage">프로필 사진</label>
        <input
          id="profileImage"
          type="file"
          accept="image/*"
          onChange={handleProfileChange}
        />
        {/* 미리보기 (CSS는 나중에) */}
        {previewUrl && (
          <div className="profile-preview">
            <img src={previewUrl} alt="프로필 미리보기" />
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit}>
        {/* 아이디 */}
        <div className="form-group">
          <label htmlFor="username">아이디</label>
          <input
            id="username"
            name="username"
            type="text"
            value={formData.username}
            onChange={handleChange}
            placeholder="아이디"
            required
          />
        </div>

        {/* 비밀번호 */}
        <div className="form-group">
          <label htmlFor="password">비밀번호</label>
          <input
            id="password"
            name="password"
            type="password"
            value={formData.password}
            onChange={handleChange}
            placeholder="비밀번호"
            required
          />
        </div>

        {/* 비밀번호 확인 */}
        <div className="form-group">
          <label htmlFor="confirmPassword">비밀번호 확인</label>
          <input
            id="confirmPassword"
            name="confirmPassword"
            type="password"
            value={formData.confirmPassword}
            onChange={handleChange}
            placeholder="비밀번호 확인"
            required
          />
        </div>

        {/* 이름 */}
        <div className="form-group">
          <label htmlFor="name">이름</label>
          <input
            id="name"
            name="name"
            type="text"
            value={formData.name}
            onChange={handleChange}
            placeholder="이름"
            required
          />
        </div>


        {/* 생년월일 */}
        <div className="form-group">
          <label htmlFor="birthDate">생년월일</label>
          <input
            id="birthDate"
            name="birthDate"
            type="date"
            value={formData.birthDate}
            onChange={handleChange}
            required
          />
        </div>

        {/* 연락처 */}
        <div className="form-group">
          <label htmlFor="phone">연락처</label>
          <input
            id="phone"
            name="phone"
            type="tel"
            value={formData.phone}
            onChange={handleChange}
            placeholder="010-0000-0000"
            required
          />
        </div>

        {/* 이메일 */}
        <div className="form-group">
          <label htmlFor="email">이메일</label>
          <input
            id="email"
            name="email"
            type="email"
            value={formData.email}
            onChange={handleChange}
            placeholder="email@example.com"
            required
          />
        </div>

        {/* 폼 검증 에러 표시 */}
        {formError && <p className="error-message">{formError}</p>}

        <button className="submit-button" type="submit">
          가입
        </button>
      </form>
    </div>
  );
};

export default JoinRegister;
