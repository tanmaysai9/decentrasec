import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { mockWalletConnect } from "../api/client";
import useStore from "../store/useStore";

const WALLETS = [
  { address: "0xA1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2", name: "Researcher Alpha", color: "bg-blue-500", ring: "ring-blue-200" },
  { address: "0xC3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4", name: "Analyst Beta", color: "bg-emerald-500", ring: "ring-emerald-200" },
  { address: "0xE5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6", name: "Operator Gamma", color: "bg-amber-500", ring: "ring-amber-200" },
];

export default function Login() {
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const setAuth = useStore((s) => s.setAuth);

  const handleConnect = async () => {
    if (!selected) return;
    setLoading(true);
    setError("");
    try {
      const res = await mockWalletConnect(selected.address);
      setAuth(res.data.token, res.data.address, res.data.name);
      navigate("/dashboard");
      window.location.reload();
    } catch (e) {
      setError(e.response?.data?.detail || "Connection failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Secure Distributed Storage</h1>
          <p className="mt-2 text-gray-500">of Satellite Imagery</p>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-4">
            Select Identity
          </h2>

          <div className="space-y-3">
            {WALLETS.map((w) => (
              <button
                key={w.address}
                onClick={() => setSelected(w)}
                className={`w-full flex items-center gap-3 p-4 rounded-lg border-2 transition-all text-left ${
                  selected?.address === w.address
                    ? `border-primary-500 ring-2 ${w.ring} bg-primary-50`
                    : "border-gray-200 hover:border-gray-300 bg-white"
                }`}
              >
                <div className={`w-3 h-3 rounded-full ${w.color} shrink-0`} />
                <div>
                  <div className="font-medium text-gray-900">{w.name}</div>
                  <div className="text-xs text-gray-400 font-mono">{w.address}</div>
                </div>
              </button>
            ))}
          </div>

          {error && (
            <div className="mt-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
              {error}
            </div>
          )}

          <button
            onClick={handleConnect}
            disabled={!selected || loading}
            className="mt-6 w-full py-3 rounded-lg bg-primary-500 text-white font-medium hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Connecting..." : "Connect Wallet"}
          </button>
        </div>
      </div>
    </div>
  );
}
