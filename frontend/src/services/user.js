import { readStoredUser } from "./session";

export const getStoredUsername = () => {
  try {
    const user = readStoredUser();
    return user?.username || "";
  } catch (error) {
    return "";
  }
};
