export type ApplicationStatus =
  | "in-review"
  | "applied"
  | "interview"
  | "rejected"
  | "offered"
  | "withdrawn"
  | "not-interested";

export type ApplicationSource =
  | "greenhouse"
  | "lever"
  | "ashby"
  | "workday"
  | "careers-page"
  | "other";

export type CompanyStatus = "in-review" | "interested" | "not-interested";

export type RemotePolicy = "remote" | "hybrid" | "onsite";

export type AnswerTheme =
  | "identity"
  | "beliefs"
  | "stories"
  | "career"
  | "skills"
  | "voice";

export interface Application {
  id: string;
  title: string;
  companyIds: string[];
  companyName: string | null;
  status: ApplicationStatus | null;
  atsId: string | null;
  url: string | null;
  source: ApplicationSource | null;
  postedAt: string | null;
  dateFound: string | null;
  salaryMin: number | null;
  salaryMax: number | null;
  location: string | null;
  notes: string | null;
  matchScore: number | null;
}

export interface Company {
  id: string;
  name: string;
  slug: string | null;
  status: CompanyStatus | null;
  industry: string[];
  matchScore: number | null;
  size: string | null;
  hq: string | null;
  remotePolicy: RemotePolicy | null;
  researchedOn: string | null;
  notInterestedReason: string | null;
  careersUrl: string | null;
}

export interface AnswerBankEntry {
  id: string;
  question: string;
  theme: AnswerTheme | null;
  tags: string[];
  canonicalAnswer: string | null;
  /** File mtime — when the markdown was last edited. Read-only; derived. */
  lastUpdated: string | null;
}

export type RenderableBlock =
  | { kind: "heading_1"; text: InlineSegment[] }
  | { kind: "heading_2"; text: InlineSegment[] }
  | { kind: "heading_3"; text: InlineSegment[] }
  | { kind: "paragraph"; text: InlineSegment[] }
  | { kind: "bulleted_list_item"; text: InlineSegment[] }
  | { kind: "numbered_list_item"; text: InlineSegment[] }
  | { kind: "code"; text: InlineSegment[]; language: string | null }
  | { kind: "callout"; text: InlineSegment[]; emoji: string | null }
  | { kind: "divider" }
  | { kind: "unsupported"; type: string };

export interface InlineSegment {
  text: string;
  bold: boolean;
  italic: boolean;
  code: boolean;
  underline: boolean;
  strikethrough: boolean;
  href: string | null;
}

export const APPLICATION_STATUSES: ApplicationStatus[] = [
  "in-review",
  "applied",
  "interview",
  "rejected",
  "offered",
  "withdrawn",
  "not-interested",
];

export const COMPANY_STATUSES: CompanyStatus[] = [
  "in-review",
  "interested",
  "not-interested",
];

export const ANSWER_THEMES: AnswerTheme[] = [
  "identity",
  "beliefs",
  "stories",
  "career",
  "skills",
  "voice",
];

export const APPLICATION_SOURCES: ApplicationSource[] = [
  "greenhouse",
  "lever",
  "ashby",
  "workday",
  "careers-page",
  "other",
];

export const REMOTE_POLICIES: RemotePolicy[] = ["remote", "hybrid", "onsite"];
