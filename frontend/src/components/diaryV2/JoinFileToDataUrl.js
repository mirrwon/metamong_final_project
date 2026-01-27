
export function JoinFileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    if (!file) return reject(new Error("No file"));
    if (!file.type?.startsWith("image/")) return reject(new Error("Not an image"));

    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("FileReader error"));
    reader.readAsDataURL(file);
  });
}
