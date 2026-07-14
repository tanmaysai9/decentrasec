import { useEffect, useState } from "react";
import { getSatelliteStatus } from "../api/client";
import SatelliteTable from "../components/SatelliteTable";

export default function SatelliteShares() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    getSatelliteStatus()
      .then((r) => setStatus(r.data))
      .catch(() => setStatus({ ready: false }));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-[1400px] mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a href="/dashboard" className="text-base text-gray-400 hover:text-gray-600 transition-colors">
              ← Dashboard
            </a>
            <div className="w-px h-5 bg-gray-200" />
            <div className="text-lg font-semibold text-gray-900">Satellite Imagery</div>
            <span className="text-sm bg-primary-100 text-primary-700 px-2.5 py-0.5 rounded-full font-medium">
              SSL4EO-S12 v1.1
            </span>
          </div>
          {status && (
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${status.ready ? "bg-green-500" : "bg-amber-400"}`} />
              <span className="text-sm text-gray-500">
                {status.ready ? "Ready" : "Processing..."}
              </span>
            </div>
          )}
        </div>
      </header>
      <main className="max-w-[1400px] mx-auto px-4 py-6">
        <SatelliteTable />
      </main>
    </div>
  );
}
