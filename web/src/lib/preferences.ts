import { promises as fs } from "fs";
import path from "path";
import { cache } from "react";
import matter from "gray-matter";
import { DEFAULT_PREFERENCES, type Preferences } from "./preferences-shape";
import { getDataRoot } from "./markdown-store";

export { DEFAULT_PREFERENCES };
export type { Preferences, Track } from "./preferences-shape";

// preferences.md is the single source of truth: YAML frontmatter holds the
// typed Preferences object (what the dashboard form binds to), markdown body
// below it renders the human-readable view that consumer skills (find-roles,
// find-companies, etc.) parse. Both are produced from the same in-memory
// Preferences object on every write. Path resolves against the same data root
// as markdown-store (CAREERBOT_DATA_ROOT env var, or auto-detected by walking
// up from cwd looking for SCHEMA.md).
async function preferencesPath(): Promise<string> {
  const root = await getDataRoot();
  return path.join(root, "context", "preferences.md");
}

export async function readPreferences(): Promise<Preferences> {
  try {
    const raw = await fs.readFile(await preferencesPath(), "utf-8");
    const parsed = matter(raw);
    return mergeWithDefaults(parsed.data as Partial<Preferences>);
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

/**
 * Returns whether context/preferences.md exists on disk. Used by the root
 * layout to decide whether to mount the first-run onboarding overlay.
 * Cached per request so layout + page calls don't double-stat.
 */
export const preferencesFileExists = cache(async (): Promise<boolean> => {
  try {
    await fs.stat(await preferencesPath());
    return true;
  } catch {
    return false;
  }
});

export async function writePreferences(prefs: Preferences): Promise<void> {
  // Both layers come from the same Preferences object: frontmatter is the
  // typed shape, body is the human-readable rendering. Write them as one file.
  const body = renderPreferencesMarkdown(prefs);
  const fileContent = matter.stringify(body, prefs as unknown as Record<string, unknown>);
  const target = await preferencesPath();
  await fs.mkdir(path.dirname(target), { recursive: true });
  await fs.writeFile(target, fileContent, "utf-8");
}

function formatUsd(n: number | null): string {
  if (n == null) return "TBD";
  return `$${n.toLocaleString("en-US")}`;
}

export function renderPreferencesMarkdown(p: Preferences): string {
  return `# Job Preferences

> Auto-rendered from the YAML frontmatter at the top of this file. Edit via the Configuration page in the dashboard (writes both halves) or via \`/onboard\` in Claude Code.

## Role
- Titles I'm targeting: ${p.role.titles.join(", ") || "TBD"}
- Track: ${p.role.track}
- Specialties: ${p.role.specialties.join(", ") || "TBD"}
- Titles to exclude: ${p.role.exclude_titles.join(", ") || "(none)"}
- Title synonyms: ${Object.entries(p.role.title_synonyms).map(([k, v]) => `${k} → ${v.join(", ")}`).join("; ") || "(none)"}

## Compensation
- Minimum base salary: ${formatUsd(p.compensation.base_min_usd)}
- Total comp target: ${formatUsd(p.compensation.total_comp_target_usd)}
- Equity preferences: ${p.compensation.equity_open_to.join(", ") || "TBD"}

## Location
- Preferred cities: ${p.location.preferred_cities.join("; ") || "TBD"}
- Time zones: ${p.location.time_zones.join(", ") || "TBD"}
- Remote: ${p.location.open_to_remote ? "yes" : "no"} · Hybrid: ${p.location.open_to_hybrid ? "yes" : "no"} · Onsite: ${p.location.open_to_onsite ? "yes" : "no"}
- Open to relocation: ${p.location.open_to_relocation ? "yes" : "no"}
- US work authorization: ${p.location.work_auth_us ? "yes" : "no"}
- Needs visa sponsorship: ${p.location.needs_sponsorship ? "yes" : "no"}

## Company
- Open stages: ${p.company.stages.join(", ") || "TBD"}
- Size range: ${p.company.size_range || "TBD"}
- Industries I want: ${p.company.industries_want.join(", ") || "TBD"}
- Industries to avoid: ${p.company.industries_avoid.join(", ") || "(none)"}
- Specific companies to exclude: ${p.company.excluded_companies.join(", ") || "(none)"}

## Work
- Design tools I use: ${p.work.design_tools.join(", ") || "TBD"}
- Tech stack to avoid: ${p.work.tech_avoid.join(", ") || "(none)"}
- Domains I'm excited about: ${p.work.domains.join(", ") || "TBD"}
- Problems I want to work on: ${p.work.problems || "TBD"}

## Culture & Schedule
- Hours / on-call expectations: ${p.culture.hours || "TBD"}
- Travel tolerance: ${p.culture.travel_tolerance || "TBD"}
- Async vs synchronous teams: ${p.culture.async_sync || "TBD"}
- Anything else that matters: ${p.culture.other || "(none)"}

## Voice
${p.voice.no_em_dashes ? "- Never use em dashes (`—`) in any drafted prose (cover letters, \"Why us?\" essays, application answers). Substitute with commas, periods, parentheses, or rewrite. Hyphens (`-`) and en dashes (`–`) are fine.\n" : ""}- Phrases to avoid: ${p.voice.phrases_to_avoid.join(", ") || "(none)"}
- Tone notes: ${p.voice.tone_notes || "(none)"}
`;
}

function mergeWithDefaults(partial: Partial<Preferences>): Preferences {
  return {
    role: { ...DEFAULT_PREFERENCES.role, ...partial.role },
    compensation: {
      ...DEFAULT_PREFERENCES.compensation,
      ...partial.compensation,
    },
    location: { ...DEFAULT_PREFERENCES.location, ...partial.location },
    company: { ...DEFAULT_PREFERENCES.company, ...partial.company },
    work: { ...DEFAULT_PREFERENCES.work, ...partial.work },
    culture: { ...DEFAULT_PREFERENCES.culture, ...partial.culture },
    voice: { ...DEFAULT_PREFERENCES.voice, ...partial.voice },
  };
}

