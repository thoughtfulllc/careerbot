"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { GlassCard } from "@/components/glass-card";
import { StatusSelect } from "@/components/status-select";
import { TabBar } from "@/components/tab-bar";
import { COMPANY_STATUSES, type Company } from "@/lib/types";
import { humanizeSlug } from "@/lib/format";
import { cn } from "@/lib/utils";

type TabSpec = { value: string; label: string };

const TABS: TabSpec[] = [
  { value: "all", label: "All" },
  ...COMPANY_STATUSES.map((s) => ({
    value: s,
    label: humanizeSlug(s),
  })),
];

export function CompaniesTabs({ companies }: { companies: Company[] }) {
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
    if (!selectedId) return;
    const rows =
      active === "all"
        ? companies
        : companies.filter((c) => c.status === active);
    if (rows.some((r) => r.id === selectedId)) return;
    const next = rows[0]?.id ?? "__empty__";
    if (next === selectedId) return;
    router.replace(`${pathname}?selected=${encodeURIComponent(next)}`);
  }, [active, selectedId, companies, router, pathname]);

  const counts = new Map<string, number>();
  counts.set("all", companies.length);
  for (const status of COMPANY_STATUSES) counts.set(status, 0);
  for (const company of companies) {
    if (company.status && counts.has(company.status)) {
      counts.set(company.status, counts.get(company.status)! + 1);
    }
  }

  // Preserve any existing search params (e.g. `selected`) when linking to a row.
  const rowHref = (id: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("selected", id);
    return `/companies?${params.toString()}`;
  };

  return (
    <Tabs value={active} onValueChange={(v) => setActive(v ?? "all")} className="flex h-full flex-col gap-0">
      <TabBar tabs={TABS} counts={counts} active={active} />

      {TABS.map((tab) => {
        const rows =
          tab.value === "all"
            ? companies
            : companies.filter((c) => c.status === tab.value);
        return (
          <TabsContent
            key={tab.value}
            value={tab.value}
            className="flex-1 overflow-y-auto pt-4 pb-8"
          >
            {rows.length === 0 ? (
              <GlassCard className="p-10 text-center text-sm text-zinc-500">
                No companies in this status.
              </GlassCard>
            ) : (
              <GlassCard className="overflow-hidden">
                <ul className="list-divide">
                  {rows.map((company) => (
                    <li key={company.id}>
                      <Link
                        href={rowHref(company.id)}
                        className={cn(
                          "group list-row",
                          company.id === selectedId && "row-selected",
                        )}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="truncate font-medium tracking-tight text-zinc-900 dark:text-zinc-50">
                              {company.name}
                            </span>
                            {company.industry.slice(0, 3).map((tag) => (
                              <IndustryChip key={tag} tag={tag} />
                            ))}
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
                            {company.hq ? <span>{company.hq}</span> : null}
                            {company.remotePolicy ? (
                              <span>{humanizeSlug(company.remotePolicy)}</span>
                            ) : null}
                          </div>
                        </div>
                        <StatusSelect
                          kind="company"
                          id={company.id}
                          status={company.status}
                        />
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

function IndustryChip({ tag }: { tag: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-zinc-100/70 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-zinc-600 ring-1 ring-inset ring-zinc-200/70 dark:bg-white/5 dark:text-zinc-400 dark:ring-white/10">
      {tag}
    </span>
  );
}
