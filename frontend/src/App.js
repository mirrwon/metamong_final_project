import "./styles/tokens.css";
import "./styles/components.css"
import "./styles/layout.css"
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useState } from 'react';
import { ROUTES } from './constants/routes';
import {
  clearSession,
  readStoredUser,
  SESSION_EXPIRED_EVENT,
  touchActivity,
  isSessionExpired,
} from './services/session';

//이미지 배경으로 설정
import { useEffect } from "react";

// pages (라우트에 직접 연결되는 페이지)\
import Splash from './pages/intro/Splash';
import Home from './pages/Home';
import Login from './pages/auth/Login';
import Register from './pages/auth/Register';
import Myinfo from './pages/Myinfo';
import MyinfoEdit from './pages/MyinfoEdit';
import Chat from './pages/Chat';
import PlantData from './pages/PlantData';

// Diary pages
import Diary from './pages/Diary';
import DiaryNew from './pages/DiaryNew';
import DiaryDetail from './pages/DiaryDetail';
import DiaryEdit from './pages/DiaryEdit';

//DiaryV2 pages
import DiaryV2 from "./pages/DiaryV2";


// layout (공통 레이아웃)
import Layout from './components/layout/Layout';

const SessionTracker = ({ user, onLogout }) => {
  const location = useLocation();

  useEffect(() => {
    if (!user) return;
    if (isSessionExpired()) {
      onLogout();
      return;
    }
    touchActivity();
  }, [location.key, user, onLogout]);

  return null;
};

function App() {
  // localStorage에서 user 정보 불러와 초기 상태 설정
  const [user, setUser] = useState(readStoredUser());

  // 로그아웃: localStorage 비우고 user 상태도 null로
  const handleLogout = () => {
    clearSession();
    setUser(null);
  };

  //이미지 배경으로 설정
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--bg-image",
      `url(${process.env.PUBLIC_URL}/images/cover.jpg)`
    );

    return () => {
      document.documentElement.style.removeProperty("--bg-image");
    };
  }, []);

  useEffect(() => {
    const handleSessionExpired = () => {
      setUser(null);
    };

    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => {
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    };
  }, []);



  return (
    <div className="App">
      <BrowserRouter>
        <SessionTracker user={user} onLogout={handleLogout} />
        {/* Layout: Header/Footer 등 공통 UI (로그아웃 핸들러도 내려줌) */}
        <Layout user={user} onLogout={handleLogout}>
          <Routes>
            {/* Splash (표지): 첫 진입 화면 */}
            <Route path={ROUTES.SPLASH} element={<Splash />} />

            {/* 메인(Home): 로그인한 사용자만 접근 */}
             <Route path={ROUTES.HOME} element={<Home />} />

            {/* 로그인: 비로그인 사용자 접근 */}
            <Route
              path={ROUTES.LOGIN}
              element={<Login setUser={setUser} />}
            />

            {/* 회원가입: 비로그인 사용자 접근 */}
            <Route
              path={ROUTES.REGISTER}
              element={<Register />}
            />

            {/* 내 정보: 로그인한 사용자만 접근 */}
            <Route
              path={ROUTES.MYINFO}
              element={user ? <Myinfo /> : <Navigate to={ROUTES.LOGIN} />}
            />

            {/* 내 정보 수정: 로그인한 사용자만 접근 */}
            <Route
              path={ROUTES.MYINFO_EDIT}
              element={user ? <MyinfoEdit /> : <Navigate to={ROUTES.LOGIN} />}
            />

            {/* Chat: 로그인한 사용자만 접근 */}
            <Route
              path={ROUTES.CHAT}
              element={user ? <Chat /> : <Navigate to={ROUTES.LOGIN} />}
            />

              {/* Diary: 로그인한 사용자만 접근 */}
            <Route
              path={ROUTES.DIARY}
              element={user ? <Diary /> : <Navigate to={ROUTES.LOGIN} />}
            />
            <Route
              path={ROUTES.DIARY_NEW}
              element={user ? <DiaryNew /> : <Navigate to={ROUTES.LOGIN} />}
            />
            <Route
              path={ROUTES.DIARY_DETAIL}
              element={user ? <DiaryDetail /> : <Navigate to={ROUTES.LOGIN} />}
            />
            <Route
              path={ROUTES.DIARY_EDIT}
              element={user ? <DiaryEdit /> : <Navigate to={ROUTES.LOGIN} />}
            />

            <Route
              path={ROUTES.DIARY_V2}  
              element={user ? <DiaryV2 /> : <Navigate to={ROUTES.LOGIN} />}
            />

            <Route
              path={ROUTES.PLANT_DATA}
              element={<PlantData />}
            />

          </Routes>
        </Layout>
      </BrowserRouter>
    </div>
  );
}

export default App;
