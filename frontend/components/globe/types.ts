export type FlagCategory = "domestic" | "shadow" | "sanctioned" | "other";

export type Vessel = {
  mmsi: string;
  lat: number;
  lon: number;
  flag_category: FlagCategory;
  // optional metadata surfaced by VesselPanel
  name?: string;
  flag?: string;
  destination?: string;
  cargo_bbls?: number;
  eta?: string;
  last_24h_nm?: number;
};

export const CATEGORY_COLORS: Record<FlagCategory, string> = {
  // tailwind emerald-400 / amber-400 / rose-500 / slate-400
  domestic: "#34d399",
  shadow: "#fbbf24",
  sanctioned: "#f43f5e",
  other: "#94a3b8",
};

export const CATEGORY_LABELS: Record<FlagCategory, string> = {
  domestic: "Jones Act / Domestic",
  shadow: "Shadow",
  sanctioned: "Sanctioned",
  other: "Other",
};
