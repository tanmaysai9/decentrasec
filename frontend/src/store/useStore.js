import { create } from "zustand";

const useStore = create((set) => ({
  token: sessionStorage.getItem("decentrasec_token") || null,
  address: sessionStorage.getItem("decentrasec_address") || null,
  name: sessionStorage.getItem("decentrasec_name") || null,

  setAuth: (token, address, name) => {
    sessionStorage.setItem("decentrasec_token", token);
    sessionStorage.setItem("decentrasec_address", address);
    sessionStorage.setItem("decentrasec_name", name);
    set({ token, address, name });
  },

  disconnect: () => {
    sessionStorage.removeItem("decentrasec_token");
    sessionStorage.removeItem("decentrasec_address");
    sessionStorage.removeItem("decentrasec_name");
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

  reconstructDurations: {},
  setReconstructDuration: (id, ms) =>
    set((s) => ({ reconstructDurations: { ...s.reconstructDurations, [id]: ms } })),
}));

export default useStore;
