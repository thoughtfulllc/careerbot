import { promises as fs } from "node:fs";
import path from "node:path";

export const DATA_ROOT = path.resolve(__dirname, "../.tmp/data-root");
export const FIXTURES_ROOT = path.resolve(__dirname, "../fixtures");

const COMPANY_STATUSES = ["in-review", "interested", "not-interested"] as const;
const APPLICATION_STATUSES = [
  "in-review",
  "interested",
  "applied",
  "interview",
  "rejected",
  "offered",
  "archived",
] as const;
const ANSWER_THEMES = [
  "identity",
  "beliefs",
  "stories",
  "career",
  "skills",
  "voice",
] as const;

export async function resetDataRoot(): Promise<void> {
  await fs.rm(DATA_ROOT, { recursive: true, force: true });
  await fs.mkdir(DATA_ROOT, { recursive: true });
  await fs.mkdir(path.join(DATA_ROOT, "context"), { recursive: true });
  for (const status of COMPANY_STATUSES) {
    await fs.mkdir(path.join(DATA_ROOT, "companies", status), { recursive: true });
  }
  for (const status of APPLICATION_STATUSES) {
    await fs.mkdir(path.join(DATA_ROOT, "applications", status), { recursive: true });
  }
  for (const theme of ANSWER_THEMES) {
    await fs.mkdir(path.join(DATA_ROOT, "answer-bank", theme), { recursive: true });
  }
}

export async function setupFreshRepo(): Promise<void> {
  await resetDataRoot();
}

export async function setupOnboarded(): Promise<void> {
  await resetDataRoot();
  await fs.copyFile(
    path.join(FIXTURES_ROOT, "context/preferences.md"),
    path.join(DATA_ROOT, "context/preferences.md"),
  );
}

interface CompanyOpts {
  inReview?: string[];
  interested?: string[];
  notInterested?: string[];
}

export async function setupWithCompanies(opts: CompanyOpts): Promise<void> {
  await setupOnboarded();
  const buckets: Array<{ status: (typeof COMPANY_STATUSES)[number]; slugs: string[] }> = [
    { status: "in-review", slugs: opts.inReview ?? [] },
    { status: "interested", slugs: opts.interested ?? [] },
    { status: "not-interested", slugs: opts.notInterested ?? [] },
  ];
  for (const { status, slugs } of buckets) {
    for (const slug of slugs) {
      await fs.copyFile(
        path.join(FIXTURES_ROOT, "companies", status, `${slug}.md`),
        path.join(DATA_ROOT, "companies", status, `${slug}.md`),
      );
    }
  }
}

export async function setupMidPipeline(): Promise<void> {
  await setupWithCompanies({ interested: ["linear"] });

  const applicationsDir = path.join(DATA_ROOT, "applications/in-review/linear");
  await fs.mkdir(applicationsDir, { recursive: true });
  for (const file of [
    "full-synth-engineer.md",
    "partial-synth-designer.md",
    "all-todo-pm.md",
  ]) {
    await fs.copyFile(
      path.join(FIXTURES_ROOT, "applications/in-review/linear", file),
      path.join(applicationsDir, file),
    );
  }

  // beliefs/mission-fit is FILLED; beliefs/culture-fit and career/companies-admired are STUBS.
  for (const [theme, file] of [
    ["beliefs", "mission-fit.md"],
    ["beliefs", "culture-fit.md"],
    ["career", "companies-admired.md"],
  ] as const) {
    await fs.copyFile(
      path.join(FIXTURES_ROOT, "answer-bank", theme, file),
      path.join(DATA_ROOT, "answer-bank", theme, file),
    );
  }
}

export async function readFile(rel: string): Promise<string> {
  return fs.readFile(path.join(DATA_ROOT, rel), "utf-8");
}

export async function fileExists(rel: string): Promise<boolean> {
  try {
    await fs.stat(path.join(DATA_ROOT, rel));
    return true;
  } catch {
    return false;
  }
}
