import { useEffect, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { ROUTES } from "../../constants/routes";
import "./Header.css";

const Header = ({ user, onLogout }) => {
  const nav = useNavigate();
  const location = useLocation();
  const closeMenu = () => { };

  const navigateOrReload = (path) => {
    closeMenu();
    if (location.pathname === path) {
      window.location.reload();
    } else {
      nav(path);
    }
  };

  const goHome = () => navigateOrReload(ROUTES.HOME);
  const goMyinfo = () => navigateOrReload(ROUTES.MYINFO);
  const goChat = () => navigateOrReload(ROUTES.CHAT);
  const goPlantBoard = () => navigateOrReload(ROUTES.PLANTBOARD);
  const goLogin = () => navigateOrReload(ROUTES.LOGIN);
  const goPlantData = () => navigateOrReload(ROUTES.PLANT_DATA);

  const handleLogout = () => {
    closeMenu();
    if (onLogout) onLogout();
    nav(ROUTES.LOGIN);
  };

  return (
    <header className="header">
      {/* 상단: 로고 + 로그인 */}
      <div className="header-top">
        <div className="header-logo typo-title" onClick={goHome}>
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

      {/* 하단: 메뉴 */}
      <nav className="header-nav">
        <button className="header-link" onClick={goHome}>Home</button>
        <button className="header-link" onClick={goMyinfo} disabled={!user}>Profile</button>
        <button className="header-link" onClick={goChat} disabled={!user}>Chat</button>
        <button className="header-link" onClick={goPlantBoard} disabled={!user}>PlantBoard</button>
        <button className="header-link" onClick={goPlantData}>Data</button>
      </nav>
    </header>

  );
};

export default Header;
