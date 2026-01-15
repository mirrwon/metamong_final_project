import { useState } from "react";

const JoinLogin = ({ onSubmit }) => {
  const [formData, setFormData] = useState({
    username: "",
    password: "",
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData({
      ...formData,
      [name]: value,
    });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(formData);
  };

  return (
    <form className="join-login" onSubmit={handleSubmit}>
      <div className="join-login__row">
        <input
          className="ui-input"
          type="text"
          name="username"
          value={formData.username}
          onChange={handleChange}
          placeholder="아이디"
        />
      </div>

      <div className="join-login__row">
        <input
          className="ui-input"
          type="password"
          name="password"
          value={formData.password}
          onChange={handleChange}
          placeholder="비밀번호"
        />
      </div>

      <div className="ui-line login-bottom-line" />

      <button className="ui-btn ui-btn-primary" type="submit">
        로그인
      </button>
    </form>
  );
};

export default JoinLogin;
