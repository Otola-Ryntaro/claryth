// API contracts mirrored from the FastAPI response models.
export type InteractionStatus =
  | "contraindicated"
  | "caution"
  | "not_listed"
  | "unresolved"
  | "unsupported"
  | "system_error";

export interface Candidate {
  drug_id: string;
  display_name: string;
  generic_name: string | null;
  category: "prescription" | "otc" | "ingredient";
  score: number;
}

export interface ResolutionItem {
  input_name: string;
  normalized_input: string;
  status: "resolved" | "unresolved" | "unsupported";
  selected: Candidate | null;
  candidates: Candidate[];
  llm_used: boolean;
  message: string | null;
}

export interface IngredientResult {
  drug_id: string;
  generic_name: string;
  status: InteractionStatus;
  effect: string | null;
  mechanism: string | null;
  action: string | null;
  evidence_url: string | null;
  source_url: string | null;
  source_section: string | null;
  source_revision: string | null;
}

export interface CheckResult {
  input_name: string;
  drug_id: string;
  display_name: string;
  generic_name: string | null;
  category: "prescription" | "otc" | "ingredient";
  ingredients: string[];
  status: InteractionStatus;
  effect: string;
  mechanism: string;
  action: string;
  evidence_url: string | null;
  source_url: string | null;
  source_section: string | null;
  source_revision: string | null;
  dataset_updated_at: string;
  ingredient_results: IngredientResult[];
  target_id: string;
  target_name: string;
}

export interface TargetDrug {
  id: string;
  rank: number;
  label: string;
  group_label: string;
  is_default: boolean;
}
