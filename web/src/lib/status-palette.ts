import type { ApplicationStatus, CompanyStatus } from "@/lib/types";

export const APPLICATION_PALETTE: Record<ApplicationStatus, string> = {
  "in-review":
    "bg-amber-100/70 text-amber-800 ring-amber-200/70 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/20",
  applied:
    "bg-blue-100/70 text-blue-800 ring-blue-200/70 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-400/20",
  interview:
    "bg-violet-100/70 text-violet-800 ring-violet-200/70 dark:bg-violet-500/10 dark:text-violet-300 dark:ring-violet-400/20",
  rejected:
    "bg-rose-100/70 text-rose-800 ring-rose-200/70 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-400/20",
  offered:
    "bg-emerald-100/70 text-emerald-800 ring-emerald-200/70 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/20",
  archived:
    "bg-zinc-100/70 text-zinc-700 ring-zinc-200/70 dark:bg-zinc-500/10 dark:text-zinc-300 dark:ring-zinc-400/20",
};

export const COMPANY_PALETTE: Record<CompanyStatus, string> = {
  "in-review":
    "bg-zinc-100/70 text-zinc-700 ring-zinc-200/70 dark:bg-white/5 dark:text-zinc-300 dark:ring-white/10",
  interested:
    "bg-blue-100/70 text-blue-800 ring-blue-200/70 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-400/20",
  "not-interested":
    "bg-rose-100/70 text-rose-800 ring-rose-200/70 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-400/20",
};

export const STATUS_FALLBACK =
  "bg-zinc-100/70 text-zinc-700 ring-zinc-200/70 dark:bg-white/5 dark:text-zinc-300 dark:ring-white/10";
