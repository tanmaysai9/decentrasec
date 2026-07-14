import useStore from "../store/useStore";

const NODE_NAMES = ["NODE-1", "NODE-2", "NODE-3", "NODE-4", "NODE-5"];

export default function NodeCards() {
  const uploadStatus = useStore((s) => s.uploadStatus);
  const nodes = uploadStatus?.nodes || {};

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-4">
        Storage Nodes
      </h2>
      <div className="grid grid-cols-5 gap-2">
        {NODE_NAMES.map((name) => {
          const info = nodes[name] || {};
          const st = info.status || "pending";
          return (
            <div
              key={name}
              className={`rounded-lg border p-3 text-center transition-all ${
                st === "ok"
                  ? "border-green-400 bg-green-50"
                  : st === "uploading"
                  ? "border-primary-400 bg-primary-50 animate-pulse"
                  : st === "error"
                  ? "border-red-400 bg-red-50"
                  : "border-gray-200 bg-gray-50"
              }`}
            >
              <div className="text-xs font-semibold text-gray-700">{name}</div>
              <div
                className={`mt-2 mx-auto w-3 h-3 rounded-full ${
                  st === "ok"
                    ? "bg-green-500"
                    : st === "uploading"
                    ? "bg-primary-500"
                    : st === "error"
                    ? "bg-red-500"
                    : "bg-gray-300"
                }`}
              />
              {info.cid && (
                <div className="mt-1 text-[9px] text-gray-400 truncate">
                  {info.cid.slice(0, 10)}...
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
