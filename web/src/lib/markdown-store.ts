import { promises as fs } from "node:fs";
import path from "node:path";
import matter from "gray-matter";
import { cache } from "react";
import { parseMarkdownBody } from "./parse-markdown";
import type {
  AnswerBankEntry,
  AnswerTheme,
  Application,
  ApplicationSource,
  ApplicationStatus,
  Company,
  CompanyStatus,
  RemotePolicy,
} from "./types";

/**
 * Single source of truth for reading the local markdown tree that backs the
 * web app. Mirrors the schema in /SCHEMA.md at the repo root.
 *
 * IDs are URL-safe joins of the file's path components separated by "__".
 * Slugs in the schema are kebab-case (hyphens only) so "__" is unambiguous.
 *
 *   Application: <status>__<company-slug>__<filename-without-ext>
 *   Company:     <status>__<slug>
 *   Answer Bank: <theme>__<slug>
 */

export class DataNotConfiguredError extends Error {
  readonly missing: string[];
  constructor(missing: string[]) {
    super(`Data folders missing under repo root: ${missing.join(", ")}`);
    this.name = "DataNotConfiguredError";
    this.missing = missing;
  }
}

let cachedRoot: string | null = null;

/** Walk upward from process.cwd() looking for SCHEMA.md (the repo marker). */
async function findRepoRoot(): Promise<string> {
  if (cachedRoot) return cachedRoot;
  const envRoot = process.env.CAREERBOT_DATA_ROOT;
  if (envRoot) {
    cachedRoot = path.resolve(envRoot);
    return cachedRoot;
  }
  let dir = process.cwd();
  for (let i = 0; i < 8; i++) {
    try {
      await fs.access(path.join(dir, "SCHEMA.md"));
      cachedRoot = dir;
      return dir;
    } catch {
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  // Fall back to one level up from cwd (matches `web/` → repo root).
  cachedRoot = path.resolve(process.cwd(), "..");
  return cachedRoot;
}

export async function getDataRoot(): Promise<string> {
  return findRepoRoot();
}

/** Throws DataNotConfiguredError if any of the three top-level folders is missing. */
async function assertDataFolders(): Promise<{ root: string }> {
  const root = await findRepoRoot();
  const missing: string[] = [];
  for (const dir of ["applications", "companies", "answer-bank"]) {
    try {
      const stat = await fs.stat(path.join(root, dir));
      if (!stat.isDirectory()) missing.push(dir);
    } catch {
      missing.push(dir);
    }
  }
  if (missing.length > 0) throw new DataNotConfiguredError(missing);
  return { root };
}

async function listMarkdownFiles(dir: string): Promise<string[]> {
  let entries: import("node:fs").Dirent[];
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const out: string[] = [];
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      out.push(...(await listMarkdownFiles(full)));
    } else if (
      e.isFile() &&
      e.name.endsWith(".md") &&
      !["AGENTS.md", "CLAUDE.md", "README.md", "EXAMPLE.md"].includes(e.name) &&
      !e.name.endsWith(".example.md")
    ) {
      out.push(full);
    }
  }
  return out;
}

interface ParsedFile<T> {
  /** Frontmatter fields. */
  data: Record<string, unknown>;
  /** Markdown body (everything after the second `---`). */
  body: string;
  /** Path components relative to the entity root, e.g. ["applied","stripe","1234-eng"]. */
  parts: string[];
  /** Stable URL-safe ID built from parts. */
  id: string;
  /** Path on disk. */
  abs: string;
  /** File modification time, ISO date string (yyyy-mm-dd). */
  mtime: string;
  _t?: T; // phantom for typing
}

async function mtimeOf(abs: string): Promise<string> {
  const st = await fs.stat(abs);
  return st.mtime.toISOString().slice(0, 10);
}

function partsToId(parts: string[]): string {
  return parts.join("__");
}

export function idToParts(id: string): string[] {
  return id.split("__");
}

async function loadEntity<T>(
  rootDir: string,
  expectedDepth: number,
): Promise<ParsedFile<T>[]> {
  const files = await listMarkdownFiles(rootDir);
  const out: ParsedFile<T>[] = [];
  for (const abs of files) {
    const rel = path.relative(rootDir, abs);
    const parts = rel.replace(/\.md$/, "").split(path.sep);
    if (parts.length !== expectedDepth) continue;
    const [raw, mtime] = await Promise.all([
      fs.readFile(abs, "utf8"),
      mtimeOf(abs),
    ]);
    let parsed: ReturnType<typeof matter>;
    try {
      parsed = matter(raw);
    } catch (err) {
      // Malformed frontmatter (typically an unquoted YAML value with an
      // inline `:` or other special char). Skip the file rather than crashing
      // the whole tree walk — one bad file shouldn't take down the page.
      console.warn(
        `[markdown-store] Skipping ${abs}: ${(err as Error).message}`,
      );
      continue;
    }
    out.push({
      data: parsed.data as Record<string, unknown>,
      body: parsed.content,
      parts,
      id: partsToId(parts),
      abs,
      mtime,
    });
  }
  return out;
}

function str(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") return v.length === 0 ? null : v;
  return String(v);
}

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function strList(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.filter((x): x is string => typeof x === "string");
}

function date(v: unknown): string | null {
  if (v === null || v === undefined || v === "") return null;
  if (v instanceof Date) return v.toISOString().slice(0, 10);
  if (typeof v === "string") return v;
  return null;
}

function joinSize(headcount: string | null, stage: string | null, valuation: string | null): string | null {
  const parts = [headcount, stage, valuation].filter((s): s is string => !!s);
  return parts.length === 0 ? null : parts.join(" · ");
}

const APPLICATION_STATUS_SET = new Set<ApplicationStatus>([
  "in-review", "applied", "interview", "rejected", "offered", "archived",
]);
const COMPANY_STATUS_SET = new Set<CompanyStatus>([
  "in-review", "interested", "not-interested",
]);
const ANSWER_THEME_SET = new Set<AnswerTheme>([
  "identity", "beliefs", "stories", "career", "skills", "voice",
]);
const APPLICATION_SOURCE_SET = new Set<ApplicationSource>([
  "greenhouse", "lever", "ashby", "workday", "careers-page", "other",
]);
const REMOTE_POLICY_SET = new Set<RemotePolicy>(["remote", "hybrid", "onsite"]);

function enumOrNull<T>(v: unknown, set: Set<T>): T | null {
  const s = str(v);
  return s && set.has(s as T) ? (s as T) : null;
}

function applicationFromFile(f: ParsedFile<Application>): Application & { _body: string } {
  const [statusPart, companySlug, _filename] = f.parts;
  void _filename;
  const status = APPLICATION_STATUS_SET.has(statusPart as ApplicationStatus)
    ? (statusPart as ApplicationStatus)
    : null;
  const d = f.data;
  return {
    id: f.id,
    title: str(d.title) ?? "(untitled)",
    companyIds: companySlug && companySlug !== "_orphans" ? [companySlug] : [],
    companyName: null, // filled in by attachCompanyNames
    status,
    atsId: str(d.ats_id),
    url: str(d.url),
    source: enumOrNull<ApplicationSource>(d.source, APPLICATION_SOURCE_SET),
    postedAt: date(d.posted_at),
    dateFound: date(d.date_found),
    salaryMin: num(d.salary_min),
    salaryMax: num(d.salary_max),
    location: str(d.location),
    notes: str(d.notes),
    matchScore: num(d.match_score),
    _body: f.body,
  };
}

function companyFromFile(f: ParsedFile<Company>): Company & { _body: string } {
  const [statusPart, _slugFile] = f.parts;
  void _slugFile;
  const status = COMPANY_STATUS_SET.has(statusPart as CompanyStatus)
    ? (statusPart as CompanyStatus)
    : null;
  const d = f.data;
  const headcount = str(d.headcount);
  const stage = str(d.stage);
  const valuation = str(d.valuation);
  return {
    id: f.id,
    name: str(d.name) ?? "(unnamed)",
    slug: str(d.slug),
    status,
    industry: strList(d.industry),
    matchScore: num(d.match_score),
    size: joinSize(headcount, stage, valuation),
    hq: str(d.hq),
    remotePolicy: enumOrNull<RemotePolicy>(d.remote_policy, REMOTE_POLICY_SET),
    researchedOn: date(d.researched_on),
    notInterestedReason: str(d.not_interested_reason),
    careersUrl: str(d.careers_url),
    _body: f.body,
  };
}

function answerFromFile(f: ParsedFile<AnswerBankEntry>): AnswerBankEntry & { _body: string } {
  const [themePart, _slug] = f.parts;
  void _slug;
  const theme = ANSWER_THEME_SET.has(themePart as AnswerTheme)
    ? (themePart as AnswerTheme)
    : null;
  const d = f.data;
  return {
    id: f.id,
    question: str(d.question) ?? "(no question)",
    theme,
    tags: strList(d.tags),
    canonicalAnswer: f.body.trim() ? f.body.trim() : null,
    lastUpdated: f.mtime,
    _body: f.body,
  };
}

// ----- public read API ------------------------------------------------------

export const listApplications = cache(async (): Promise<Application[]> => {
  const { root } = await assertDataFolders();
  const files = await loadEntity<Application>(path.join(root, "applications"), 3);
  const apps = files.map(applicationFromFile);
  return attachCompanyNames(apps);
});

export const getApplication = cache(async (id: string) => {
  const { root } = await assertDataFolders();
  const parts = idToParts(id);
  if (parts.length !== 3) throw new Error(`Invalid application id: ${id}`);
  const abs = path.join(root, "applications", parts[0], parts[1], parts[2] + ".md");
  const [raw, mtime] = await Promise.all([
    fs.readFile(abs, "utf8"),
    mtimeOf(abs),
  ]);
  const parsed = matter(raw);
  const file: ParsedFile<Application> = {
    data: parsed.data as Record<string, unknown>,
    body: parsed.content,
    parts,
    id,
    abs,
    mtime,
  };
  const app = applicationFromFile(file);
  const [withNames, blocks] = await Promise.all([
    attachCompanyNames([app]),
    parseMarkdownBody(app._body),
  ]);
  return { application: withNames[0], blocks, body: app._body };
});

export const listCompanies = cache(async (): Promise<Company[]> => {
  const { root } = await assertDataFolders();
  const files = await loadEntity<Company>(path.join(root, "companies"), 2);
  return files.map(companyFromFile);
});

export const getCompany = cache(async (id: string) => {
  const { root } = await assertDataFolders();
  const parts = idToParts(id);
  if (parts.length !== 2) throw new Error(`Invalid company id: ${id}`);
  const abs = path.join(root, "companies", parts[0], parts[1] + ".md");
  const [raw, mtime] = await Promise.all([
    fs.readFile(abs, "utf8"),
    mtimeOf(abs),
  ]);
  const parsed = matter(raw);
  const file: ParsedFile<Company> = {
    data: parsed.data as Record<string, unknown>,
    body: parsed.content,
    parts,
    id,
    abs,
    mtime,
  };
  const company = companyFromFile(file);
  const blocks = await parseMarkdownBody(company._body);
  return { company, blocks };
});

/**
 * Look up a company by bare slug (no `<status>__` prefix). Walks all three
 * status folders to find a matching file. Used by the Applications page to
 * resolve an application's `company:` frontmatter slug to a full Company
 * record (so Quick Facts can render the company's industry and size).
 */
export const getCompanyBySlug = cache(
  async (slug: string): Promise<{ company: Company; blocks: import("./types").RenderableBlock[] } | null> => {
    const { root } = await assertDataFolders();
    for (const status of ["interested", "in-review", "not-interested"] as const) {
      const abs = path.join(root, "companies", status, slug + ".md");
      try {
        const [raw, mtime] = await Promise.all([
          fs.readFile(abs, "utf8"),
          mtimeOf(abs),
        ]);
        const parsed = matter(raw);
        const file: ParsedFile<Company> = {
          data: parsed.data as Record<string, unknown>,
          body: parsed.content,
          parts: [status, slug],
          id: `${status}__${slug}`,
          abs,
          mtime,
        };
        const company = companyFromFile(file);
        const blocks = await parseMarkdownBody(company._body);
        return { company, blocks };
      } catch {
        // try the next status folder
      }
    }
    return null;
  },
);

export const listAnswerBank = cache(async (): Promise<AnswerBankEntry[]> => {
  const { root } = await assertDataFolders();
  const files = await loadEntity<AnswerBankEntry>(path.join(root, "answer-bank"), 2);
  return files.map(answerFromFile);
});

export const getAnswerBankEntry = cache(async (id: string) => {
  const { root } = await assertDataFolders();
  const parts = idToParts(id);
  if (parts.length !== 2) throw new Error(`Invalid answer-bank id: ${id}`);
  const abs = path.join(root, "answer-bank", parts[0], parts[1] + ".md");
  const [raw, mtime] = await Promise.all([
    fs.readFile(abs, "utf8"),
    mtimeOf(abs),
  ]);
  const parsed = matter(raw);
  const file: ParsedFile<AnswerBankEntry> = {
    data: parsed.data as Record<string, unknown>,
    body: parsed.content,
    parts,
    id,
    abs,
    mtime,
  };
  return answerFromFile(file);
});

/**
 * Resolve company-name strings on a batch of applications by looking up each
 * companyId (which is a slug) in the Companies tree. Tries all three company
 * status folders.
 */
export async function attachCompanyNames(
  apps: (Application & { _body?: string })[],
): Promise<Application[]> {
  const { root } = await assertDataFolders();
  const slugs = new Set<string>();
  for (const a of apps) for (const s of a.companyIds) slugs.add(s);
  const cache = new Map<string, string | null>();
  await Promise.all(
    Array.from(slugs).map(async (slug) => {
      for (const status of ["interested", "in-review", "not-interested"] as const) {
        try {
          const abs = path.join(root, "companies", status, slug + ".md");
          const raw = await fs.readFile(abs, "utf8");
          const parsed = matter(raw);
          const name = str((parsed.data as Record<string, unknown>).name);
          cache.set(slug, name);
          return;
        } catch {
          // try the next status folder
        }
      }
      cache.set(slug, null);
    }),
  );
  return apps.map(({ _body: _b, ...rest }) => {
    void _b;
    const firstName = rest.companyIds.map((s) => cache.get(s) ?? null).find((n) => n) ?? null;
    return { ...rest, companyName: firstName };
  });
}

// ----- write helpers --------------------------------------------------------

/**
 * Write a markdown file with the given frontmatter object and body. Creates
 * parent directories as needed. Atomic via temp-file rename.
 */
export async function writeMarkdownFile(
  abs: string,
  frontmatter: Record<string, unknown>,
  body: string,
): Promise<void> {
  await fs.mkdir(path.dirname(abs), { recursive: true });
  const yaml = serializeFrontmatter(frontmatter);
  const content = `---\n${yaml}---\n\n${body.trim()}\n`;
  const tmp = abs + ".tmp";
  await fs.writeFile(tmp, content, "utf8");
  await fs.rename(tmp, abs);
}

/**
 * Read a markdown file, update its frontmatter via `patch`, and write it back.
 * Existing body is preserved. Unknown keys in `patch` are merged.
 */
export async function patchMarkdownFile(
  abs: string,
  patch: Record<string, unknown>,
): Promise<void> {
  const raw = await fs.readFile(abs, "utf8");
  const parsed = matter(raw);
  const merged = { ...(parsed.data as Record<string, unknown>), ...patch };
  await writeMarkdownFile(abs, merged, parsed.content);
}

export async function moveFile(absFrom: string, absTo: string): Promise<void> {
  await fs.mkdir(path.dirname(absTo), { recursive: true });
  await fs.rename(absFrom, absTo);
}

export async function pathForApplicationId(id: string): Promise<string> {
  const { root } = await assertDataFolders();
  const parts = idToParts(id);
  if (parts.length !== 3) throw new Error(`Invalid application id: ${id}`);
  return path.join(root, "applications", parts[0], parts[1], parts[2] + ".md");
}

export async function pathForCompanyId(id: string): Promise<string> {
  const { root } = await assertDataFolders();
  const parts = idToParts(id);
  if (parts.length !== 2) throw new Error(`Invalid company id: ${id}`);
  return path.join(root, "companies", parts[0], parts[1] + ".md");
}

export async function pathForAnswerBankId(id: string): Promise<string> {
  const { root } = await assertDataFolders();
  const parts = idToParts(id);
  if (parts.length !== 2) throw new Error(`Invalid answer-bank id: ${id}`);
  return path.join(root, "answer-bank", parts[0], parts[1] + ".md");
}

/**
 * Serialize a JS object as YAML frontmatter. Keeps key order, quotes strings
 * conservatively, emits `null` literal, renders lists inline if short.
 */
function serializeFrontmatter(obj: Record<string, unknown>): string {
  const lines: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    lines.push(`${k}: ${serializeYamlValue(v)}`);
  }
  return lines.join("\n") + "\n";
}

function serializeYamlValue(v: unknown): string {
  if (v === null || v === undefined) return "null";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return String(v);
  if (Array.isArray(v)) {
    if (v.length === 0) return "[]";
    return "[" + v.map((x) => serializeYamlValue(x)).join(", ") + "]";
  }
  if (v instanceof Date) return v.toISOString().slice(0, 10);
  const s = String(v);
  // dates / slugs / kebab strings → bare
  if (/^[A-Za-z0-9][\w./:-]*$/.test(s) && !["null", "true", "false"].includes(s)) {
    return s;
  }
  // anything else → double-quoted, escape `"` and `\`
  return `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

// re-export the markdown body parser so callers only need one import
export { parseMarkdownBody };
