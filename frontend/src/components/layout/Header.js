import { useEffect, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { ROUTES } from "../../constants/routes";
import "./Header.css";

const Header = ({ user, onLogout }) => {
  const nav = useNavigate();
  const location = useLocation();
  const [isLoading, setIsLoading] = useState(false);

  const closeMenu = () => {
  };

  const startLoadingThen = (fn) => {
    setIsLoading(true);

    window.setTimeout(() => {
      fn();

      setIsLoading(false);
    }, 400);
  };

  const openInNewTab = (path, beforeOpen) => {
    if (beforeOpen) beforeOpen();
    window.open(path, "_blank", "noopener");
  };

  const handleNavClick = (path, beforeNavigate) => (e) => {
    if (e?.ctrlKey || e?.metaKey) {
      e.preventDefault();
      openInNewTab(path, beforeNavigate);
      return;
    }
    if (beforeNavigate) beforeNavigate();
    navigateOrReload(path);
  };

  const handleNavAuxClick = (path, beforeNavigate) => (e) => {
    if (e?.button === 1) {
      e.preventDefault();
      openInNewTab(path, beforeNavigate);
    }
  };

  const handleNavMouseDown = (path, beforeNavigate) => (e) => {
    if (e?.button === 1) {
      e.preventDefault();
      openInNewTab(path, beforeNavigate);
    }
  };

  const navigateOrReload = (path) => {
    closeMenu();

    if (location.pathname === path) {
      startLoadingThen(() => window.location.reload());
      return;
    }

    startLoadingThen(() => nav(path));
  };

  const goPlantBoard = () => {
    try {
      localStorage.removeItem("plantboard_selected_plant");
      localStorage.setItem("plantboard_active_view", "timelog");
    } catch {}
  };
  const goLogin = () => navigateOrReload(ROUTES.LOGIN);
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

    <header className={`header ${location.pathname === ROUTES.HOME ? "header--home" : "header--default"}`}>
    <div className="header-top">
      <div
        className="header-logo typo-title"
        onClick={handleNavClick(ROUTES.HOME)}
        onAuxClick={handleNavAuxClick(ROUTES.HOME)}
        onMouseDown={handleNavMouseDown(ROUTES.HOME)}
        role="button"
        tabIndex={0}
      >
        Ditto
      </div>

      <nav className="header-nav">
        <button
          className="header-link"
          type="button"
          onClick={handleNavClick(ROUTES.HOME)}
          onAuxClick={handleNavAuxClick(ROUTES.HOME)}
          onMouseDown={handleNavMouseDown(ROUTES.HOME)}
        >
          Home
        </button>

        <button
          className="header-link"
          type="button"
          onClick={handleNavClick(ROUTES.MYINFO)}
          onAuxClick={handleNavAuxClick(ROUTES.MYINFO)}
          onMouseDown={handleNavMouseDown(ROUTES.MYINFO)}
          disabled={!user}
        >
          Profile
        </button>

        <button
          className="header-link"
          type="button"
          onClick={handleNavClick(ROUTES.UPLOAD)}
          onAuxClick={handleNavAuxClick(ROUTES.UPLOAD)}
          onMouseDown={handleNavMouseDown(ROUTES.UPLOAD)}
          disabled={!user}
        >
          Chat
        </button>

        <button
          className="header-link"
          type="button"
          onClick={handleNavClick(ROUTES.PLANTBOARD, goPlantBoard)}
          onAuxClick={handleNavAuxClick(ROUTES.PLANTBOARD, goPlantBoard)}
          onMouseDown={handleNavMouseDown(ROUTES.PLANTBOARD, goPlantBoard)}
          disabled={!user}
        >
          PlantBoard
        </button>

        <button
          className="header-link"
          type="button"
          onClick={handleNavClick(ROUTES.PLANT_DATA)}
          onAuxClick={handleNavAuxClick(ROUTES.PLANT_DATA)}
          onMouseDown={handleNavMouseDown(ROUTES.PLANT_DATA)}
        >
          Data
        </button>

        <button
          className="header-link"
          type="button"
          onClick={handleNavClick(ROUTES.MAP)}
          onAuxClick={handleNavAuxClick(ROUTES.MAP)}
          onMouseDown={handleNavMouseDown(ROUTES.MAP)}
        >
          Map
        </button>
        <button
          className="header-link header-auth"
          type="button"
          onClick={user ? handleLogout : goLogin}
        >
          {user ? "logout" : "login"}
        </button>
      </nav>
    </div>
      </header>
    </>
  );
};

export default Header;
