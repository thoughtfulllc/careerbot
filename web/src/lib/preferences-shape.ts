// Pure types + constants for Preferences. No Node imports — safe to import
// from client components. The server-side IO lives in ./preferences.ts.

export type Track = "IC" | "Management";

export interface Preferences {
  role: {
    titles: string[];
    track: Track;
    specialties: string[];
    exclude_titles: string[];
    title_synonyms: Record<string, string[]>;
  };
  compensation: {
    base_min_usd: number | null;
    total_comp_target_usd: number | null;
    equity_open_to: string[];
  };
  location: {
    preferred_cities: string[];
    time_zones: string[];
    open_to_remote: boolean;
    open_to_hybrid: boolean;
    open_to_onsite: boolean;
    open_to_relocation: boolean;
    work_auth_us: boolean;
    needs_sponsorship: boolean;
  };
  company: {
    stages: string[];
    size_range: string;
    industries_want: string[];
    industries_avoid: string[];
    excluded_companies: string[];
  };
  work: {
    design_tools: string[];
    tech_avoid: string[];
    domains: string[];
    problems: string;
  };
  culture: {
    hours: string;
    travel_tolerance: string;
    async_sync: string;
    other: string;
  };
  voice: {
    no_em_dashes: boolean;
    phrases_to_avoid: string[];
    tone_notes: string;
  };
}

export const DEFAULT_PREFERENCES: Preferences = {
  role: {
    titles: [],
    // Radio groups need one selection; "IC" is the conventional default. The
    // user can flip it on the Configuration page before they ever save.
    track: "IC",
    specialties: [],
    exclude_titles: [],
    title_synonyms: {},
  },
  compensation: {
    base_min_usd: null,
    total_comp_target_usd: null,
    equity_open_to: [],
  },
  location: {
    preferred_cities: [],
    time_zones: [],
    open_to_remote: false,
    open_to_hybrid: false,
    open_to_onsite: false,
    open_to_relocation: false,
    work_auth_us: false,
    needs_sponsorship: false,
  },
  company: {
    stages: [],
    size_range: "",
    industries_want: [],
    industries_avoid: [],
    excluded_companies: [],
  },
  work: {
    design_tools: [],
    tech_avoid: [],
    domains: [],
    problems: "",
  },
  culture: {
    hours: "",
    travel_tolerance: "",
    async_sync: "",
    other: "",
  },
  voice: {
    no_em_dashes: false,
    phrases_to_avoid: [],
    tone_notes: "",
  },
};
