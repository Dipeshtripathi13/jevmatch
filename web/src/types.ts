export type RequirementKind = "must_have" | "skill" | "nice_to_have";

export interface Requirement {
  id: string;
  text: string;
  kind: RequirementKind;
  weight: number;
}

export interface HardConstraints {
  min_years_experience: number | null;
  required_degree: "associate" | "bachelor" | "master" | "doctorate" | null;
  location: string | null;
  remote: boolean | null;
}

export interface ExtractedRequirements {
  requirements: Requirement[];
  hard_constraints: HardConstraints;
}

export interface SavedResume {
  id: string;
  name: string;
  filename: string;
  size_bytes: number;
  created_at: string;
}

export interface InlineResume {
  name: string;
  text: string;
}

export interface RequirementResult {
  requirement: Requirement;
  value: number;
  normalized_score: number;
  confidence: number | null;
  evidence: string[];
  raw_answer: Record<string, unknown>;
}

export interface MatchResult {
  resume_id: string | null;
  resume_name: string;
  match_score: number;
  verdict:
    "strong_match" | "partial_match" | "weak_match" | "needs_human_review";
  requires_human_review: boolean;
  missing_must_haves: string[];
  gaps: Array<{ requirement_id: string; requirement: string; impact: number }>;
  requirement_results: RequirementResult[];
  hard_constraint_checks: Array<{
    constraint: string;
    required: string;
    observed: string | null;
    passed: boolean | null;
  }>;
  seniority: string | null;
  is_resume_probability: number;
  model_version: string;
  latency_ms: number;
}
