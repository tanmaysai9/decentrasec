import { create } from "zustand";

const useStore = create((set) => ({
  token: sessionStorage.getItem("sds_token") || null,
  address: sessionStorage.getItem("sds_address") || null,
  name: sessionStorage.getItem("sds_name") || null,

  setAuth: (token, address, name) => {
    sessionStorage.setItem("sds_token", token);
    sessionStorage.setItem("sds_address", address);
    sessionStorage.setItem("sds_name", name);
    set({ token, address, name });
  },

  disconnect: () => {
    sessionStorage.removeItem("sds_token");
    sessionStorage.removeItem("sds_address");
    sessionStorage.removeItem("sds_name");
    set({ token: null, address: null, name: null, archive: [], uploadStatus: null });
    window.location.href = "/";
  },

  uploadStatus: null,
  setUploadStatus: (s) => set({ uploadStatus: s }),

  archive: [],
  setArchive: (a) => set({ archive: a }),

  nodes: [],
  setNodes: (n) => set({ nodes: n }),

  reconstructingId: null,
  setReconstructingId: (id) => set({ reconstructingId: id }),

  reconstructDurations: (() => {
    try {
      return JSON.parse(sessionStorage.getItem("sds_reconstruct_durations") || "{}");
    } catch {
      return {};
    }
  })(),
  setReconstructDuration: (id, ms) =>
    set((s) => {
      const next = { ...s.reconstructDurations, [id]: ms };
      try {
        sessionStorage.setItem("sds_reconstruct_durations", JSON.stringify(next));
      } catch {}
      return { reconstructDurations: next };
    }),
}));

export default useStore;
