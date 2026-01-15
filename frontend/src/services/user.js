export const getStoredUsername = () => {
  try {
    const raw = localStorage.getItem("user");
    if (!raw) return "";
    const user = JSON.parse(raw);
    return user?.username || "";
  } catch (error) {
    return "";
  }
};