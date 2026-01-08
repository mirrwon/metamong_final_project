//지금 당장 쓸 임시(authService MOCK 버전)


const USE_MOCK = true; // 🔴 지금은 무조건 true

const MOCK_USER_KEY = "mock_registered_user";

// 로그인
export const login = async (data) => {
  if (USE_MOCK) {
    const saved = JSON.parse(localStorage.getItem(MOCK_USER_KEY));

    if (!saved) {
      return Promise.reject(new Error("가입된 사용자 없음"));
    }

    if (
      saved.username !== data.username ||
      saved.password !== data.password
    ) {
      return Promise.reject(new Error("아이디/비밀번호 불일치"));
    }

    return Promise.resolve({
      data: {
        username: saved.username,
        email: saved.email,
        name: saved.name,
        accessToken: "mock-token",
      },
    });
  }
};

// 회원가입
export const register = async (payload) => {
  if (USE_MOCK) {
    localStorage.setItem(MOCK_USER_KEY, JSON.stringify(payload));
    return Promise.resolve({ data: { success: true } });
  }
};
