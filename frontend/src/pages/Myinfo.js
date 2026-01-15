import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Button from '../components/common/Button';
import { ROUTES } from '../constants/routes';
import api from '../services/api';
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
    try {
      return JSON.parse(localStorage.getItem('user'));
    } catch (error) {
      return null;
    }
  }, [location.key]);

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
      name: '혜원',
    };

    if (!effectiveUser) return fallback;

    const merged = { ...fallback, ...effectiveUser };

    return {
      ...merged,
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
        <h1 className="myinfo-title">My Info</h1>
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
            <p>아이디: {myinfo.username}</p>
            <p>이름: {myinfo.name}</p>
            <p>나이: {myinfo.age}</p>
            <p>성별: {myinfo.gender}</p>
            <p>생년월일: {myinfo.birthDate}</p>
            <p>연락처: {myinfo.phone}</p>
            <p>e-mail: {myinfo.email}</p>
          </div>

          {/* 버튼 */}
          <div className="myinfo-actions">
            <Button text="내 정보 수정" type="primary" onClick={goEditMyinfo} />
          </div>
        </section>

        <section className="">
          <h2 className="">Results</h2>
          {resultError ? (
            <p className="">{resultError}</p>
          ) : null}
          {!resultError && resultImages.length === 0 ? (
            <p className="">No images yet.</p>
          ) : (
            <div className="">
              {resultImages.map((item) => (
                <img
                  key={item.name}
                  className=""
                  src={withCacheBust(item.url, item.mtime)}
                  alt={item.name}
                  loading="lazy"
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

export default Myinfo;
