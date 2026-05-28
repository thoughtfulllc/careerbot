"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Bot,
  Briefcase,
  Building2,
  MessageSquareText,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ThemeToggle } from "./theme-toggle";
import { useUnsavedChanges } from "./unsaved-changes";

interface NavItem {
  href: string;
  label: string;
  icon: typeof Briefcase;
}

const NAV: NavItem[] = [
  { href: "/applications", label: "Applications", icon: Briefcase },
  { href: "/companies", label: "Companies", icon: Building2 },
  { href: "/answer-bank", label: "Answer Bank", icon: MessageSquareText },
  { href: "/configuration", label: "Configuration", icon: Bot },
];

const STORAGE_KEY = "careerbot-sidenav-collapsed";

function NavLinks({
  items,
  pathname,
  collapsed,
  onNavigate,
}: {
  items: NavItem[];
  pathname: string;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const router = useRouter();
  const { dirty, confirmDiscard } = useUnsavedChanges();
  const guardedClick = (
    e: React.MouseEvent<HTMLAnchorElement>,
    href: string,
  ) => {
    if (!dirty) {
      onNavigate?.();
      return;
    }
    e.preventDefault();
    void confirmDiscard().then((ok) => {
      if (ok) {
        onNavigate?.();
        router.push(href);
      }
    });
  };

  return (
    <nav className="flex flex-col gap-1">
      {items.map((item) => {
        const active =
          pathname === item.href || pathname.startsWith(item.href + "/");
        const Icon = item.icon;
        const link = (
          <Link
            key={item.href}
            href={item.href}
            onClick={(e) => guardedClick(e, item.href)}
            className={cn(
              "flex items-center text-sm transition-colors duration-150",
              collapsed
                ? "size-10 justify-center self-center rounded-full"
                : "gap-3 rounded-xl px-3 py-2",
              active
                ? "bg-zinc-900/5 text-zinc-900 dark:bg-white/10 dark:text-zinc-50"
                : "text-zinc-600 hover:bg-zinc-900/10 hover:text-zinc-900 dark:text-zinc-300 dark:hover:bg-white/10 dark:hover:text-zinc-50",
            )}
          >
            <Icon className="h-4 w-4 shrink-0" />
            {collapsed ? (
              <span className="sr-only">{item.label}</span>
            ) : (
              <span className="tracking-tight">{item.label}</span>
            )}
          </Link>
        );
        if (collapsed) {
          return (
            <Tooltip key={item.href}>
              <TooltipTrigger render={link} />
              <TooltipContent side="right">{item.label}</TooltipContent>
            </Tooltip>
          );
        }
        return link;
      })}
    </nav>
  );
}

function Brand({ collapsed }: { collapsed: boolean }) {
  return (
    <div
      className={cn(
        "flex items-center gap-2",
        collapsed ? "justify-center px-0" : "px-1",
      )}
    >
      <div className="relative h-8 w-8 shrink-0">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/careerbot-mark-ink.svg"
          alt=""
          aria-hidden
          className="absolute inset-0 h-full w-full dark:hidden"
        />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/careerbot-mark-paper.svg"
          alt=""
          aria-hidden
          className="absolute inset-0 hidden h-full w-full dark:block"
        />
      </div>
      {collapsed ? null : (
        <span className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Careerbot
        </span>
      )}
    </div>
  );
}

export function SideNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { dirty, confirmDiscard } = useUnsavedChanges();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);

  const guardedAiSkillsClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (!dirty) return;
    e.preventDefault();
    void confirmDiscard().then((ok) => {
      if (ok) router.push("/ai-skills");
    });
  };

  // Hydrate from localStorage after mount so SSR + first render match.
  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "1") setCollapsed(true);
    setMounted(true);
  }, []);

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      if (mounted) {
        window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      }
      return next;
    });
  };

  const PanelIcon = collapsed ? PanelLeftOpen : PanelLeftClose;

  return (
    <>
      {/* Desktop */}
      <aside
        className={cn(
          "sticky top-0 hidden h-screen shrink-0 p-4 transition-[width] duration-200 ease-out md:flex",
          collapsed ? "w-[5.5rem]" : "w-60",
        )}
      >
        <div
          className={cn(
            "glass-strong relative flex h-full w-full flex-col gap-6 overflow-hidden rounded-2xl",
            "p-2",
          )}
        >
          {/* subtle gradient overlay on the sidenav */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-gradient-to-b from-white/40 to-transparent dark:from-white/[0.04] dark:to-transparent"
          />

          <div
            className={cn(
              "relative z-10 flex items-center gap-2",
              collapsed ? "justify-center" : "justify-between",
            )}
          >
            {collapsed ? null : <Brand collapsed={false} />}
            <button
              type="button"
              onClick={toggleCollapsed}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-zinc-500 transition-colors hover:bg-zinc-900/10 hover:text-zinc-900 dark:hover:bg-white/10 dark:hover:text-zinc-50"
            >
              <PanelIcon className="h-4 w-4" />
            </button>
          </div>

          <div className="relative z-10 flex-1">
            <NavLinks items={NAV} pathname={pathname} collapsed={collapsed} />
          </div>

          <div className="relative z-10 flex flex-col gap-3">
            <div
              className={cn(
                "flex gap-1",
                collapsed
                  ? "flex-col items-center"
                  : "items-center justify-end px-1",
              )}
            >
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Link
                      href="/ai-skills"
                      aria-label="AI Skills"
                      onClick={guardedAiSkillsClick}
                      className={cn(
                        "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors",
                        pathname === "/ai-skills" || pathname.startsWith("/ai-skills/")
                          ? "bg-zinc-900/[0.05] text-zinc-900 dark:bg-white/10 dark:text-zinc-50"
                          : "text-zinc-600 hover:bg-zinc-900/10 hover:text-zinc-900 dark:text-zinc-300 dark:hover:bg-white/10 dark:hover:text-zinc-50",
                      )}
                    >
                      <Sparkles className="h-4 w-4" />
                    </Link>
                  }
                />
                <TooltipContent side="top">AI Skills</TooltipContent>
              </Tooltip>
              <ThemeToggle />
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile */}
      <div className="sticky top-0 z-30 flex items-center justify-between gap-2 p-4 md:hidden">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger className="glass inline-flex h-9 w-9 items-center justify-center rounded-full text-zinc-700 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-zinc-50">
            <Menu className="h-5 w-5" />
            <span className="sr-only">Open menu</span>
          </SheetTrigger>
          <SheetContent side="left" className="w-72 p-4">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <div className="flex h-full flex-col gap-6">
              <Brand collapsed={false} />
              <NavLinks
                items={NAV}
                pathname={pathname}
                collapsed={false}
                onNavigate={() => setOpen(false)}
              />
            </div>
          </SheetContent>
        </Sheet>
        <Brand collapsed={false} />
        <ThemeToggle />
      </div>
    </>
  );
}
