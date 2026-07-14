import { useEffect } from "react";
import useStore from "../store/useStore";
import { getArchive, getNodes } from "../api/client";
import Header from "../components/Header";
import UploadPanel from "../components/UploadPanel";
import PipelineStepper from "../components/PipelineStepper";
import NodeCards from "../components/NodeCards";
import ArchiveTable from "../components/ArchiveTable";

export default function Dashboard() {
  const setArchive = useStore((s) => s.setArchive);
  const setNodes = useStore((s) => s.setNodes);

  useEffect(() => {
    getArchive().then((r) => setArchive(r.data.files || [])).catch(() => {});
    getNodes().then((r) => setNodes(r.data.nodes || [])).catch(() => {});
  }, [setArchive, setNodes]);

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <div className="flex justify-end">
          <a
            href="/satellite"
            className="text-xs bg-gray-900 text-white px-4 py-2 rounded-lg hover:bg-gray-800 transition-colors font-medium"
          >
            Satellite Imagery →
          </a>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <UploadPanel />
          <div className="space-y-6">
            <PipelineStepper />
            <NodeCards />
          </div>
        </div>
        <ArchiveTable />
      </main>
    </div>
  );
}
