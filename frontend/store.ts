import { create } from "zustand";
type UIState = {
  graphics: boolean;
  view: "overview" | "evidence" | "runs" | "review";
  selectedFinding: string | null;
  setView: (v: UIState["view"]) => void;
  setSelectedFinding: (id: string | null) => void;
  toggleGraphics: () => void;
};
export const useUI = create<UIState>((set) => ({
  graphics: true,
  view: "overview",
  selectedFinding: null,
  setView: (view) => set({ view }),
  setSelectedFinding: (selectedFinding) => set({ selectedFinding }),
  toggleGraphics: () => set((s) => ({ graphics: !s.graphics })),
}));
