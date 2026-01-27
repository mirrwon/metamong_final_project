const KEY = "pendingDiaryPhoto";

export function readPendingDiaryPhoto() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function clearPendingDiaryPhoto() {
  try {
    localStorage.removeItem(KEY);
  } catch {}
}
