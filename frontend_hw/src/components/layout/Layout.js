import { useLocation } from "react-router-dom";
import Header from "./Header";
import { ROUTES } from "../../constants/routes";

const Layout = ({ user, children, onLogout }) => {
  const { pathname } = useLocation();

  //헤더 숨길 페이지들
  const hideHeaderPaths = [ROUTES.SPLASH, ROUTES.LOGIN, ROUTES.REGISTER];
  const shouldHideHeader = hideHeaderPaths.includes(pathname);

  return (
    <>
      {!shouldHideHeader && user && <Header user={user} onLogout={onLogout} />}
      <main>{children}</main>
    </>
  );
};

export default Layout;