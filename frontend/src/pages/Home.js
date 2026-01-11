import { useNavigate } from 'react-router-dom';
import { useState } from 'react';
import Button from '../components/common/Button';
import { ROUTES } from '../constants/routes';

const Home = () => {
  const nav = useNavigate();

  // 임시 사용자 정보 (나중에 로그인 연동)
  const user = {
    username: 'username',
    email: 'onlywon@example.com',
  };

  // 임시 다이어리 데이터 (나중에 API 연동)
  const diaryPosts = [
    {
      id: 1,
      date: '2026-01-06',
      title: '테라스 식물 물주기',
      content: '햇빛이 좋아서 잎이 더 싱싱해진 느낌',
    },
    {
      id: 2,
      date: '2026-01-05',
      title: '거실 식물 배치 고민',
      content: '창가 쪽이 좋을지 테이블 옆이 좋을지',
    },
    {
      id: 3,
      date: '2026-01-04',
      title: '새 화분 도착',
      content: '예쁘긴 한데 사이즈가 생각보다 크다',
    },
  ];

  const [hoveredDiaryId, setHoveredDiaryId] = useState(null);

  const hoveredDiary = diaryPosts.find(
    (post) => post.id === hoveredDiaryId
  );

  
  /* ================= 이동 함수 (ROUTES 기준 통일) ================= */
  const goMyinfo = () => {
    nav(ROUTES.MYINFO);
  };

  const goChat = () => {
    nav(ROUTES.CHAT);
  };

  const goDiary = () => {
    nav(ROUTES.DIARY);
  };

  const goDiaryDetail = (postId) => {
    nav(`${ROUTES.DIARY}/${postId}`);
  };

  /* ================= hover 처리 ================= */
  const handleEnterDiaryCard = (postId) => {
    setHoveredDiaryId(postId);
  };

  const handleLeaveDiaryCard = () => {
    setHoveredDiaryId(null);
  };

 return (
    <>
      {/* 메인 이미지 + 앱 제목 */}
      <h1>PlantGuide AI</h1>

      {/* 프로필 탭 */}
      <section>
        <h2>Profile</h2>
        <p>ID: {user.username}</p>
        <p>Email: {user.email}</p>

        <Button
          text="Profile"
          type="primary"
          onClick={goMyinfo}
        />
      </section>

      {/* AI Plant Pick 탭 */}
      <section>
        <h2>AI Plant Pick</h2>
        <p>
          실내 공간 사진을 분석해 분위기에 어울리는 식물을 추천하고,
          배치했을 때의 모습을 미리 확인할 수 있는 서비스입니다.
        </p>

        <Button
          text="Start"
          type="primary"
          onClick={goChat}
        />
      </section>

      {/* 다이어리 탭 */}
      <section>
        <h2>Diary</h2>

        <Button
          text="Diary"
          type="primary"
          onClick={goDiary}
        />

        {/* 다이어리 카드 목록 */}
        <ul>
          {diaryPosts.map((post) => (
            <li
              key={post.id}
              onMouseEnter={() => handleEnterDiaryCard(post.id)}
              onMouseLeave={handleLeaveDiaryCard}
              onClick={() => goDiaryDetail(post.id)}
            >
              <p>{post.date}</p>
              <p>{post.title}</p>
            </li>
          ))}
        </ul>

        {/* hover 시 미리보기 */}
        {hoveredDiary && (
          <div>
            <h3>{hoveredDiary.title}</h3>
            <p>{hoveredDiary.date}</p>
            <p>{hoveredDiary.content}</p>
          </div>
        )}
      </section>
    </>
  );
};

export default Home;
