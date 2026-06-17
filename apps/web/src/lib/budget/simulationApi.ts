import { apiPost, apiPostBlob } from "@/lib/shared/api";

export type SimulationBaselineRequestItemDto = {
  indicator_code: string;
  product_code?: string | null;
};

export type SimulationBaselineRowDto = {
  indicator_code: string;
  indicator_name: string;
  product_code: string | null;
  product_name: string | null;
  value_type: string;
  baseline_value: number;
  source_data_acct_codes?: string[];
  source_metric_codes?: string[];
  source_org_product_refs?: string[];
};

export type SimulationInputItemDto = {
  indicator_code: string;
  product_code?: string | null;
  simulate_value: number;
};

export type SimulationResultRowDto = {
  metric_group: string;
  indicator_code: string;
  indicator_name: string;
  value_type: string;
  baseline_2025: number;
  baseline_2026: number;
  simulation_2026: number;
};

export async function fetchSimulationBaseline(
  items: SimulationBaselineRequestItemDto[],
): Promise<SimulationBaselineRowDto[]> {
  return apiPost<SimulationBaselineRowDto[]>("/api/budget-simulation/baseline", items);
}

export async function fetchSimulationResult(items: SimulationInputItemDto[]): Promise<SimulationResultRowDto[]> {
  return apiPost<SimulationResultRowDto[]>("/api/budget-simulation/result", items);
}

export async function exportSimulationExcel(
  items: SimulationInputItemDto[],
): Promise<{ blob: Blob; filename: string | null }> {
  return apiPostBlob("/api/budget-simulation/export", items);
}
