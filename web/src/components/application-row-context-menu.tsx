"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuGroup,
  ContextMenuLabel,
  ContextMenuRadioGroup,
  ContextMenuRadioItem,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { humanizeSlug } from "@/lib/format";
import {
  APPLICATION_STATUSES,
  type ApplicationStatus,
} from "@/lib/types";
import { updateApplication } from "@/app/applications/[id]/actions";

interface ApplicationRowContextMenuProps {
  id: string;
  status: ApplicationStatus | null;
  children: React.ReactNode;
}

/**
 * Right-click anywhere on an application row to open a menu listing every
 * status. Picking one moves the markdown file via the existing
 * `updateApplication` server action. Coexists with the row's hover icon
 * buttons; left-click navigation is unaffected.
 */
export function ApplicationRowContextMenu({
  id,
  status,
  children,
}: ApplicationRowContextMenuProps) {
  const router = useRouter();
  const [, startTransition] = React.useTransition();

  const handleChange = (value: string) => {
    const next = value as ApplicationStatus;
    if (next === status) return;
    startTransition(async () => {
      try {
        await updateApplication(id, { status: next });
        toast.success(humanizeSlug(next));
        router.refresh();
      } catch (err) {
        toast.error("Failed to update status", {
          description: (err as Error).message,
        });
      }
    });
  };

  return (
    <ContextMenu>
      <ContextMenuTrigger className="contents">{children}</ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuGroup>
          <ContextMenuLabel>Move to</ContextMenuLabel>
          <ContextMenuRadioGroup
            value={status ?? undefined}
            onValueChange={handleChange}
          >
            {APPLICATION_STATUSES.map((s) => (
              <ContextMenuRadioItem
                key={s}
                value={s}
                className="data-checked:text-blue-600 dark:data-checked:text-blue-400"
              >
                {humanizeSlug(s)}
              </ContextMenuRadioItem>
            ))}
          </ContextMenuRadioGroup>
        </ContextMenuGroup>
      </ContextMenuContent>
    </ContextMenu>
  );
}
