import './App.css';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useState } from 'react';
import { ROUTES } from './constants/routes';

// pages (라우트에 직접 연결되는 페이지)
import Home from './pages/Home';
import Login from './pages/auth/Login';
import Register from './pages/auth/Register';
import Myinfo from './pages/Myinfo';
import MyinfoEdit from './pages/MyinfoEdit';
// import PlantPick from './pages/PlantPick';
import Chat from './components/plantpick/Chat';

// Diary pages
import Diary from './pages/Diary';
import DiaryNew from './pages/DiaryNew';
import DiaryDetail from './pages/DiaryDetail';
import DiaryEdit from './pages/DiaryEdit';

// Test
import Test from "./pages/test";


// layout (공통 레이아웃)
import Layout from './components/layout/Layout';

function App() {
  // localStorage에서 user 정보 불러와 초기 상태 설정
  const [user, setUser] = useState(JSON.parse(localStorage.getItem('user')));

  // 로그아웃: localStorage 비우고 user 상태도 null로
  const handleLogout = () => {
    localStorage.removeItem('user');
    setUser(null);
  };

  return (
    <div className="App">
      <BrowserRouter>
        {/* Layout: Header/Footer 등 공통 UI (로그아웃 핸들러도 내려줌) */}
        <Layout user={user} onLogout={handleLogout}>
          <Routes>
            {/* 메인(Home): 로그인한 사용자만 접근 */}
            <Route
              path={ROUTES.HOME}
              element={user ? <Home /> : <Navigate to={ROUTES.LOGIN} />}
            />

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

            {/* Plant Pick: 로그인한 사용자만 접근 */}
            <Route
              path={ROUTES.PLANT_PICK}
              element={user ? <Chat /> : <Navigate to={ROUTES.LOGIN} />}
            />

              {/* ✅ Diary: 로그인한 사용자만 접근 */}
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

            <Route path="/test" element={<Test />} />

            <Route path="/chat" element={<Chat />} />

          </Routes>
        </Layout>
      </BrowserRouter>
    </div>
  );
}

export default App;
