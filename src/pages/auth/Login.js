import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../../services/authService';
import JoinLogin from '../../components/auth/JoinLogin';
// import './Login.css';
import Button from '../../components/common/Button';

const Login = ({setUser}) => {

  const nav = useNavigate();

   //로그인 실패 메시지 상태
  const [error, setError] = useState('');

  //LoginForm에서 formData를 받아오는 함수
  const handleLogin = async (formData) => {
    try {
      setError(''); // 이전 에러 초기화

      const res = await login(formData);

      //로그인 성공 시 localStorage에 user정보 저장
      localStorage.setItem('user', JSON.stringify(res.data));

      //App.js의 user 상태 업데이트
      setUser(res.data)

      //성공 시 메인 이동
      nav('/');
    } catch (err) {
      setError('아이디 또는 비밀번호가 올바르지 않습니다.');
    }
  };

    const goRegister = () => {
      nav('/register')
    }


  return (
    <div className="login-page">
      <h2>로그인</h2>
      <JoinLogin onSubmit={handleLogin} />
      {error && <p className="login-error">{error}</p>}
      <Button
        text="회원가입"
        type="primary"
        onClick={goRegister}/>        
     
    </div>
  );
};

export default Login;