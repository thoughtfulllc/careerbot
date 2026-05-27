"use client";

import * as React from "react";
import { toast } from "sonner";
import { GlassCard } from "@/components/glass-card";
import { ChipInput } from "@/components/chip-input";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Separator } from "@/components/ui/separator";
import type { Preferences } from "@/lib/preferences";
import { savePreferences } from "./actions";
import { useUnsavedChanges } from "@/components/unsaved-changes";

const EQUITY_OPTIONS = [
  { value: "public", label: "Public" },
  { value: "late-stage-private", label: "Late-stage private" },
  { value: "early-stage", label: "Early-stage" },
];

const STAGE_OPTIONS = [
  { value: "seed-A", label: "Seed–Series A" },
  { value: "B-D", label: "Series B–D" },
  { value: "late-stage", label: "Late-stage / pre-IPO" },
  { value: "public", label: "Public / big tech" },
];

export function ConfigurationForm({ initial }: { initial: Preferences }) {
  const [baseline, setBaseline] = React.useState<Preferences>(initial);
  const [prefs, setPrefs] = React.useState<Preferences>(initial);
  const [saving, setSaving] = React.useState(false);

  // Cheap deep-equal: the Preferences object is JSON-safe (strings, numbers,
  // booleans, nulls, arrays of strings), so stringify works.
  const dirty = React.useMemo(
    () => JSON.stringify(prefs) !== JSON.stringify(baseline),
    [prefs, baseline],
  );

  // Push dirty state up to the layout-level provider so navigation guards
  // (side-nav links, browser back, refresh) can warn before discarding.
  const { setDirty } = useUnsavedChanges();
  React.useEffect(() => {
    setDirty(dirty);
  }, [dirty, setDirty]);
  React.useEffect(() => {
    return () => setDirty(false);
  }, [setDirty]);

  const update = <K extends keyof Preferences>(
    section: K,
    updater: (s: Preferences[K]) => Preferences[K],
  ) => {
    setPrefs((p) => ({ ...p, [section]: updater(p[section]) }));
  };

  const toggleInArray = (arr: string[], value: string): string[] =>
    arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value];

  const onSave = async () => {
    setSaving(true);
    try {
      const res = await savePreferences(prefs);
      if (res.ok) {
        setBaseline(prefs);
        toast.success("Preferences saved");
      }
    } catch (err) {
      toast.error("Failed to save", {
        description: (err as Error).message,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Role */}
      <Section
        title="Role"
        description="What you're looking for, broadly."
        usedBy={
          <>
            <SkillTag>/find-roles</SkillTag> filters open postings by title.{" "}
            <SkillTag>/find-companies</SkillTag> checks whether a company is hiring for these titles before researching it.{" "}
            <FilterTag kind="hard" /> Titles to avoid are dropped outright.
          </>
        }
      >
        <Field label="Titles">
          <ChipInput
            value={prefs.role.titles}
            onChange={(titles) => update("role", (r) => ({ ...r, titles }))}
            placeholder="Product Designer"
          />
        </Field>
        <Field label="Track">
          <RadioGroup
            value={prefs.role.track}
            onValueChange={(v) =>
              update("role", (r) => ({ ...r, track: (v as "IC" | "Management") ?? "IC" }))
            }
            className="flex gap-6"
          >
            <RadioWith value="IC" label="Individual contributor" />
            <RadioWith value="Management" label="Management" />
          </RadioGroup>
        </Field>
        <Field label="Specialties">
          <ChipInput
            value={prefs.role.specialties}
            onChange={(specialties) =>
              update("role", (r) => ({ ...r, specialties }))
            }
            placeholder="Product/UX"
          />
        </Field>
        <Field label="Titles to avoid">
          <ChipInput
            value={prefs.role.exclude_titles}
            onChange={(exclude_titles) =>
              update("role", (r) => ({ ...r, exclude_titles }))
            }
            placeholder="Engineering Manager"
          />
        </Field>
      </Section>

      {/* Compensation */}
      <Section
        title="Compensation"
        usedBy={
          <>
            <FilterTag kind="hard" /> <SkillTag>/find-roles</SkillTag> drops any
            posting whose listed comp falls below your min base. Total comp
            target is informational. Equity preferences bias{" "}
            <SkillTag>/find-companies</SkillTag> ranking toward matching stages.
          </>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Min base salary (USD)">
            <Input
              type="number"
              inputMode="numeric"
              value={prefs.compensation.base_min_usd ?? ""}
              onChange={(e) =>
                update("compensation", (c) => ({
                  ...c,
                  base_min_usd: e.target.value === "" ? null : Number(e.target.value),
                }))
              }
              placeholder="150000"
            />
          </Field>
          <Field label="Total comp target (USD, optional)">
            <Input
              type="number"
              inputMode="numeric"
              value={prefs.compensation.total_comp_target_usd ?? ""}
              onChange={(e) =>
                update("compensation", (c) => ({
                  ...c,
                  total_comp_target_usd:
                    e.target.value === "" ? null : Number(e.target.value),
                }))
              }
              placeholder="Leave blank for TBD"
            />
          </Field>
        </div>
        <Field label="Equity preferences">
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            {EQUITY_OPTIONS.map((opt) => (
              <CheckboxWith
                key={opt.value}
                label={opt.label}
                checked={prefs.compensation.equity_open_to.includes(opt.value)}
                onChange={() =>
                  update("compensation", (c) => ({
                    ...c,
                    equity_open_to: toggleInArray(c.equity_open_to, opt.value),
                  }))
                }
              />
            ))}
          </div>
        </Field>
      </Section>

      {/* Location */}
      <Section
        title="Location"
        usedBy={
          <>
            <FilterTag kind="hard" /> Both skills reject postings / companies
            incompatible with your preferred cities and work arrangement. Work
            authorization + sponsorship also auto-fill those exact questions in
            application forms (via{" "}
            <code className="rounded bg-zinc-100/80 px-1 py-0.5 font-mono text-[10px] dark:bg-white/10">
              answer-bank/identity/
            </code>
            ).
          </>
        }
      >
        <Field label="Preferred cities">
          <ChipInput
            value={prefs.location.preferred_cities}
            onChange={(preferred_cities) =>
              update("location", (l) => ({ ...l, preferred_cities }))
            }
            placeholder="San Francisco / Berkeley, CA"
          />
        </Field>
        <Field label="Time zones">
          <ChipInput
            value={prefs.location.time_zones}
            onChange={(time_zones) =>
              update("location", (l) => ({ ...l, time_zones }))
            }
            placeholder="US Pacific"
          />
        </Field>
        <Field label="Open to">
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <CheckboxWith
              label="Remote"
              checked={prefs.location.open_to_remote}
              onChange={() =>
                update("location", (l) => ({ ...l, open_to_remote: !l.open_to_remote }))
              }
            />
            <CheckboxWith
              label="Hybrid"
              checked={prefs.location.open_to_hybrid}
              onChange={() =>
                update("location", (l) => ({ ...l, open_to_hybrid: !l.open_to_hybrid }))
              }
            />
            <CheckboxWith
              label="Onsite"
              checked={prefs.location.open_to_onsite}
              onChange={() =>
                update("location", (l) => ({ ...l, open_to_onsite: !l.open_to_onsite }))
              }
            />
            <CheckboxWith
              label="Relocation"
              checked={prefs.location.open_to_relocation}
              onChange={() =>
                update("location", (l) => ({
                  ...l,
                  open_to_relocation: !l.open_to_relocation,
                }))
              }
            />
          </div>
        </Field>
        <Field label="Work authorization">
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <CheckboxWith
              label="Authorized to work in the US"
              checked={prefs.location.work_auth_us}
              onChange={() =>
                update("location", (l) => ({ ...l, work_auth_us: !l.work_auth_us }))
              }
            />
            <CheckboxWith
              label="Needs visa sponsorship"
              checked={prefs.location.needs_sponsorship}
              onChange={() =>
                update("location", (l) => ({
                  ...l,
                  needs_sponsorship: !l.needs_sponsorship,
                }))
              }
            />
          </div>
        </Field>
      </Section>

      {/* Company */}
      <Section
        title="Company"
        usedBy={
          <>
            Heart of <SkillTag>/find-companies</SkillTag>.{" "}
            <FilterTag kind="hard" /> Industries to avoid and excluded companies
            cause silent skips — nothing in those buckets gets surfaced or
            researched. Stages, size range, and target industries bias the
            candidate search toward your preferences (soft).
          </>
        }
      >
        <Field label="Stages open to">
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            {STAGE_OPTIONS.map((opt) => (
              <CheckboxWith
                key={opt.value}
                label={opt.label}
                checked={prefs.company.stages.includes(opt.value)}
                onChange={() =>
                  update("company", (c) => ({
                    ...c,
                    stages: toggleInArray(c.stages, opt.value),
                  }))
                }
              />
            ))}
          </div>
        </Field>
        <Field label="Size range">
          <Input
            value={prefs.company.size_range}
            onChange={(e) =>
              update("company", (c) => ({ ...c, size_range: e.target.value }))
            }
            placeholder="open / 50–500 / 1000+"
          />
        </Field>
        <Field label="Target industries">
          <ChipInput
            value={prefs.company.industries_want}
            onChange={(industries_want) =>
              update("company", (c) => ({ ...c, industries_want }))
            }
            placeholder="ai-ml"
          />
        </Field>
        <Field label="Industries to avoid (hard filter)">
          <ChipInput
            value={prefs.company.industries_avoid}
            onChange={(industries_avoid) =>
              update("company", (c) => ({ ...c, industries_avoid }))
            }
            placeholder="crypto"
          />
        </Field>
        <Field label="Companies to exclude (hard filter)">
          <ChipInput
            value={prefs.company.excluded_companies}
            onChange={(excluded_companies) =>
              update("company", (c) => ({ ...c, excluded_companies }))
            }
            placeholder="ExampleCo"
          />
        </Field>
      </Section>

      {/* Work */}
      <Section
        title="Work"
        usedBy={
          <>
            Soft ranking signal for both skills.{" "}
            <SkillTag>/find-companies</SkillTag> surfaces &quot;if you like X,
            you might like Y&quot; lookalikes from these.{" "}
            <SkillTag>/find-roles</SkillTag> boosts postings that mention your
            tools, domains, or the kinds of problems you want to work on.
          </>
        }
      >
        <Field label="Design tools">
          <ChipInput
            value={prefs.work.design_tools}
            onChange={(design_tools) =>
              update("work", (w) => ({ ...w, design_tools }))
            }
            placeholder="Figma"
          />
        </Field>
        <Field label="Tech stack to avoid">
          <ChipInput
            value={prefs.work.tech_avoid}
            onChange={(tech_avoid) =>
              update("work", (w) => ({ ...w, tech_avoid }))
            }
            placeholder="Vue"
          />
        </Field>
        <Field label="Domains you're excited about">
          <ChipInput
            value={prefs.work.domains}
            onChange={(domains) => update("work", (w) => ({ ...w, domains }))}
            placeholder="AI products"
          />
        </Field>
        <Field label="Problems you want to work on">
          <Textarea
            value={prefs.work.problems}
            onChange={(e) => update("work", (w) => ({ ...w, problems: e.target.value }))}
            rows={3}
            placeholder="Free-form notes"
          />
        </Field>
      </Section>

      {/* Culture & Schedule */}
      <Section
        title="Culture & Schedule"
        usedBy={
          <>
            Informational context for{" "}
            <SkillTag>/find-roles</SkillTag>: surfaces in the cover-letter
            synthesis when a posting mentions on-call expectations, travel, or
            team rituals you've opted into or out of.
          </>
        }
      >
        <Field label="Hours / on-call expectations">
          <Input
            value={prefs.culture.hours}
            onChange={(e) =>
              update("culture", (c) => ({ ...c, hours: e.target.value }))
            }
            placeholder="standard hours, no on-call"
          />
        </Field>
        <Field label="Travel tolerance">
          <Input
            value={prefs.culture.travel_tolerance}
            onChange={(e) =>
              update("culture", (c) => ({
                ...c,
                travel_tolerance: e.target.value,
              }))
            }
            placeholder="up to 2 trips/quarter"
          />
        </Field>
        <Field label="Async vs synchronous teams">
          <Input
            value={prefs.culture.async_sync}
            onChange={(e) =>
              update("culture", (c) => ({
                ...c,
                async_sync: e.target.value,
              }))
            }
            placeholder="async-first preferred"
          />
        </Field>
        <Field label="Anything else that matters">
          <Textarea
            value={prefs.culture.other}
            onChange={(e) =>
              update("culture", (c) => ({ ...c, other: e.target.value }))
            }
            rows={3}
            placeholder="Free-form notes"
          />
        </Field>
      </Section>

      {/* Voice */}
      <Section
        title="Voice"
        description="Rules for how AI drafts your application prose."
        usedBy={
          <>
            <SkillTag>/find-roles</SkillTag> and{" "}
            <SkillTag>/draft-missing-answers</SkillTag> follow these when
            synthesizing cover letters, &quot;Why us?&quot; essays, and other
            answers. They never touch verbatim job-description text.
          </>
        }
      >
        <Field label="Em dashes">
          <CheckboxWith
            label="Never use em dashes (—) in drafted prose"
            checked={prefs.voice.no_em_dashes}
            onChange={() =>
              update("voice", (v) => ({
                ...v,
                no_em_dashes: !v.no_em_dashes,
              }))
            }
          />
        </Field>
        <Field label="Phrases to avoid">
          <ChipInput
            value={prefs.voice.phrases_to_avoid}
            onChange={(phrases_to_avoid) =>
              update("voice", (v) => ({ ...v, phrases_to_avoid }))
            }
            placeholder="I'm passionate about"
          />
        </Field>
        <Field label="Tone notes">
          <Textarea
            value={prefs.voice.tone_notes}
            onChange={(e) =>
              update("voice", (v) => ({ ...v, tone_notes: e.target.value }))
            }
            rows={3}
            placeholder="direct, occasionally self-deprecating, never gushing"
          />
        </Field>
      </Section>

      <div className="sticky bottom-4 z-10 flex justify-end">
        <GlassCard className="flex items-center gap-3 px-4 py-2 shadow-sm">
          <span className="text-xs text-zinc-500">
            Saves to <code className="font-mono">context/preferences.md</code>
          </span>
          <Button onClick={onSave} disabled={saving}>
            {saving ? "Saving…" : "Save preferences"}
          </Button>
        </GlassCard>
      </div>
    </div>
  );
}

function Section({
  title,
  description,
  usedBy,
  children,
}: {
  title: string;
  description?: string;
  usedBy?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <GlassCard className="p-6">
      <div className="mb-4 space-y-2">
        <h2 className="text-base font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          {title}
        </h2>
        {description ? (
          <p className="text-xs text-zinc-500">{description}</p>
        ) : null}
        {usedBy ? (
          <p className="text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">
            <span className="mr-1 font-semibold uppercase tracking-wider text-zinc-500">
              Used by:
            </span>
            {usedBy}
          </p>
        ) : null}
      </div>
      <Separator className="mb-5" />
      <div className="space-y-5">{children}</div>
    </GlassCard>
  );
}

function SkillTag({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-zinc-900/[0.05] px-1.5 py-0.5 font-mono text-[11px] font-medium text-zinc-700 dark:bg-white/10 dark:text-zinc-200">
      {children}
    </code>
  );
}

function FilterTag({ kind }: { kind: "hard" | "soft" }) {
  if (kind === "hard") {
    return (
      <span className="inline-flex items-center rounded-full bg-rose-100/70 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-rose-700 ring-1 ring-inset ring-rose-200/70 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/20">
        Hard filter
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-zinc-100/70 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-600 ring-1 ring-inset ring-zinc-200/70 dark:bg-white/5 dark:text-zinc-400 dark:ring-white/10">
      Soft preference
    </span>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label className="text-xs uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
        {label}
      </Label>
      {children}
    </div>
  );
}

function CheckboxWith({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: () => void;
}) {
  const id = React.useId();
  return (
    <div className="flex items-center gap-2">
      <Checkbox id={id} checked={checked} onCheckedChange={onChange} />
      <Label htmlFor={id} className="cursor-pointer text-sm font-normal text-zinc-700 dark:text-zinc-200">
        {label}
      </Label>
    </div>
  );
}

function RadioWith({ value, label }: { value: string; label: string }) {
  const id = React.useId();
  return (
    <div className="flex items-center gap-2">
      <RadioGroupItem value={value} id={id} />
      <Label htmlFor={id} className="cursor-pointer text-sm font-normal text-zinc-700 dark:text-zinc-200">
        {label}
      </Label>
    </div>
  );
}

