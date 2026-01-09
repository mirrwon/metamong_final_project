import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/common/Button';
import { ROUTES } from '../constants/routes';

const MyinfoEdit = () => {
  const nav = useNavigate();

  // TODO: 로그인 연동 후 서버에서 가져온 기존 사용자 정보로 교체
  const initialMyinfo = useMemo(
    () => ({
      profileImageUrl: '',
      username: 'hyewon',
      password: '',
      name: '혜원',
      birthDate: '1994-10-19',
      phone: '010-1234-5678',
      email: 'onlywon@gmail.com',
    }),
    []
  );

  const [myinfo, setMyinfo] = useState(initialMyinfo);
  const [profileImageFile, setProfileImageFile] = useState(null);

  const handleChangeMyinfo = (e) => {
    const { name, value } = e.target;

    setMyinfo((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleChangeProfileImage = (e) => {
    const file = e.target.files?.[0] ?? null;
    setProfileImageFile(file);

    // TODO: 업로드/미리보기 필요하면 여기서 처리
    // 미리보기까지 하고 싶으면 URL.createObjectURL(file) 사용
  };

  const goMyinfo = (e) => {
    // form 안에서 submit 되는 것 방지
    if (e) e.preventDefault();
    nav(ROUTES.MYINFO);
  };

  const handleSubmitMyinfoEdit = (e) => {
    e.preventDefault();

    // TODO: API 연동 (예: myinfoService.updateMyinfo(myinfo, profileImageFile))
    // 성공 시 내 정보 페이지로 이동
    nav(ROUTES.MYINFO);
  };

  return (
    <>
      <h1>My Info Edit</h1>

      <form onSubmit={handleSubmitMyinfoEdit}>
        <section>
          <h2>프로필 사진</h2>

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
            <label htmlFor="profileImage">프로필 사진 수정</label>
            <input
              id="profileImage"
              type="file"
              accept="image/*"
              onChange={handleChangeProfileImage}
            />
            {profileImageFile && <p>선택된 파일: {profileImageFile.name}</p>}
          </div>
        </section>

        <section>
          <h2>기본 정보</h2>

          <div>
            <label htmlFor="username">아이디</label>
            <input
              id="username"
              name="username"
              type="text"
              value={myinfo.username}
              onChange={handleChangeMyinfo}
              readOnly
            />
            <p>아이디는 수정할 수 없어요.</p>
          </div>

          <div>
            <label htmlFor="password">비밀번호</label>
            <input
              id="password"
              name="password"
              type="password"
              value={myinfo.password}
              onChange={handleChangeMyinfo}
              placeholder="변경할 비밀번호를 입력하세요"
              autoComplete="new-password"
            />
          </div>

          <div>
            <label htmlFor="name">이름</label>
            <input
              id="name"
              name="name"
              type="text"
              value={myinfo.name}
              onChange={handleChangeMyinfo}
            />
          </div>

          <div>
            <label htmlFor="birthDate">생년월일</label>
            <input
              id="birthDate"
              name="birthDate"
              type="date"
              value={myinfo.birthDate}
              onChange={handleChangeMyinfo}
            />
          </div>

          <div>
            <label htmlFor="phone">연락처</label>
            <input
              id="phone"
              name="phone"
              type="tel"
              value={myinfo.phone}
              onChange={handleChangeMyinfo}
              placeholder="010-0000-0000"
            />
          </div>

          <div>
            <label htmlFor="email">이메일</label>
            <input
              id="email"
              name="email"
              type="email"
              value={myinfo.email}
              onChange={handleChangeMyinfo}
            />
          </div>
        </section>

        <div>
          <Button text="취소" type="secondary" onClick={goMyinfo} />
          <button type="submit">수정</button>
        </div>
      </form>
    </>
  );
};

export default MyinfoEdit;
