import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/common/Button';
import { ROUTES } from '../constants/routes';
import { updateProfile } from '../services/authService';
import './MyinfoEdit.css';

const withCacheBust = (url, cacheBust) => {
  if (!url) return '';
  if (!cacheBust) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}v=${cacheBust}`;
};

const MyinfoEdit = ({ user, setUser }) => {
  const nav = useNavigate();

  const storedUser = useMemo(() => {
    try {
      return JSON.parse(localStorage.getItem("user"));
    } catch {
      return null;
    }
  }, []);

  const effectiveUser = storedUser || user;

  const initialMyinfo = useMemo(
    () => ({
      profileImageUrl: effectiveUser?.profileImageUrl || '',
      username: effectiveUser?.username || '',
      password: '',
      name: effectiveUser?.name || '혜원',
      gender: effectiveUser?.gender || 'female',
      birthDate: effectiveUser?.birthDate || '',
      phone: effectiveUser?.phone || '010-1234-5678',
      email: effectiveUser?.email || 'onlywon@gmail.com',
    }),
    [effectiveUser]
  );

  const [myinfo, setMyinfo] = useState(initialMyinfo);
  const [profileImageFile, setProfileImageFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    setMyinfo(initialMyinfo);
  }, [initialMyinfo]);

  useEffect(() => {
    if (!profileImageFile) {
      setPreviewUrl('');
      return;
    }
    const url = URL.createObjectURL(profileImageFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [profileImageFile]);

  const handleChangeMyinfo = (e) => {
    const { name, value } = e.target;
    setMyinfo((prev) => ({ ...prev, [name]: value }));
  };

  const handleChangeProfileImage = (e) => {
    const file = e.target.files?.[0] ?? null;
    setProfileImageFile(file);
    setError('');
  };

  const goMyinfo = (e) => {
    if (e) e.preventDefault();
    nav(ROUTES.MYINFO);
  };

  const handleSubmitMyinfoEdit = async (e) => {
    e.preventDefault();
    setError('');

    try {
      const payload = {
        username: myinfo.username,
        password: myinfo.password || undefined,
        name: myinfo.name,
        gender: myinfo.gender,
        birthDate: myinfo.birthDate,
        phone: myinfo.phone,
        email: myinfo.email,
        profileImage: profileImageFile || undefined,
      };

      const res = await updateProfile(payload);
      const cacheBust = Date.now();
      const nextUser = { ...res.data, profileImageCacheBust: cacheBust };

      localStorage.setItem('user', JSON.stringify(nextUser));
      if (setUser) setUser(nextUser);

      nav(ROUTES.MYINFO);
    } catch (err) {
      setError('프로필 수정에 실패했습니다.');
    }
  };

  const imageSrc =
    previewUrl ||
    withCacheBust(myinfo.profileImageUrl, effectiveUser?.profileImageCacheBust);

  return (
    <div className="l-cover">
      <div className="l-cover-center">
        <h1 className="myinfoedit-title">My Info Edit</h1>
        <div className="ui-line myinfoedit-divider" />

        {/* ✅ 핵심: form 래퍼 클래스 */}
        <form className="myinfoedit-form" onSubmit={handleSubmitMyinfoEdit}>
          {/* ================= 프로필 사진 ================= */}
          <section className="myinfoedit-section">
            <div className="myinfoedit-photoRow">
              <div className="myinfoedit-photoBox">
                {imageSrc ? (
                  <img
                    src={imageSrc}
                    alt="내 정보 사진"
                    className="myinfoedit-photoImg"
                  />
                ) : (
                  <div className="myinfoedit-photoEmpty">사진</div>
                )}
              </div>

              <input
                id="profileImage"
                type="file"
                accept="image/*"
                onChange={handleChangeProfileImage}
                className="myinfoedit-fileInput"
              />

              {/* ✅ ui-btn 사용 */}
              <label
                htmlFor="profileImage"
                className="ui-btn ui-btn-primary myinfoedit-fileBtn"
              >
                프로필 사진 수정
              </label>

              {profileImageFile && (
                <p className="myinfoedit-fileName">
                  선택된 파일: {profileImageFile.name}
                </p>
              )}
            </div>
          </section>

          {/* ================= 기본 정보 ================= */}
          <section className="myinfoedit-section">
            <input
              name="username"
              type="text"
              value={myinfo.username}
              readOnly
              className="ui-input myinfoedit-readonly"
            />
            <p className="myinfoedit-help">아이디는 수정할 수 없어요.</p>

            <input
              name="password"
              type="password"
              value={myinfo.password}
              onChange={handleChangeMyinfo}
              placeholder="비밀번호 변경 (원할 때만 입력)"
              autoComplete="new-password"
              className="ui-input"
            />

            <input
              name="name"
              type="text"
              value={myinfo.name}
              onChange={handleChangeMyinfo}
              placeholder="이름"
              className="ui-input"
            />

            <select
              name="gender"
              value={myinfo.gender}
              onChange={handleChangeMyinfo}
              className="ui-input"
            >
              <option value="male">남성</option>
              <option value="female">여성</option>
              <option value="other">무응답</option>
            </select>

            <input
              name="birthDate"
              type="date"
              value={myinfo.birthDate}
              onChange={handleChangeMyinfo}
              className="ui-input"
            />

            <input
              name="phone"
              type="tel"
              value={myinfo.phone}
              onChange={handleChangeMyinfo}
              placeholder="010-0000-0000"
              className="ui-input"
            />

            <input
              name="email"
              type="email"
              value={myinfo.email}
              onChange={handleChangeMyinfo}
              placeholder="email@example.com"
              className="ui-input"
            />
          </section>

          {/* ================= 버튼 ================= */}
          <div className="myinfoedit-actions">
            <Button text="취소" type="secondary" onClick={goMyinfo} />
            <button
              type="submit"
              className="ui-btn ui-btn-primary"
            >
              수정
            </button>
          </div>

          {error && <p className="error-message">{error}</p>}
        </form>
      </div>
    </div>
  );
};

export default MyinfoEdit;
