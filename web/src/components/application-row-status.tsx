"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Archive,
  CalendarCheck,
  Loader2,
  PartyPopper,
  Send,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { humanizeSlug } from "@/lib/format";
import type { ApplicationStatus } from "@/lib/types";
import { updateApplication } from "@/app/applications/[id]/actions";

// Order: backward / negative step on the left, forward / positive step on the right.
const NEXT_STEPS: Partial<Record<ApplicationStatus, ApplicationStatus[]>> = {
  "in-review": ["archived", "applied"],
  applied: ["rejected", "interview"],
  interview: ["rejected", "offered"],
};

const ACTION_ICON: Record<ApplicationStatus, LucideIcon> = {
  "in-review": Send,
  applied: Send,
  archived: Archive,
  interview: CalendarCheck,
  rejected: XCircle,
  offered: PartyPopper,
};

interface ApplicationRowStatusProps {
  id: string;
  status: ApplicationStatus | null;
}

/** Next-step icon buttons for an application row. */
export function ApplicationRowStatus({ id, status }: ApplicationRowStatusProps) {
  const router = useRouter();
  const [current, setCurrent] = React.useState<ApplicationStatus | null>(status);
  const [pending, setPending] = React.useState<ApplicationStatus | null>(null);

  React.useEffect(() => {
    setCurrent(status);
  }, [status]);

  const nextOptions = current ? NEXT_STEPS[current] : undefined;
  if (!nextOptions) return null;

  const apply = (target: ApplicationStatus) => {
    const prev = current;
    setCurrent(target);
    setPending(target);
    (async () => {
      try {
        await updateApplication(id, { status: target });
        toast.success(
          humanizeSlug(target),
          prev
            ? {
                action: {
                  label: "Undo",
                  onClick: async () => {
                    setCurrent(prev);
                    setPending(prev);
                    try {
                      await updateApplication(id, { status: prev });
                      toast.success(humanizeSlug(prev));
                      router.refresh();
                    } catch (err) {
                      toast.error("Failed to undo status change", {
                        description: (err as Error).message,
                      });
                      setCurrent(target);
                    } finally {
                      setPending(null);
                    }
                  },
                },
              }
            : undefined,
        );
        router.refresh();
      } catch (err) {
        toast.error("Failed to update status", {
          description: (err as Error).message,
        });
        setCurrent(prev);
      } finally {
        setPending(null);
      }
    })();
  };

  return (
    <span
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
      onPointerDown={(e) => e.stopPropagation()}
      className="inline-flex shrink-0 items-center gap-1"
    >
      <TooltipProvider delay={0}>
        {nextOptions.map((opt) => {
          const Icon = ACTION_ICON[opt];
          const label = humanizeSlug(opt);
          return (
            <Tooltip key={opt}>
              <TooltipTrigger
                render={
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={label}
                    disabled={pending !== null}
                    className="size-8 cursor-pointer rounded-sm text-zinc-500 hover:bg-zinc-900/10 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-zinc-50"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      apply(opt);
                    }}
                  >
                    {pending === opt ? (
                      <Loader2 className="size-4 animate-spin" strokeWidth={1.5} />
                    ) : (
                      <Icon className="size-4" strokeWidth={1.5} />
                    )}
                  </Button>
                }
              />
              <TooltipContent side="top">{label}</TooltipContent>
            </Tooltip>
          );
        })}
      </TooltipProvider>
    </span>
  );
}
