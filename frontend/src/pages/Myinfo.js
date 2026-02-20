import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Button from '../components/common/Button';
import { ROUTES } from '../constants/routes';
import api from '../services/api';
import { readStoredUser } from '../services/session';
import './Myinfo.css';

const withCacheBust = (url, cacheBust) => {
  if (!url) return '';
  if (!cacheBust) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}v=${cacheBust}`;
};

const calculateAge = (birthDate) => {
  if (!birthDate) return "";
  const date = new Date(birthDate);
  if (Number.isNaN(date.getTime())) return "";

  const now = new Date();
  let age = now.getFullYear() - date.getFullYear();
  const monthDiff = now.getMonth() - date.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && now.getDate() < date.getDate())) {
    age -= 1;
  }
  return age;
};

const Myinfo = ({ user }) => {
  const nav = useNavigate();
  const location = useLocation();
  const [resultImages, setResultImages] = useState([]);
  const [resultError, setResultError] = useState('');

  const storedUser = useMemo(() => {
    return readStoredUser();
  }, []);

  // Prefer localStorage so updated profile shows immediately after redirect.
  const effectiveUser = storedUser || user;

  const myinfo = useMemo(() => {
    const fallback = {
      profileImageUrl: '',
      username: 'hyewon',
      age: 30,
      gender: "여성",
      birthDate: '1994-10-19',
      phone: '010-1234-5678',
      email: 'onlywon@gmail.com',
      zipcode: '',
      address1: '',
      address2: '',
      name: '혜원',
    };

    if (!effectiveUser) return fallback;

    const merged = { ...fallback, ...effectiveUser };
    const resolvedUsername = merged.user_name || merged.username || fallback.username;

    return {
      ...merged,
      username: resolvedUsername,
      profileImageUrl: withCacheBust(
        merged.profileImageUrl,
        effectiveUser?.profileImageCacheBust
      ),
      age: calculateAge(merged.birthDate),
    };
  }, [effectiveUser]);

  const goEditMyinfo = () => {
    nav(ROUTES.MYINFO_EDIT);
  };

  useEffect(() => {
    let active = true;

    const loadResults = async () => {
      try {
        const { data } = await api.get('/api/auth/results');
        if (!active) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        setResultImages(items);
        setResultError('');
      } catch (error) {
        if (!active) return;
        setResultImages([]);
        setResultError('Failed to load results.');
      }
    };

    loadResults();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="myinfo-page l-cover">
      <div className="myinfo-center l-cover-center">
        <h1 className="myinfo-title">내 프로필</h1>
        <div className="ui-line myinfo-divider" />

        <section className="myinfo-section">
          {/* 프로필 이미지 */}
          <div className="myinfo-photo">
            {myinfo.profileImageUrl ? (
              <img
                className="myinfo-photo-img"
                src={myinfo.profileImageUrl}
                alt="내 정보 사진"
              />
            ) : (
              <div className="myinfo-photo-empty">[내 정보 이미지]</div>
            )}
          </div>

          {/* 텍스트 정보 */}
          <div className="myinfo-text">
            <div className="myinfo-field">
              <span className="myinfo-label">아이디</span>
              <div className="myinfo-value">{myinfo.username}</div>
            </div>
            <div className="myinfo-field">
              <span className="myinfo-label">이름</span>
              <div className="myinfo-value">{myinfo.name}</div>
            </div>
            <div className="myinfo-field">
              <span className="myinfo-label">나이</span>
              <div className="myinfo-value">{myinfo.age}</div>
            </div>
            <div className="myinfo-field">
              <span className="myinfo-label">성별</span>
              <div className="myinfo-value">{myinfo.gender}</div>
            </div>
            <div className="myinfo-field">
              <span className="myinfo-label">생년월일</span>
              <div className="myinfo-value">{myinfo.birthDate}</div>
            </div>
            <div className="myinfo-field">
              <span className="myinfo-label">연락처</span>
              <div className="myinfo-value">{myinfo.phone}</div>
            </div>
            <div className="myinfo-field">
              <span className="myinfo-label">e-mail</span>
              <div className="myinfo-value">{myinfo.email}</div>
            </div>
            {myinfo.zipcode ? (
              <div className="myinfo-field">
                <span className="myinfo-label">우편번호</span>
                <div className="myinfo-value">{myinfo.zipcode}</div>
              </div>
            ) : null}
            {myinfo.address1 ? (
              <div className="myinfo-field">
                <span className="myinfo-label">주소</span>
                <div className="myinfo-value">{myinfo.address1}</div>
              </div>
            ) : null}
            {myinfo.address2 ? (
              <div className="myinfo-field">
                <span className="myinfo-label">상세 주소</span>
                <div className="myinfo-value">{myinfo.address2}</div>
              </div>
            ) : null}
          </div>

          {/* 버튼 */}
          <div className="myinfo-actions">
            <Button text="프로필 수정" type="primary" onClick={goEditMyinfo} />
          </div>
        </section>


      </div>
    </div>
  );
};

export default Myinfo;
