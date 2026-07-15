import { useState, useEffect, useCallback, useMemo } from "react";
import { reconstructSatelliteImage } from "../api/client";

function NoiseImage({ seed, size = 42, grayscale = false }) {
  const dataUrl = useMemo(() => {
    const c = document.createElement("canvas");
    c.width = size;
    c.height = size;
    const ctx = c.getContext("2d");
    const imgData = ctx.createImageData(size, size);
    let s = ((seed || 1) * 2654435761) >>> 0;
    for (let i = 0; i < imgData.data.length; i += 4) {
      s = (s * 1103515245 + 12345) >>> 0;
      const r = s & 0xff;
      const g = grayscale ? r : (s >> 8) & 0xff;
      const b = grayscale ? r : (s >> 16) & 0xff;
      imgData.data[i] = r;
      imgData.data[i + 1] = g;
      imgData.data[i + 2] = b;
      imgData.data[i + 3] = 255;
    }
    ctx.putImageData(imgData, 0, 0);
    return c.toDataURL();
  }, [seed, size, grayscale]);

  return (
    <img
      src={dataUrl}
      alt="noise"
      className="rounded border border-gray-200 shrink-0"
      style={{ width: size, height: size }}
      title="Decoy noise"
    />
  );
}

const SENSOR_COLORS = {
  "S1-SAR": { bg: "bg-blue-100", text: "text-blue-700", border: "border-blue-200" },
  "S2-MSI": { bg: "bg-green-100", text: "text-green-700", border: "border-green-200" },
  "S2-RGB": { bg: "bg-teal-100", text: "text-teal-700", border: "border-teal-200" },
  "S2-NIR": { bg: "bg-amber-100", text: "text-amber-700", border: "border-amber-200" },
};

function EssentialCell({ share }) {
  if (!share) return <td className="sat-cell sat-cell-essential"><span className="text-gray-300 text-lg">—</span></td>;
  return (
    <td className="sat-cell sat-cell-essential">
      <div className="flex flex-col gap-1.5 items-center py-1">
        <div className="w-10 h-10 rounded-full bg-amber-100 border-2 border-amber-300 flex items-center justify-center text-amber-600 font-bold text-lg shrink-0">
          ★
        </div>
        <span className="font-mono text-sm text-gray-500">0x{share.hex_prefix}</span>
        <span className="text-xs font-bold text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
          ESSENTIAL
        </span>
        <span className="font-mono text-xs text-amber-400">LOCAL</span>
      </div>
    </td>
  );
}

function ShareCell({ share }) {
  if (!share) return <td className="sat-cell sat-cell-share"><span className="text-gray-300 text-lg">—</span></td>;
  const seed = (share.cid || share.node || "42").split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  return (
    <td className="sat-cell sat-cell-share">
      <div className="flex items-start gap-2">
        <NoiseImage seed={seed} size={42} />
        <div className="flex flex-col gap-1 items-start">
          <span className="font-mono text-base text-gray-700 font-semibold">
            {share.node || "—"}
          </span>
          <span className="font-mono text-sm text-gray-500">
            {share.node_ip || "—"}
          </span>
          <span className="font-mono text-sm text-gray-400">
            {share.cid ? `${share.cid.slice(0, 16)}...` : ""}
          </span>
        </div>
      </div>
    </td>
  );
}

function SensorBadge({ sensor }) {
  const c = SENSOR_COLORS[sensor] || SENSOR_COLORS["S1-SAR"];
  return (
    <span className={`inline-block text-lg font-semibold px-3 py-1.5 rounded border ${c.bg} ${c.text} ${c.border} whitespace-nowrap`}>
      {sensor}
    </span>
  );
}

function SkeletonRow({ nNodes }) {
  return (
    <tr className="animate-pulse">
      <td className="sat-cell"><div className="w-24 h-24 bg-gray-100 rounded" /></td>
      <td className="sat-cell"><div className="h-8 w-24 bg-gray-100 rounded" /></td>
      <td className="sat-cell sat-cell-essential"><div className="flex flex-col gap-1.5 items-center"><div className="h-5 w-24 bg-gray-100 rounded" /><div className="h-4 w-16 bg-gray-50 rounded" /></div></td>
      {Array.from({ length: nNodes }).map((_, i) => (
        <td key={i} className="sat-cell sat-cell-share">
          <div className="flex flex-col gap-1.5">
            <div className="h-5 w-36 bg-gray-100 rounded" />
            <div className="h-4 w-24 bg-gray-50 rounded" />
          </div>
        </td>
      ))}
      <td className="sat-cell"><div className="h-10 w-28 bg-gray-100 rounded" /></td>
    </tr>
  );
}

function ReconstructModal({ image, reconstructedPng, shareDetails, durationMs, sensor, season, onClose }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />
      <div
        className="relative bg-white rounded-lg shadow-2xl border border-gray-200 max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-8 py-5 border-b border-gray-100">
          <div>
            <h3 className="text-xl font-semibold text-gray-900">Reconstructed Image</h3>
            <p className="text-lg text-gray-500 mt-1">{image.id} &middot; {sensor} &middot; {season} &middot; {durationMs}ms</p>
          </div>
          <button
            onClick={onClose}
            className="w-10 h-10 flex items-center justify-center rounded-md hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4l12 12M16 4L4 16" /></svg>
          </button>
        </div>

        <div className="p-8">
          <div className="flex justify-center">
            <div>
              <div className="border border-gray-200 rounded p-1 bg-gray-50 inline-block">
                {reconstructedPng ? (
                  <img src={reconstructedPng} alt="reconstructed" className="w-[420px] h-[420px] object-cover" />
                ) : (
                  <div className="w-[420px] h-[420px] flex items-center justify-center text-gray-300 text-lg">No image</div>
                )}
              </div>
            </div>
          </div>

          {shareDetails && shareDetails.length > 0 && (
            <div className="mt-8">
              <p className="text-base uppercase tracking-wider text-gray-400 mb-3 font-medium">Share Breakdown</p>
              <div className="border border-gray-200 rounded overflow-hidden">
                <table className="w-full text-lg">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="text-left px-5 py-3 text-gray-500 font-medium text-lg">Share</th>
                      <th className="text-left px-5 py-3 text-gray-500 font-medium text-lg">Location</th>
                      <th className="text-left px-5 py-3 text-gray-500 font-medium text-lg">Node IP</th>
                      <th className="text-left px-5 py-3 text-gray-500 font-medium text-lg">CID</th>
                      <th className="text-left px-5 py-3 text-gray-500 font-medium text-lg">Hex</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shareDetails.map((s, i) => (
                      <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-gray-50/50"}>
                        <td className="px-5 py-3">
                          <span className={`font-medium text-lg ${s.node === "LOCAL" ? "text-amber-600" : "text-gray-600"}`}>
                            {i === 0 ? "Essential (local)" : `NLSS Piece ${i}`}
                          </span>
                        </td>
                        <td className="px-5 py-3">
                          {s.node === "LOCAL" ? (
                            <span className="text-amber-600 bg-amber-50 border border-amber-200 px-2 py-1 rounded text-base font-semibold">
                              LOCAL
                            </span>
                          ) : (
                            <span className="text-gray-700 text-lg">{s.node}</span>
                          )}
                        </td>
                        <td className="px-5 py-3 font-mono text-gray-500 text-lg">
                          {s.node === "LOCAL" ? "— (local disk)" : s.node_ip}
                        </td>
                        <td className="px-5 py-3 font-mono text-gray-500 text-lg">
                          {s.node === "LOCAL" ? "— (not on IPFS)" : `${s.cid.slice(0, 16)}...`}
                        </td>
                        <td className="px-5 py-3 font-mono text-gray-500 text-lg">0x{s.hex_prefix}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const RECONSTRUCT_CACHE_KEY = "sds_reconstruct_cache";

export default function SatelliteTable() {
  const [images, setImages] = useState([]);
  const [nodes, setNodes] = useState({});
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterSensor, setFilterSensor] = useState("all");
  const [sortCol, setSortCol] = useState("index");
  const [sortDir, setSortDir] = useState("asc");
  const [reconstructingId, setReconstructingId] = useState(null);
  const [modal, setModal] = useState(null);
  const [largeThumb, setLargeThumb] = useState(null);

  useEffect(() => {
    try {
      const cached = sessionStorage.getItem(RECONSTRUCT_CACHE_KEY);
      if (cached) {
        const d = JSON.parse(cached);
        setModal({
          image: { id: d.imageId },
          reconstructedPng: d.reconstructedPng,
          shareDetails: d.shareDetails || [],
          durationMs: d.durationMs || "—",
          sensor: d.sensor || "",
          season: d.season || "",
        });
      }
    } catch (e) {}
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => setLoading(false), 300);
    return () => clearTimeout(timer);
  }, [images]);

  useEffect(() => {
    const fetchCatalog = async () => {
      try {
        const res = await (await import("../api/client")).getSatelliteCatalog();
        setImages(res.data.images || []);
        setNodes(res.data.nodes || {});
      } catch (e) {
        console.error("Failed to fetch catalog:", e);
      }
    };
    fetchCatalog();
  }, []);

  const handleSort = useCallback((col) => {
    setSortCol((prev) => {
      if (prev === col) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        return col;
      }
      setSortDir("asc");
      return col;
    });
  }, []);

  const handleReconstruct = useCallback(async (img) => {
    setReconstructingId(img.id);
    try {
      const res = await reconstructSatelliteImage(img.id);
      const { image: b64, duration_ms, sensor, season, shares } = res.data;
      const pngUrl = `data:image/png;base64,${b64}`;
      const modalData = {
        imageId: img.id,
        reconstructedPng: pngUrl,
        shareDetails: shares || [],
        durationMs: duration_ms ? `${duration_ms}ms` : "—",
        sensor: sensor || img.sensor,
        season: season || img.season,
      };
      try {
        sessionStorage.setItem(RECONSTRUCT_CACHE_KEY, JSON.stringify(modalData));
      } catch (e) {}
      setModal({ image: img, ...modalData });
    } catch (e) {
      alert(`Reconstruct failed: ${e.response?.data?.detail || e.message}`);
    } finally {
      setReconstructingId(null);
    }
  }, []);

  const filtered = images
    .filter((img) => {
      if (filterSensor !== "all" && img.sensor !== filterSensor) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          img.id.includes(q) ||
          img.sensor.toLowerCase().includes(q) ||
          img.season.includes(q) ||
          img.acquisition_date.includes(q) ||
          img.shares?.some((s) => s.node_ip.includes(q) || s.node.toLowerCase().includes(q))
        );
      }
      return true;
    })
    .sort((a, b) => {
      let va, vb;
      switch (sortCol) {
        case "sensor": va = a.sensor; vb = b.sensor; break;
        case "season": va = a.season; vb = b.season; break;
        case "date": va = a.acquisition_date; vb = b.acquisition_date; break;
        default: va = a.index; vb = b.index;
      }
      if (va < vb) return sortDir === "asc" ? -1 : 1;
      if (va > vb) return sortDir === "asc" ? 1 : -1;
      return 0;
    });

  const nodeEntries = Object.entries(nodes);
  const maxShares = Math.max(1, ...images.map((img) => (img.shares?.length || 0)));

  return (
    <>
      <style>{`
        .sat-table { border-collapse: collapse; width: max-content; min-width: 100%; }
        .sat-cell { padding: 12px 14px; border-right: 1px solid #e5e7eb; border-bottom: 1px solid #e5e7eb; vertical-align: middle; white-space: normal; }
        .sat-cell:last-child { border-right: none; }
        .sat-cell-essential { min-width: 120px; max-width: 120px; }
        .sat-cell-share { min-width: 200px; max-width: 200px; }
        .sat-header { background: #f9fafb; position: sticky; top: 0; z-index: 5; }
        .sat-header-cell { padding: 14px 14px; border-right: 1px solid #e5e7eb; border-bottom: 2px solid #d1d5db; text-align: left; font-size: 17px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; cursor: pointer; user-select: none; white-space: nowrap; }
        .sat-header-cell:hover { background: #f3f4f6; }
        .sat-header-cell:last-child { border-right: none; }
        .sat-header-essential { background: #fffbeb; }
        .sat-row-even { background: #ffffff; }
        .sat-row-odd { background: #f9fafb; }
        .sat-row-even:hover, .sat-row-odd:hover { background: #eff6ff; }
        .sort-icon { display: inline-block; margin-left: 5px; opacity: 0.4; font-size: 15px; }
        .sort-icon.active { opacity: 1; color: #3b82f6; }
      `}</style>

      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        <div className="px-6 py-5 border-b border-gray-100 flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-4">
            <h2 className="text-xl font-semibold text-gray-900">SSL4EO-S12 v1.1</h2>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={filterSensor}
              onChange={(e) => setFilterSensor(e.target.value)}
              className="text-lg border border-gray-200 rounded-md px-4 py-2.5 bg-white text-gray-600 focus:outline-none focus:ring-1 focus:ring-primary-400"
            >
              <option value="all">All Sensors</option>
              {Object.keys(SENSOR_COLORS).map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <input
              type="text"
              placeholder="Search sensor, date, node IP..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="text-lg border border-gray-200 rounded-md px-4 py-2.5 w-80 text-gray-600 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-primary-400"
            />
            <span className="text-lg text-gray-400">
              {filtered.length} / {images.length}
            </span>
          </div>
        </div>

        <div className="overflow-x-auto" style={{ maxHeight: "calc(100vh - 260px)" }}>
          <table className="sat-table">
            <thead className="sat-header">
              <tr>
                <th className="sat-header-cell" style={{ width: "100px" }}>
                  Thumbnail
                </th>
                <th
                  className="sat-header-cell"
                  style={{ width: "120px" }}
                  onClick={() => handleSort("sensor")}
                >
                  Type{sortIcon(sortCol, sortDir, "sensor")}
                </th>
                <th className="sat-header-cell sat-header-essential" style={{ width: "150px" }}>
                  <div className="flex flex-col items-center">
                    <span className="text-amber-600 font-semibold text-lg">Essential</span>
                    <span className="text-base text-amber-500 font-normal normal-case tracking-normal">Local</span>
                  </div>
                </th>
                {Array.from({ length: maxShares }).map((_, idx) => (
                  <th key={idx} className="sat-header-cell sat-cell-share">
                    <div className="flex flex-col items-start">
                      <span className="text-base text-gray-400 font-normal">NLSS Share {idx + 1}</span>
                    </div>
                  </th>
                ))}
                <th className="sat-header-cell" style={{ width: "160px", cursor: "default" }}>
                  Action
                </th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 10 }).map((_, i) => <SkeletonRow key={i} nNodes={maxShares} />)
              ) : (
                filtered.map((img) => {
                  const rowCls = img.index % 2 === 0 ? "sat-row-even" : "sat-row-odd";

                  return (
                    <tr key={img.id} className={rowCls}>
                      <td className="sat-cell">
                        <img
                          src={`data:image/jpeg;base64,${img.thumbnail}`}
                          alt={img.id}
                          className="w-24 h-24 object-cover border border-gray-100 cursor-pointer hover:opacity-70 transition-opacity"
                          onClick={() => setLargeThumb(img.thumbnail)}
                        />
                      </td>
                      <td className="sat-cell">
                        <SensorBadge sensor={img.sensor} />
                      </td>
                      <td className="sat-cell sat-cell-essential">
                        <EssentialCell share={img.essential_share} />
                      </td>
                      {Array.from({ length: maxShares }).map((_, idx) => (
                        <ShareCell key={idx} share={(img.shares || [])[idx]} />
                      ))}
                      <td className="sat-cell">
                        <button
                          onClick={() => handleReconstruct(img)}
                          disabled={reconstructingId === img.id}
                          className="text-lg bg-primary-500 text-white px-5 py-3 rounded hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
                        >
                          {reconstructingId === img.id ? (
                            <span className="flex items-center gap-2">
                              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                              </svg>
                              Working
                            </span>
                          ) : (
                            "Reconstruct"
                          )}
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {modal && (
        <ReconstructModal
          image={modal.image}
          reconstructedPng={modal.reconstructedPng}
          shareDetails={modal.shareDetails}
          durationMs={modal.durationMs}
          sensor={modal.sensor}
          season={modal.season}
          onClose={() => {
            sessionStorage.removeItem(RECONSTRUCT_CACHE_KEY);
            setModal(null);
          }}
        />
      )}

      {largeThumb && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setLargeThumb(null)}
        >
          <img
            src={`data:image/jpeg;base64,${largeThumb}`}
            alt="Large preview"
            className="max-w-[90vw] max-h-[90vh] rounded-lg shadow-2xl"
          />
        </div>
      )}
    </>
  );
}

function sortIcon(col, dir, target) {
  if (col !== target) return <span className="sort-icon">↕</span>;
  return <span className="sort-icon active">{dir === "asc" ? "↑" : "↓"}</span>;
}
