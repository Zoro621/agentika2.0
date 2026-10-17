import type { components } from "./generated-api";
export type Provider = NonNullable<
  components["schemas"]["CaseCreate"]["provider"]
>;
export type ReviewStatus = components["schemas"]["ReviewInput"]["status"];

export type Anchor = {
  id: string;
  artifact_id?: string;
  execution_id?: string;
  path: string;
  text: string;
  line?: number;
  highlight_line?: number;
  page?: number;
  cell?: number;
  pointer?: string;
  kind?: string;
  bbox?: number[];
};
export type Artifact = {
  id: string;
  path: string;
  kind: string;
  size: number;
  sha256: string;
  warnings?: string[];
  parsed?: {
    text?: string;
    anchors?: Anchor[];
    profile?: unknown;
    code?: unknown;
    warnings?: string[];
    pages?: number;
  };
};
export type Claim = {
  id: string;
  artifact_id: string;
  quote: string;
  type: string;
  metric?: string;
  value?: number;
  reported?: string;
  anchor: Anchor;
  context?: Record<string, string>;
  origin: string;
};
export type Finding = {
  id: string;
  title: string;
  kind: string;
  evidence_status: string;
  impact: string;
  explanation: string;
  evidence: Anchor[];
  observed: Record<string, unknown>;
  alternatives: string[];
  limitations: string[];
  next_action: string;
  review_status: string;
  review_note: string;
};
export type Question = {
  id: string;
  title: string;
  why: string;
  evidence: Anchor[];
  options: { value: string; label: string; effect: string }[];
  answer?: string;
};
export type Check = {
  id: string;
  name: string;
  status: string;
  detail: string;
  claim_id?: string;
};
export type Run = {
  id: string;
  status: string;
  manifest: {
    variant: string;
    classification: string;
    runner: string;
    input_sha256: string;
    [key: string]: unknown;
  };
  output: {
    metrics?: Record<string, number>;
    entity_overlap?: number;
    train_rows?: number;
    test_rows?: number;
    seconds?: number;
    environment?: Record<string, string>;
    limitations?: string[];
    error?: string;
    [key: string]: unknown;
  };
  created_at: string;
};
export type GraphNode = {
  id: string;
  label: string;
  type: string;
  status?: string;
  artifact_id?: string;
  finding_id?: string;
  path?: string;
  members?: string[];
  count?: number;
};
export type Graph = {
  nodes: GraphNode[];
  edges: { source: string; target: string; type: string; count?: number }[];
};
export type CaseResult = {
  claims?: Claim[];
  findings?: Finding[];
  questions?: Question[];
  checks?: Check[];
  executions?: Run[];
  warnings?: string[];
  graph?: Graph;
  provider?: string;
  coverage?: Record<string, number>;
  history?: {
    revision: number;
    at: string;
    findings: Finding[];
    coverage: Record<string, number>;
  }[];
  agent_actions?: { tool: string; summary: string; result: unknown }[];
};
export type Case = {
  id: string;
  title: string;
  status: string;
  revision: number;
  provider: string;
  created_at: string;
  updated_at: string;
  sources: {
    type: string;
    url?: string;
    commit?: string;
    name?: string;
    label?: string;
  }[];
  artifacts: Artifact[];
  decisions: {
    question_id: string;
    answer: string;
    revision: number;
    at: string;
    rationale: string;
  }[];
  result: CaseResult;
  jobs: { id: string; state: string; checkpoint: string; error?: string }[];
};
export type Capabilities = {
  offline: boolean;
  openai: { configured: boolean; model: string };
  ollama: { available: boolean; models: string[]; model: string };
  runner: { available: boolean; provider: string; reason: string };
  storage: string;
  supported: string[];
  unsupported: string[];
};
export type Activity = {
  id: number;
  stage: string;
  type: string;
  message: string;
  created_at: string;
  payload: Record<string, unknown>;
};
export type Sample = {
  id: string;
  title: string;
  subtitle: string;
  tags: string[];
  description: string;
};
export type RecentCase = {
  id: string;
  title: string;
  status: string;
  created_at: string;
  findings: number;
};
export const activeStates = new Set([
  "queued",
  "inspecting",
  "extracting",
  "mapping",
  "checking",
  "investigating",
]);
export const humanize = (value: string) => value.replaceAll("_", " ");
