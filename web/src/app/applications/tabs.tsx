"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { GlassCard } from "@/components/glass-card";
import { StatusSelect } from "@/components/status-select";
import { TabBar } from "@/components/tab-bar";
import { APPLICATION_STATUSES, type Application } from "@/lib/types";
import { formatDate, formatSalaryRange } from "@/lib/format";
import { cn } from "@/lib/utils";

type TabSpec = { value: string; label: string };

const TABS: TabSpec[] = [
  { value: "all", label: "All" },
  ...APPLICATION_STATUSES.map((s) => ({
    value: s,
    label: s
      .split("-")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" "),
  })),
];

export function ApplicationsTabs({ applications }: { applications: Application[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get("selected");
  const [active, setActive] = React.useState("all");

  // When the panel is open, swapping tabs should auto-select the first row of
  // the new tab. If the currently-selected row already belongs to the new tab,
  // keep it. If the new tab has no rows, push a sentinel so the panel stays
  // open and renders an empty state.
  React.useEffect(() => {
    if (!selectedId) return; // panel closed — leave URL alone
    const rows =
      active === "all"
        ? applications
        : applications.filter((a) => a.status === active);
    if (rows.some((r) => r.id === selectedId)) return;
    const next = rows[0]?.id ?? "__empty__";
    if (next === selectedId) return;
    router.replace(`${pathname}?selected=${encodeURIComponent(next)}`);
  }, [active, selectedId, applications, router, pathname]);

  const counts = new Map<string, number>();
  counts.set("all", applications.length);
  for (const status of APPLICATION_STATUSES) counts.set(status, 0);
  for (const app of applications) {
    if (app.status && counts.has(app.status)) {
      counts.set(app.status, counts.get(app.status)! + 1);
    }
  }

  return (
    <Tabs value={active} onValueChange={(v) => setActive(v ?? "all")} className="flex h-full flex-col gap-0">
      <TabBar tabs={TABS} counts={counts} active={active} />

      {TABS.map((tab) => {
        const rows =
          tab.value === "all"
            ? applications
            : applications.filter((a) => a.status === tab.value);
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
                      <Link
                        href={`/applications?selected=${app.id}`}
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
                            {app.location ? <span>{app.location}</span> : null}
                            {app.salaryMin != null || app.salaryMax != null ? (
                              <span>
                                {formatSalaryRange(app.salaryMin, app.salaryMax)}
                              </span>
                            ) : null}
                          </div>
                        </div>
                        <div className="hidden text-xs text-zinc-500 sm:block">
                          {formatDate(app.dateFound)}
                        </div>
                        <StatusSelect kind="application" id={app.id} status={app.status} />
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
