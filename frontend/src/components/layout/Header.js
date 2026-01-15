import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ROUTES } from "../../constants/routes";
import "./Header.css";

const Header = ({ user, onLogout }) => {
  const nav = useNavigate();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setIsMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const closeMenu = () => setIsMenuOpen(false);


  const goHome = () => { closeMenu(); nav(ROUTES.HOME); };
  const goMyinfo = () => { closeMenu(); nav(ROUTES.MYINFO); };
  const goChat = () => { closeMenu(); nav(ROUTES.CHAT); };
  const goDiary = () => { closeMenu(); nav(ROUTES.DIARY); };
  const goLogin = () => { closeMenu(); nav(ROUTES.LOGIN); };

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
      <button className="header-link" onClick={goDiary} disabled={!user}>Diary</button>
    </nav>
  </header>

  );
};

export default Header;
