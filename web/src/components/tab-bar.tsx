"use client";

import { TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { useTabIndicator } from "@/lib/use-tab-indicator";

interface TabBarProps<T extends string> {
  tabs: { value: T; label: string }[];
  counts: Map<T, number>;
  active: T;
}

export function TabBar<T extends string>({
  tabs,
  counts,
  active,
}: TabBarProps<T>) {
  const { listRef, setTriggerRef, indicator, firstPaint } = useTabIndicator(active);

  return (
    <div className="shrink-0 border-b border-zinc-200/70 dark:border-white/10">
      <TabsList
        ref={listRef}
        className="relative flex w-full flex-nowrap justify-start gap-1 overflow-x-auto bg-transparent p-0 group-data-horizontal/tabs:h-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {indicator ? (
          <div
            aria-hidden
            className={cn(
              "pointer-events-none absolute -bottom-px left-0 z-10 h-[2.5px] rounded-full bg-zinc-900 dark:bg-white",
              firstPaint ? "" : "transition-all duration-300 ease-out",
            )}
            style={{ transform: `translateX(${indicator.left}px)`, width: indicator.width }}
          />
        ) : null}

        {tabs.map((tab) => {
          const count = counts.get(tab.value) ?? 0;
          const isActive = active === tab.value;
          return (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              ref={setTriggerRef(tab.value)}
              className={cn(
                "relative z-10 h-10 shrink-0 bg-transparent px-4 text-sm transition-colors",
                "before:absolute before:inset-x-0 before:top-1 before:bottom-1.5 before:rounded-md before:transition-colors before:content-['']",
                "data-active:bg-transparent data-active:border-transparent data-active:shadow-none dark:data-active:bg-transparent dark:data-active:border-transparent",
                isActive
                  ? "text-zinc-900 dark:text-zinc-50"
                  : "text-zinc-500 hover:text-zinc-900 hover:before:bg-zinc-100/60 dark:text-zinc-400 dark:hover:text-zinc-50 dark:hover:before:bg-white/[0.04]",
              )}
            >
              <span className={isActive ? "font-medium" : ""}>{tab.label}</span>
              <span className="ml-1 text-xs tabular-nums text-zinc-500 dark:text-zinc-500">
                {count}
              </span>
            </TabsTrigger>
          );
        })}
      </TabsList>
    </div>
  );
}
