import useStore from "../store/useStore";

export default function Header() {
  const address = useStore((s) => s.address);
  const name = useStore((s) => s.name);
  const disconnect = useStore((s) => s.disconnect);

  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="text-base font-bold text-gray-900 leading-tight">Secure Distributed Storage<div className="text-[10px] font-normal text-gray-400">of Satellite Imagery</div></div>
          <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full font-medium">
            Demo
          </span>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-sm font-medium text-gray-700">{name}</div>
            <div className="text-xs text-gray-400 font-mono">
              {address ? `${address.slice(0, 6)}...${address.slice(-4)}` : ""}
            </div>
          </div>
          <button
            onClick={disconnect}
            className="text-sm text-gray-500 hover:text-red-600 border border-gray-200 rounded-lg px-3 py-1.5 hover:border-red-300 transition-colors"
          >
            Disconnect
          </button>
        </div>
      </div>
    </header>
  );
}
