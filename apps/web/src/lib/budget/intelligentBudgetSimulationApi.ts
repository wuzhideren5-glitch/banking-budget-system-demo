import { apiGet, apiPost, apiPostBlob } from "@/lib/shared/api";

export type ParsedIntelligentBudgetTargetDto = {
  original_text: string;
  min_net_profit_growth: number;
  max_npl_ratio: number;
  hard_targets: Record<string, number>;
  soft_preferences: string[];
  adjustable_factors: string[];
  requires_confirmation: boolean;
  warnings: string[];
};

export type ProductContributionDto = {
  product_code: string;
  product_name: string;
  scale_growth: number;
  yield_bp: number;
  risk_action: string;
  expense_growth: number;
  marginal_contribution: number;
};

export type IntelligentBudgetSolutionDto = {
  solution_id: string;
  rank: number;
  name: string;
  math_score: number;
  net_profit_growth: number;
  npl_ratio: number;
  core_actions: Record<string, number | string>;
  factor_movements: Record<string, number>;
  top_product_contributions: ProductContributionDto[];
  other_product_contribution: number;
  explanation: string;
  display_role: "baseline" | "recommended" | "risk_first" | "profit_first" | "alternate";
  recommendation_reason: string;
  budget_snapshot: Record<string, number>;
  risk_bridge: Record<string, number>;
};

export type IntelligentBudgetTaskDto = {
  task_id: string;
  target_text: string;
  parsed_target: ParsedIntelligentBudgetTargetDto;
  status: "completed" | "negotiation_required";
  stage: string;
  step_summary: string;
  baseline_solution: IntelligentBudgetSolutionDto;
  solutions: IntelligentBudgetSolutionDto[];
  negotiation_message: string;
  negotiation_suggestions: string[];
};

export async function parseIntelligentBudgetTarget(
  targetText: string,
): Promise<ParsedIntelligentBudgetTargetDto> {
  return apiPost<ParsedIntelligentBudgetTargetDto>("/api/intelligent-budget-simulation/parse-target", {
    target_text: targetText,
  });
}

export async function createIntelligentBudgetTask(
  targetText: string,
  confirmed: boolean,
): Promise<IntelligentBudgetTaskDto> {
  return apiPost<IntelligentBudgetTaskDto>("/api/intelligent-budget-simulation/tasks", {
    target_text: targetText,
    confirmed,
  });
}

export async function fetchIntelligentBudgetTask(taskId: string): Promise<IntelligentBudgetTaskDto> {
  return apiGet<IntelligentBudgetTaskDto>(`/api/intelligent-budget-simulation/tasks/${encodeURIComponent(taskId)}`);
}

export async function exportIntelligentBudgetTask(taskId: string): Promise<{ blob: Blob; filename: string | null }> {
  return apiPostBlob("/api/intelligent-budget-simulation/export", { task_id: taskId });
}
