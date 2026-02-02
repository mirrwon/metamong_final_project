import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { ROUTES } from "../../constants/routes";
import "./Header.css";

const Header = ({ user, onLogout }) => {
  const nav = useNavigate();
  const location = useLocation();
  const [isLoading, setIsLoading] = useState(false);

  const closeMenu = () => {
    // 메뉴(햄버거 등) 닫는 로직 있으면 여기
  };

  const startLoadingThen = (fn) => {
    setIsLoading(true);

    window.setTimeout(() => {
      fn();
      // ✅ nav 이동이면 컴포넌트가 바뀌면서 자연스럽게 사라지지만,
      // ✅ reload는 아래에서 바로 새로고침되어 의미 없음.
      // 그래도 안전하게 꺼주고 싶으면 유지:
      setIsLoading(false);
    }, 400);
  };

  const navigateOrReload = (path) => {
    closeMenu();

    // ✅ 같은 페이지면: 로딩 연출 후 reload
    if (location.pathname === path) {
      startLoadingThen(() => window.location.reload());
      return;
    }

    // ✅ 다른 페이지면: 로딩 연출 후 이동
    startLoadingThen(() => nav(path));
  };

  const goHome = () => navigateOrReload(ROUTES.HOME);
  const goMyinfo = () => navigateOrReload(ROUTES.MYINFO);
  const goChat = () => navigateOrReload(ROUTES.UPLOAD);
  const goPlantBoard = () => navigateOrReload(ROUTES.PLANTBOARD);
  const goPlantData = () => navigateOrReload(ROUTES.PLANT_DATA);
  const goLogin = () => navigateOrReload(ROUTES.LOGIN);

  const handleLogout = () => {
    closeMenu();
    if (onLogout) onLogout();
    startLoadingThen(() => nav(ROUTES.LOGIN));
  };

  return (
    <>
      {isLoading && (
        <div className="loading-overlay" aria-live="polite" aria-busy="true">
          <div className="loading-spinner" />
        </div>
      )}

      <header className="header">
        <div className="header-top">
          <div className="header-logo typo-title" onClick={goHome} role="button" tabIndex={0}>
            Ditto
          </div>

          <button
            className="header-auth"
            type="button"
            onClick={user ? handleLogout : goLogin}
          >
            {user ? "logout" : "login"}
          </button>
        </div>

        <nav className="header-nav">
          <button className="header-link" type="button" onClick={goHome}>
            Home
          </button>

          <button
            className="header-link"
            type="button"
            onClick={goMyinfo}
            disabled={!user}
          >
            Profile
          </button>

          <button
            className="header-link"
            type="button"
            onClick={goChat}
            disabled={!user}
          >
            Chat
          </button>

          <button
            className="header-link"
            type="button"
            onClick={goPlantBoard}
            disabled={!user}
          >
            PlantBoard
          </button>

          <button className="header-link" type="button" onClick={goPlantData}>
            Data
          </button>
        </nav>
      </header>
    </>
  );
};

export default Header;
