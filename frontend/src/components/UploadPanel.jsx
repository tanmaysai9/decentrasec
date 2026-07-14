import { useState, useCallback, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { uploadFile, getUploadStatus, getArchive, generateThumbnail } from "../api/client";
import useStore from "../store/useStore";

const IMAGE_EXTS = ["tif", "tiff", "png", "jpg", "jpeg", "bmp", "webp", "gif", "raw", "img"];

function isImageFile(f) {
  if (f.type && f.type.startsWith("image/")) return true;
  const ext = f.name.split(".").pop()?.toLowerCase() || "";
  return IMAGE_EXTS.includes(ext);
}

export default function UploadPanel() {
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState(null);
  const [preview, setPreview] = useState(null);
  const [thumbLoading, setThumbLoading] = useState(false);
  const [showLargePreview, setShowLargePreview] = useState(false);
  const thumbAbort = useRef(null);

  const setUploadStatus = useStore((s) => s.setUploadStatus);
  const setArchive = useStore((s) => s.setArchive);
  const navigate = useNavigate();

  useEffect(() => {
    if (!file) { setPreview(null); return; }
    if (file.type && file.type.startsWith("image/")) {
      const url = URL.createObjectURL(file);
      setPreview(url);
      return () => URL.revokeObjectURL(url);
    }
    if (isImageFile(file)) {
      setThumbLoading(true);
      setPreview(null);
      const ac = new AbortController();
      thumbAbort.current = ac;
      const slice = file.slice(0, 10 * 1024 * 1024);
      const fd = new FormData();
      fd.append("file", slice, file.name);
      generateThumbnail(fd)
        .then((res) => {
          if (!ac.signal.aborted && res.data.thumbnail) {
            setPreview(`data:image/jpeg;base64,${res.data.thumbnail}`);
          }
        })
        .catch(() => {})
        .finally(() => { if (!ac.signal.aborted) setThumbLoading(false); });
      return () => { ac.abort(); };
    }
    setPreview(null);
  }, [file]);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) setFile(e.dataTransfer.files[0]);
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setMessage(null);
    setUploadStatus(null);

    try {
      const fd = new FormData();
      fd.append("file", file);

      const res = await uploadFile(fd);
      const uploadId = res.data.id;

      const poll = setInterval(async () => {
        try {
          const status = await getUploadStatus(uploadId);
          setUploadStatus(status.data);
          if (status.data.stage === "done") {
            clearInterval(poll);
            setUploading(false);
            setMessage({ type: "success", text: "Upload complete. Redirecting to catalog..." });
            const archive = await getArchive();
            setArchive(archive.data.files || []);
            setTimeout(() => navigate("/satellite"), 1200);
          }
          if (status.data.stage === "error") {
            clearInterval(poll);
            setUploading(false);
            setMessage({ type: "error", text: status.data.error || "Upload failed" });
          }
        } catch {
          clearInterval(poll);
          setUploading(false);
          setMessage({ type: "error", text: "Status poll failed" });
        }
      }, 1000);
    } catch (e) {
      setMessage({ type: "error", text: e.response?.data?.detail || "Upload failed" });
      setUploading(false);
    }
  };

  return (
    <>
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-5">
        <h2 className="text-lg font-semibold text-gray-900">Upload Image</h2>

        <div
          onDrop={onDrop}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
            dragOver ? "border-primary-400 bg-primary-50" : "border-gray-300 hover:border-gray-400"
          }`}
          onClick={() => document.getElementById("file-input").click()}
        >
          <input
            id="file-input"
            type="file"
            accept="image/*,.tif,.tiff,.raw,.img,.png,.jpg,.jpeg,.bmp,.webp,.pdf,.zip"
            className="hidden"
            onChange={(e) => e.target.files[0] && setFile(e.target.files[0])}
          />
          {file ? (
            <div>
              {thumbLoading ? (
                <div className="mx-auto mb-2 w-16 h-16 rounded-lg bg-gray-100 flex items-center justify-center text-gray-400 animate-pulse">
                  ...
                </div>
              ) : preview ? (
                <img
                  src={preview}
                  alt="Preview"
                  className="mx-auto mb-2 max-h-40 rounded-lg object-contain cursor-pointer hover:opacity-80 transition-opacity"
                  onClick={(e) => { e.stopPropagation(); setShowLargePreview(true); }}
                />
              ) : (
                <div className="mx-auto mb-2 w-12 h-12 rounded-lg bg-gray-100 flex items-center justify-center text-gray-400 text-lg font-bold">
                  {file.name.split(".").pop()?.toUpperCase().slice(0, 4) || "?"}
                </div>
              )}
              <div className="text-sm font-medium text-gray-700">{file.name}</div>
              <div className="text-xs text-gray-400">{(file.size / 1024 / 1024).toFixed(2)} MB</div>
            </div>
          ) : (
            <div className="text-sm text-gray-500">Drag & drop an image here or click to browse</div>
          )}
        </div>

        <div>
          <label className="text-sm font-medium text-gray-600 block mb-1">Protection</label>
          <div className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-gray-50 text-gray-700">
            Secure Distribution
          </div>
          <p className="mt-1 text-xs text-gray-400">Your image is protected and distributed across storage nodes.</p>
        </div>

        {message && (
          <div className={`p-3 rounded-lg text-sm ${message.type === "error" ? "bg-red-50 border border-red-200 text-red-700" : "bg-green-50 border border-green-200 text-green-700"}`}>
            {message.text}
          </div>
        )}

        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className="w-full py-2.5 rounded-lg bg-primary-500 text-white font-medium hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {uploading ? "Processing..." : "Secure & Distribute"}
        </button>
      </div>

      {showLargePreview && preview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setShowLargePreview(false)}
        >
          <img
            src={preview}
            alt="Large preview"
            className="max-w-[90vw] max-h-[90vh] rounded-lg shadow-2xl"
          />
        </div>
      )}
    </>
  );
}
