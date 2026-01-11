import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/common/Button';
import { ROUTES } from '../constants/routes';

const Myinfo = () => {
  const nav = useNavigate();

  // TODO: 로그인 연동 후 서버 데이터로 교체
  const myinfo = useMemo(
    () => ({
      profileImageUrl: '',
      username: 'hyewon',
      age: 30,
      birthDate: '1994-10-19',
      phone: '010-1234-5678',
      email: 'onlywon@gmail.com',
    }),
    []
  );

  // 내 정보 수정 페이지 이동
  const goEditMyinfo = () => {
    nav(ROUTES.MYINFO_EDIT);
  };

  return (
    <>
      <h1>My Info</h1>

      <section>
        <div>
          {myinfo.profileImageUrl ? (
            <img
              src={myinfo.profileImageUrl}
              alt="내 정보 사진"
              width="120"
              height="120"
            />
          ) : (
            <div>[내 정보 이미지]</div>
          )}
        </div>

        <div>
          <p>아이디: {myinfo.username}</p>
          <p>나이: {myinfo.age}</p>
          <p>생년월일: {myinfo.birthDate}</p>
          <p>연락처: {myinfo.phone}</p>
          <p>e-mail: {myinfo.email}</p>
        </div>

        <Button
          text="내 정보 수정"
          type="primary"
          onClick={goEditMyinfo}
        />
      </section>
    </>
  );
};

export default Myinfo;
