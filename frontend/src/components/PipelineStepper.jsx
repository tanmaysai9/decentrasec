import useStore from "../store/useStore";

const STAGES = [
  { key: "validate", label: "Validate" },
  { key: "encrypt", label: "Protect" },
  { key: "split", label: "NLSS Split" },
  { key: "distribute", label: "Distribute" },
  { key: "anchor", label: "Confirm" },
];

export default function PipelineStepper() {
  const status = useStore((s) => s.uploadStatus);

  const getStageState = (stageKey, index) => {
    if (!status) return "pending";
    if (status.stage === "error") return index <= status.stage_index ? "error" : "pending";
    if (status.stage === "done") return "done";
    if (index < status.stage_index) return "done";
    if (index === status.stage_index) return "active";
    return "pending";
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-4">
        Pipeline Status
      </h2>
      <div className="flex items-center">
        {STAGES.map((stage, i) => {
          const state = getStageState(stage.key, i);
          return (
            <div key={stage.key} className="flex items-center flex-1">
              <div className="flex flex-col items-center">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                    state === "done"
                      ? "bg-green-500 text-white"
                      : state === "active"
                      ? "bg-primary-500 text-white animate-pulse"
                      : state === "error"
                      ? "bg-red-500 text-white"
                      : "bg-gray-200 text-gray-400"
                  }`}
                >
                  {state === "done" ? "\u2713" : i + 1}
                </div>
                <span className="mt-1 text-[10px] text-gray-500 whitespace-nowrap">{stage.label}</span>
              </div>
              {i < STAGES.length - 1 && (
                <div className={`flex-1 h-0.5 mx-1 ${state === "done" ? "bg-green-400" : "bg-gray-200"}`} />
              )}
            </div>
          );
        })}
      </div>
      {status?.error && (
        <div className="mt-3 text-sm text-red-600">{status.error}</div>
      )}
    </div>
  );
}
