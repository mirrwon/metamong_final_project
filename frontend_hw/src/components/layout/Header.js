import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Button from "../common/Button";
import { ROUTES } from "../../constants/routes";

const Header = ({ user, onLogout }) => {
  const nav = useNavigate();

  // Menu 드롭다운 열림/닫힘 상태
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  // 드롭다운 영역 참조 (바깥 클릭 감지용)
  const menuRef = useRef(null);

  useEffect(() => {
    // 메뉴 영역 밖 클릭 시 드롭다운 닫기
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setIsMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);

    // 컴포넌트 언마운트 시 이벤트 제거
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const closeMenu = () => {
    setIsMenuOpen(false);
  };

  const toggleMenu = () => {
    setIsMenuOpen((prev) => !prev);
  };

  // 홈 이동
  const goHome = () => {
    closeMenu();
    nav(ROUTES.HOME);
  };

  // 프로필(내정보)
  const goMyinfo = () => {
    closeMenu();
    nav(ROUTES.MYINFO);
  };

  // 식물 추천
  const goPlantPick = () => {
    closeMenu();
    nav(ROUTES.PLANT_PICK);
  };

  // 다이어리
  const goDiary = () => {
    closeMenu();
    nav(ROUTES.DIARY);
  };

  // 로그아웃
  const handleLogout = () => {
    closeMenu();
    if (onLogout) onLogout();
    nav(ROUTES.LOGIN);
  };

  // 로그인 전에는 헤더 자체를 렌더링하지 않음
  if (!user) return null;

  return (
    <header className="header">
      {/* 로고 */}
      <div className="logo" onClick={goHome}>
        PlantGuide AI
      </div>

      {/* 오른쪽 메뉴 */}
      <nav className="nav-links">
        <Button text="Main" type="primary" onClick={goHome} />

        <div className="menu-wrapper" ref={menuRef}>
          <Button text="Menu" type="primary" onClick={toggleMenu} />

          {isMenuOpen && (
            <div className="menu-dropdown">
              <Button text="Profile" type="primary" onClick={goMyinfo} />

              <Button text="Plant Pick" type="primary" onClick={goPlantPick} />

              <Button text="Diary" type="primary" onClick={goDiary} />

              <Button text="Logout" type="primary" onClick={handleLogout} />
            </div>
          )}
        </div>
      </nav>
    </header>
  );
};

export default Header;
