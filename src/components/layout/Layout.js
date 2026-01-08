import Header from './Header';

const Layout = ({ user, children, onLogout }) => {
  return (
    <>
      {user && <Header user={user} onLogout={onLogout} />}
      <main>{children}</main>
    </>
  );
};

export default Layout;
