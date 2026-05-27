"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { GlassCard } from "@/components/glass-card";
import { ApplicationRowStatus } from "@/components/application-row-status";
import { ApplicationRowContextMenu } from "@/components/application-row-context-menu";
import { TabBar } from "@/components/tab-bar";
import { APPLICATION_STATUSES, type Application } from "@/lib/types";
import { formatRelativeDays, formatSalaryRange } from "@/lib/format";
import { cn } from "@/lib/utils";
import { rowHref } from "@/lib/row-href";
import { useApplicationsSearch } from "./search-context";

type TabSpec = { value: string; label: string };

const TABS: TabSpec[] = APPLICATION_STATUSES.map((s) => ({
  value: s,
  label: s
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" "),
}));

export function ApplicationsTabs({ applications }: { applications: Application[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get("selected");
  const [active, setActive] = React.useState<string>(APPLICATION_STATUSES[0]);
  const search = useApplicationsSearch();
  const query = (search?.query ?? "").trim().toLowerCase();

  const visible = React.useMemo(() => {
    if (!query) return applications;
    return applications.filter((a) => {
      const haystack = [a.title, a.companyName, a.location]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [applications, query]);

  // When the panel is open, swapping tabs should auto-select the first row of
  // the new tab. If the currently-selected row already belongs to the new tab,
  // keep it. If the new tab has no rows, push a sentinel so the panel stays
  // open and renders an empty state.
  React.useEffect(() => {
    if (!selectedId) return; // panel closed — leave URL alone
    const rows = visible.filter((a) => a.status === active);
    if (rows.some((r) => r.id === selectedId)) return;
    const next = rows[0]?.id ?? "__empty__";
    if (next === selectedId) return;
    router.replace(`${pathname}?selected=${encodeURIComponent(next)}`);
  }, [active, selectedId, visible, router, pathname]);

  const counts = new Map<string, number>();
  for (const status of APPLICATION_STATUSES) counts.set(status, 0);
  for (const app of visible) {
    if (app.status && counts.has(app.status)) {
      counts.set(app.status, counts.get(app.status)! + 1);
    }
  }

  return (
    <Tabs value={active} onValueChange={(v) => setActive(v ?? APPLICATION_STATUSES[0])} className="flex h-full flex-col gap-0">
      <TabBar tabs={TABS} counts={counts} active={active} />

      {TABS.map((tab) => {
        const rows = visible.filter((a) => a.status === tab.value);
        return (
          <TabsContent
            key={tab.value}
            value={tab.value}
            className="flex-1 overflow-y-auto pt-4 pb-8"
          >
            {rows.length === 0 ? (
              <GlassCard className="p-10 text-center text-sm text-zinc-500">
                No applications in this status.
              </GlassCard>
            ) : (
              <GlassCard className="overflow-hidden">
                <ul className="list-divide">
                  {rows.map((app) => (
                    <li key={app.id}>
                      <ApplicationRowContextMenu id={app.id} status={app.status}>
                      <Link
                        href={rowHref("/applications", app.id, searchParams)}
                        className={cn(
                          "group list-row",
                          app.id === selectedId && "row-selected",
                        )}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="truncate font-medium tracking-tight text-zinc-900 dark:text-zinc-50">
                              {app.title}
                            </span>
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
                            {app.companyName ? (
                              <span className="text-zinc-600 dark:text-zinc-400">
                                {app.companyName}
                              </span>
                            ) : null}
                            {app.salaryMin != null || app.salaryMax != null ? (
                              <span>
                                {formatSalaryRange(app.salaryMin, app.salaryMax)}
                              </span>
                            ) : null}
                          </div>
                          {app.location ? (
                            <div className="mt-0.5 text-xs text-zinc-500">
                              {app.location}
                            </div>
                          ) : null}
                        </div>
                        <div className="flex shrink-0 flex-col items-end justify-between self-stretch">
                          {app.postedAt ? (
                            <span
                              title={app.postedAt}
                              className="text-xs text-zinc-500 dark:text-zinc-400"
                            >
                              {formatRelativeDays(app.postedAt)}
                            </span>
                          ) : (
                            <span />
                          )}
                          <ApplicationRowStatus id={app.id} status={app.status} />
                        </div>
                      </Link>
                      </ApplicationRowContextMenu>
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
