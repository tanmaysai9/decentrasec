import { reconstructFile } from "../api/client";
import useStore from "../store/useStore";

const NODE_NAMES = ["NODE-1", "NODE-2", "NODE-3", "NODE-4", "NODE-5"];

function formatDuration(ms) {
  if (ms == null) return "\u2014";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function timeAgo(iso) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function ArchiveTable() {
  const archive = useStore((s) => s.archive);
  const reconstructingId = useStore((s) => s.reconstructingId);
  const setReconstructingId = useStore((s) => s.setReconstructingId);
  const reconstructDurations = useStore((s) => s.reconstructDurations);
  const setReconstructDuration = useStore((s) => s.setReconstructDuration);

  const handleReconstruct = async (id) => {
    setReconstructingId(id);
    try {
      const res = await reconstructFile(id);

      if (res.headers["content-type"]?.includes("json") || res.data.size === 0) {
        const text = await res.data.text();
        let msg = "Reconstruction failed";
        try { msg = JSON.parse(text).detail || msg; } catch {}
        alert(msg);
        return;
      }

      const durHeader = res.headers["x-reconstruct-duration-ms"];
      if (durHeader) setReconstructDuration(id, parseInt(durHeader, 10));

      const blob = new Blob([res.data]);
      const url = URL.createObjectURL(blob);
      const disposition = res.headers["content-disposition"] || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : "reconstructed_file";

      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      let detail = "Reconstruction failed";
      if (e.response?.data instanceof Blob) {
        try { detail = JSON.parse(await e.response.data.text()).detail || detail; } catch {}
      } else {
        detail = e.response?.data?.detail || detail;
      }
      alert(detail);
    } finally {
      setReconstructingId(null);
    }
  };

  if (archive.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 text-center text-gray-400 text-sm">
        No files in archive. Upload a file to encrypt and distribute its key.
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-4">
        Recent Activity
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400 uppercase tracking-wider border-b border-gray-100">
              <th className="pb-3 pr-4">File</th>
              <th className="pb-3 pr-4">Size</th>
              <th className="pb-3 pr-4">Shares</th>
              <th className="pb-3 pr-4">Nodes</th>
              <th className="pb-3 pr-4">Upload</th>
              <th className="pb-3 pr-4">Reconstruct</th>
              <th className="pb-3 pr-4">Time</th>
              <th className="pb-3">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {archive.map((f) => (
              <tr key={f.id} className="hover:bg-gray-50">
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-2">
                    {f.thumbnail ? (
                      <img src={`data:image/jpeg;base64,${f.thumbnail}`} alt="" className="w-8 h-8 rounded object-cover shrink-0" />
                    ) : (
                      <div className="w-8 h-8 rounded bg-gray-100 flex items-center justify-center text-gray-400 text-xs shrink-0">?</div>
                    )}
                    <div>
                      <div className="font-medium text-gray-900 truncate max-w-[140px]">{f.file_name}</div>
                    </div>
                  </div>
                </td>
                <td className="py-3 pr-4 text-gray-500 whitespace-nowrap">{formatSize(f.original_size)}</td>
                <td className="py-3 pr-4">
                  <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full">{f.total_shares_n} shares</span>
                </td>
                <td className="py-3 pr-4">
                  <div className="flex gap-1">
                    {NODE_NAMES.map((n) => (
                      <div
                        key={n}
                        className={`w-2.5 h-2.5 rounded-full ${
                          f.nodes?.[n]?.healthy ? "bg-green-500" : "bg-red-400"
                        }`}
                        title={`${n}: ${f.nodes?.[n]?.cid?.slice(0, 12) || "N/A"}`}
                      />
                    ))}
                  </div>
                </td>
                <td className="py-3 pr-4 text-gray-500 whitespace-nowrap text-xs font-mono">
                  {formatDuration(f.upload_duration_ms)}
                </td>
                <td className="py-3 pr-4 text-gray-500 whitespace-nowrap text-xs font-mono">
                  {formatDuration(reconstructDurations[f.id])}
                </td>
                <td className="py-3 pr-4 text-gray-400 whitespace-nowrap">{timeAgo(f.created_at)}</td>
                <td className="py-3">
                  <button
                    onClick={() => handleReconstruct(f.id)}
                    disabled={reconstructingId === f.id}
                    className="text-xs bg-primary-500 text-white px-3 py-1.5 rounded-lg hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {reconstructingId === f.id ? "Working..." : "Reconstruct"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
