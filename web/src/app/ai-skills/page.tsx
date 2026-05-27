import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { GlassCard } from "@/components/glass-card";
import { DetailSheet } from "@/components/detail-sheet";
import { CopyButton } from "@/components/copy-button";
import { cn } from "@/lib/utils";

interface Skill {
  slug: string;
  command: string;
  tagline: string;
  whenToUse: string;
  examplePhrasings: string[];
  whatItChanges: string;
}

const SKILLS: Skill[] = [
  {
    slug: "find-companies",
    command: "/find-companies",
    tagline:
      "Surface ~10 new companies that fit your preferences and write a deep research profile for each. Bad matches get a one-paragraph rejection note so they never come back.",
    whenToUse: "When your pipeline is empty and you want fresh, well-researched candidates.",
    examplePhrasings: [
      "/find-companies",
      "Find me 10 new companies to look at",
    ],
    whatItChanges:
      "Writes new files to companies/in-review/<slug>.md (good matches, match_score ≥ 5) and companies/not-interested/<slug>.md (bad matches). Reads seeds from companies/ideas.md.",
  },
  {
    slug: "add-company",
    command: "/add-company",
    tagline:
      "Lightweight single-target version of /find-companies. Add one company you already know you want to track, with HQ, industry, and remote policy auto-filled.",
    whenToUse: "When you name one specific company you want in your pipeline.",
    examplePhrasings: [
      "Add Stripe",
      "Track Linear",
      "Add Anthropic, https://anthropic.com",
    ],
    whatItChanges: "Writes one new file at companies/interested/<slug>.md. Status is always `interested`.",
  },
  {
    slug: "add-application",
    command: "/add-application",
    tagline:
      "Single-target counterpart to /find-roles. Paste a job posting URL and get one application draft (verbatim JD plus AI-drafted answers from your Answer Bank) at applications/in-review/. Auto-adds the company if you haven't tracked it yet.",
    whenToUse:
      "When you've found one specific job you want to apply to and don't want to wait for the next /find-roles batch run.",
    examplePhrasings: [
      "/add-application <url>",
      "Add this job: <url>",
      "Track this application: <url>",
      "Draft an application for <url>",
    ],
    whatItChanges:
      "Writes one new file at applications/in-review/<company-slug>/<ats-id>-<title-slug>.md. May also write a new companies/interested/<slug>.md if the company isn't tracked yet. May add new stubs under answer-bank/ where the drafted essays hit a context gap.",
  },
  {
    slug: "seed-answer-bank",
    command: "/seed-answer-bank",
    tagline:
      "Walk through the Answer Bank one theme at a time, answering targeted questions so the AI has portable raw material (beliefs, stories, career, skills, voice) to synthesize application answers from — instead of asking you to copy-paste the same answer for every company.",
    whenToUse:
      "When you want to fill in the Answer Bank (or fill in more of it). Run after migrating, and any time you have a new story or belief to add.",
    examplePhrasings: [
      "/seed-answer-bank",
      "Seed my answer bank",
      "Fill out my beliefs",
      "Add a new story to my answer bank",
    ],
    whatItChanges:
      "Writes/updates files under answer-bank/<theme>/<slug>.md. Resumable — skips themes/entries you've already filled. Saves after every answer, so a long session doesn't lose progress.",
  },
  {
    slug: "find-roles",
    command: "/find-roles",
    tagline:
      "Walks every company under companies/interested/, fetches their careers page, filters open roles against your preferences, and drafts one application per match — reusing answers from your Answer Bank where they fit.",
    whenToUse: "When you want a batch of new application drafts to review and submit.",
    examplePhrasings: [
      "/find-roles",
      "Look for new jobs",
      "Scan my interested companies for open roles",
    ],
    whatItChanges:
      "Writes new files to applications/in-review/<company>/<id>.md. Reuses entries from the Answer Bank where they fit. Never submits — always leaves the application as a draft for you to review.",
  },
  {
    slug: "draft-missing-answers",
    command: "/draft-missing-answers",
    tagline:
      "Walk every drafted application under applications/in-review/ and re-synthesize Q&A sections that are still empty, TODO, or partially drafted, drawing on whatever has since been added to your Answer Bank. Never touches sections you've substantively edited.",
    whenToUse:
      "After /seed-answer-bank adds new material, to bulk-rewrite the application drafts /find-roles left with blanks. Re-run any time you fill in more of the Answer Bank.",
    examplePhrasings: [
      "/draft-missing-answers",
      "Fill in the blanks on my drafted applications",
      "Re-synthesize the partial essays now that I've answered more",
    ],
    whatItChanges:
      "Edits Q&A sections in place under applications/in-review/<company>/<id>.md. Idempotent: running it twice in a row with no Answer Bank changes is a no-op. Preserves frontmatter, job description, and any section you've revised by hand.",
  },
  {
    slug: "applicationstatus",
    command: "/applicationstatus",
    tagline:
      "Move an application between status folders. Pure file move — captures the lifecycle in folder location and git history rather than in date fields.",
    whenToUse:
      "When the status of an application changes: applied, got an interview, got an offer, rejected, or archiving it.",
    examplePhrasings: [
      "I applied to Stripe's Staff PD role",
      "Got an interview at Anthropic for Claude Code",
      "Linear rejected me",
      "Got the offer from Figma",
      "Not interested in the Airbnb offline design role",
    ],
    whatItChanges:
      "git mv between applications/<status>/ folders. Six statuses: in-review, applied, interview, rejected, offered, archived.",
  },
  {
    slug: "commitandpush",
    command: "/commitandpush",
    tagline:
      "Commit and push the public scaffolding (skills, docs, web app, examples) while keeping every private file (your applications, companies, answers, context) safely gitignored.",
    whenToUse:
      "When you want to back up or share changes to the public parts of the repo. Run it after editing skills or docs.",
    examplePhrasings: [
      "/commitandpush",
      "Commit and push my changes",
    ],
    whatItChanges:
      "Creates atomic conventional commits and pushes to origin. Never commits private content — gitignore protects you, and the skill verifies before staging.",
  },
];

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{ selected?: string }>;
}

export default async function AiSkillsPage({ searchParams }: PageProps) {
  const { selected } = await searchParams;
  const activeSkill = SKILLS.find((s) => s.slug === selected) ?? null;

  return (
    <div className="flex h-full flex-col lg:flex-row">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden lg:mx-auto lg:max-w-3xl">
        <div className="flex h-full w-full flex-col gap-4 px-4 pt-4 md:pl-0">
          <PageHeader
            title="AI Skills"
            subtitle="Slash commands you can run inside Claude Code to operate careerbot."
          />

          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto pb-8">
            <GlassCard className="p-5 text-sm text-zinc-600 dark:text-zinc-400">
              All skills read from and write to the markdown files in this repo
              — the same files this dashboard renders. Run any of them from
              inside the repo, in Claude Code, by typing the command at the
              prompt.
            </GlassCard>

            <GlassCard className="overflow-hidden">
              <ul className="list-divide">
                {SKILLS.map((skill) => (
                  <SkillRow
                    key={skill.slug}
                    skill={skill}
                    active={skill.slug === selected}
                  />
                ))}
              </ul>
            </GlassCard>
          </div>
        </div>
      </div>

      <DetailSheet
        open={!!activeSkill}
        title={activeSkill?.command ?? ""}
        titleAction={
          activeSkill ? (
            <CopyButton text={activeSkill.command} className="h-9 w-9" />
          ) : null
        }
      >
        {activeSkill ? <SkillDetail skill={activeSkill} /> : null}
      </DetailSheet>
    </div>
  );
}

function SkillRow({ skill, active }: { skill: Skill; active: boolean }) {
  return (
    <li>
      <Link
        href={`/ai-skills?selected=${skill.slug}`}
        className={cn("group list-row", active && "row-selected")}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <code className="rounded-md bg-zinc-900/[0.05] px-1.5 py-0.5 font-mono text-[13px] font-semibold tracking-tight text-zinc-900 dark:bg-white/10 dark:text-zinc-50">
              {skill.command}
            </code>
            <CopyButton text={skill.command} />
          </div>
          <p className="mt-1.5 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">
            {skill.tagline}
          </p>
        </div>
        <ChevronRight className="h-4 w-4 shrink-0 text-zinc-400 transition-transform duration-150 group-hover:translate-x-0.5 dark:text-zinc-500" />
      </Link>
    </li>
  );
}

function SkillDetail({ skill }: { skill: Skill }) {
  return (
    <div className="space-y-6 pt-4">
      <p className="text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300">
        {skill.tagline}
      </p>

      <Detail label="When to use">{skill.whenToUse}</Detail>

      <Detail label="What it changes on disk">{skill.whatItChanges}</Detail>

      <div className="space-y-1.5">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
          Example phrasings
        </div>
        <ul className="space-y-1.5">
          {skill.examplePhrasings.map((phrase) => (
            <li key={phrase}>
              <code className="inline-block rounded bg-zinc-100/70 px-1.5 py-0.5 font-mono text-[12px] text-zinc-700 dark:bg-white/[0.06] dark:text-zinc-300">
                {phrase}
              </code>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Detail({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
        {label}
      </div>
      <div className="text-sm text-zinc-700 dark:text-zinc-300">{children}</div>
    </div>
  );
}
