"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { GlassCard } from "@/components/glass-card";
import { TabBar } from "@/components/tab-bar";
import {
  ANSWER_THEMES,
  type AnswerBankEntry,
  type AnswerTheme,
} from "@/lib/types";
import { formatDate, humanizeSlug } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useUnsavedChanges } from "@/components/unsaved-changes";
import {
  parseAnsweredFilter,
  type AnsweredFilter,
} from "./answer-state-filter";

type TabValue = "all" | AnswerTheme;
type TabSpec = { value: TabValue; label: string };

const TABS: TabSpec[] = [
  { value: "all", label: "All" },
  ...ANSWER_THEMES.map((t) => ({ value: t, label: humanizeSlug(t) })),
];

function rowsFor(
  tab: TabValue,
  answered: AnsweredFilter,
  entries: AnswerBankEntry[],
): AnswerBankEntry[] {
  const byTheme = tab === "all" ? entries : entries.filter((e) => e.theme === tab);
  if (answered === "all") return byTheme;
  if (answered === "unanswered") return byTheme.filter((e) => e.canonicalAnswer === null);
  return byTheme.filter((e) => e.canonicalAnswer !== null);
}

export function AnswerBankTabs({ entries }: { entries: AnswerBankEntry[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get("selected");
  const answered = parseAnsweredFilter(searchParams.get("answered"));
  const [active, setActive] = React.useState<TabValue>("all");

  // When the panel is open, swapping tabs (or changing the answered filter)
  // should auto-select the first row of the new view. If the currently-selected
  // row already belongs to the new view, keep it. If the new view has no rows,
  // push a sentinel so the panel stays open and renders an empty state.
  React.useEffect(() => {
    if (!selectedId) return;
    const rows = rowsFor(active, answered, entries);
    if (rows.some((r) => r.id === selectedId)) return;
    const next = rows[0]?.id ?? "__empty__";
    if (next === selectedId) return;
    const params = new URLSearchParams(searchParams.toString());
    params.set("selected", next);
    router.replace(`${pathname}?${params.toString()}`);
  }, [active, answered, selectedId, entries, router, pathname, searchParams]);

  const counts = new Map<TabValue, number>(
    TABS.map((tab) => [tab.value, rowsFor(tab.value, answered, entries).length]),
  );

  const rowHref = (id: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("selected", id);
    return `/answer-bank?${params.toString()}`;
  };

  // When the editor has unsaved changes, navigating to another row should
  // warn first. We synchronously preventDefault, then defer the actual
  // router.push to after the user confirms.
  const { dirty, confirmDiscard } = useUnsavedChanges();
  const onRowClick = (e: React.MouseEvent<HTMLAnchorElement>, href: string) => {
    if (!dirty) return;
    e.preventDefault();
    confirmDiscard().then((ok) => {
      if (ok) router.push(href);
    });
  };

  return (
    <Tabs
      value={active}
      onValueChange={(v) => {
        const next = TABS.find((t) => t.value === v)?.value ?? "all";
        setActive(next);
      }}
      className="flex h-full flex-col gap-0"
    >
      <TabBar tabs={TABS} counts={counts} active={active} />

      {TABS.map((tab) => {
        const rows = rowsFor(tab.value, answered, entries);
        return (
          <TabsContent
            key={tab.value}
            value={tab.value}
            className="flex-1 overflow-y-auto pt-4 pb-8"
          >
            {rows.length === 0 ? (
              <GlassCard className="p-10 text-center text-sm text-zinc-500">
                {answered === "unanswered" ? (
                  <>
                    Nothing unanswered here. Run <code className="font-mono text-xs">/find-roles</code> in Claude Code to generate new questions as you apply to roles.
                  </>
                ) : answered === "answered" ? (
                  <>
                    Nothing answered here yet. Run <code className="font-mono text-xs">/seed-answer-bank</code> in Claude Code to fill in stubs.
                  </>
                ) : (
                  <>
                    No entries in this category yet. Run <code className="font-mono text-xs">/seed-answer-bank</code> in Claude Code to fill it in.
                  </>
                )}
              </GlassCard>
            ) : (
              <GlassCard className="overflow-hidden">
                <ul className="list-divide">
                  {rows.map((entry) => (
                    <li key={entry.id}>
                      <Link
                        href={rowHref(entry.id)}
                        onClick={(e) => onRowClick(e, rowHref(entry.id))}
                        className={cn(
                          "group list-row",
                          entry.id === selectedId && "row-selected",
                        )}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-medium tracking-tight text-zinc-900 dark:text-zinc-50">
                            {entry.question}
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-1.5">
                            {answered === "all" && entry.canonicalAnswer === null ? (
                              <UnansweredChip />
                            ) : null}
                            {tab.value === "all" && entry.theme ? (
                              <ThemeChip theme={entry.theme} />
                            ) : null}
                            {entry.tags.slice(0, 6).map((tag) => (
                              <TagChip key={tag} tag={tag} />
                            ))}
                          </div>
                        </div>
                        <div className="hidden text-right text-xs text-zinc-500 sm:block">
                          {entry.lastUpdated ? (
                            <>
                              <div>Updated</div>
                              <div className="text-zinc-700 dark:text-zinc-300">
                                {formatDate(entry.lastUpdated)}
                              </div>
                            </>
                          ) : null}
                        </div>
                        <ChevronRight className="h-4 w-4 text-zinc-400 transition-transform duration-150 group-hover:translate-x-0.5 dark:text-zinc-500" />
                      </Link>
                    </li>
                  ))}
                </ul>
              </GlassCard>
            )}
          </TabsContent>
        );
      })}
    </Tabs>
  );
}

function TagChip({ tag }: { tag: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-zinc-100/70 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-zinc-500 ring-1 ring-inset ring-zinc-200/70 dark:bg-white/5 dark:text-zinc-400 dark:ring-white/10">
      {tag}
    </span>
  );
}

function UnansweredChip() {
  return (
    <span className="inline-flex items-center rounded-full bg-amber-100/70 px-2 py-0.5 text-[10px] font-medium tracking-tight text-amber-800 ring-1 ring-inset ring-amber-200/70 dark:bg-amber-400/10 dark:text-amber-300 dark:ring-amber-400/20">
      Unanswered
    </span>
  );
}

function ThemeChip({ theme }: { theme: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-zinc-900/[0.04] px-2 py-0.5 text-[10px] font-medium tracking-tight text-zinc-700 ring-1 ring-inset ring-zinc-200/70 dark:bg-white/5 dark:text-zinc-300 dark:ring-white/10">
      {humanizeSlug(theme)}
    </span>
  );
}
