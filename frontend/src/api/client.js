import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "",
});

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("sds_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  config.headers["Ngrok-Skip-Browser-Warning"] = "true";
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) {
      sessionStorage.clear();
      window.location.href = "/";
    }
    return Promise.reject(error);
  }
);

export const mockWalletConnect = (address) =>
  api.post("/api/auth/mock-wallet", { address });

export const uploadFile = (formData, onUploadProgress) =>
  api.post("/api/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress,
  });

export const getUploadStatus = (id) =>
  api.get(`/api/upload/${id}/status`);

export const getArchive = () =>
  api.get("/api/archive");

export const reconstructFile = (manifestId) =>
  api.post(`/api/reconstruct/${manifestId}`, null, { responseType: "blob" });

export const getNodes = () =>
  api.get("/api/nodes");

export const deleteArchiveEntry = (manifestId) =>
  api.delete(`/api/archive/${manifestId}`);

export const getHealth = () =>
  api.get("/health");

export const generateThumbnail = (formData) =>
  api.post("/api/thumbnail", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

export const getSatelliteCatalog = () =>
  api.get("/api/satellite/catalog");

export const getSatelliteStatus = () =>
  api.get("/api/satellite/status");

export const reconstructSatelliteImage = (imgId) =>
  api.post(`/api/satellite/reconstruct/${imgId}`);

export default api;
