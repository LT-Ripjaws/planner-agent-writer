export type Tone = "neutral" | "technical" | "casual" | "authoritative";

export type BlogKind =
  | "auto"
  | "explainer"
  | "tutorial"
  | "news_roundup"
  | "comparison"
  | "system_design";

export type PlannedBlogKind = Exclude<BlogKind, "auto">;

export type ResearchMode = "auto" | "required" | "off";

export type BlogRunStatus =
  | "queued"
  | "running"
  | "awaiting_approval"
  | "completed"
  | "completed_with_warnings"
  | "failed"
  | (string & {});

export interface BlogRunCreate {
  topic: string;
  audience?: string | null;
  tone?: Tone;
  blog_kind?: BlogKind;
  research_mode?: ResearchMode;
}

export interface BlogRunSummary {
  id: string;
  topic: string;
  status: BlogRunStatus;
  progress_step: string;
  mode?: string | null;
  blog_title?: string | null;
  created_at: string;
  updated_at: string;
}

export interface BlogRunDetail extends BlogRunSummary {
  error?: string | null;
  warnings: string[];
  plan?: Plan | null;
}

export interface BlogRunResult {
  id: string;
  markdown: string;
  plan?: Plan | null;
  evidence: EvidenceItem[];
  citations: Record<string, unknown>[];
  quality_report?: QualityReport | null;
}

export interface EvidenceItem {
  title: string;
  url: string;
  published_at?: string | null;
  snippet: string;
  source?: string | null;
  score?: number | null;
}

export interface Task {
  id: number;
  title: string;
  goal: string;
  bullets: string[];
  target_words: number;
  tags: string[];
  requires_research: boolean;
  requires_citations: boolean;
  requires_code: boolean;
}

export interface Plan {
  blog_title: string;
  audience: string;
  tone: string;
  blog_kind: PlannedBlogKind;
  constraints: string[];
  tasks: Task[];
}

export type IssueCategory =
  | "off_topic"
  | "incomplete"
  | "tone"
  | "missing_code"
  | "length";

export type Severity = "low" | "medium" | "high";

export interface QualityIssue {
  task_id: number;
  category: IssueCategory;
  severity: Severity;
  description: string;
}

export interface HallucinationFlag {
  task_id: number;
  claim: string;
  severity: Severity;
  rationale: string;
}

export interface QualityReport {
  overall_score: number;
  on_topic: boolean;
  on_topic_reason?: string | null;
  completeness: number;
  tone_match: boolean;
  code_present_where_required: boolean;
  issues: QualityIssue[];
  hallucinations: HallucinationFlag[];
  sections_to_redo: number[];
}

export interface PlanApprovalDecision {
  action: "approve" | "reject";
  plan?: Plan | null;
}

export type RunEventName =
  | "status"
  | "node_started"
  | "node_completed"
  | "section"
  | "warning"
  | "awaiting_input"
  | "done"
  | "error";

export interface EventEnvelope<
  TData extends Record<string, unknown> = Record<string, unknown>,
> {
  event: RunEventName;
  data: TData;
}
