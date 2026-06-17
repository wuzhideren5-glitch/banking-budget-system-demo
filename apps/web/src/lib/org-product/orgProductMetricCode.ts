export function normalizeOrgProductMetricCode(value: string | null | undefined): string {
  return String(value || "").trim().toUpperCase().replace(/\s+/g, "");
}

export function deriveRuntimeRefFromOrgProductMetricCode(
  entityCode: string | null | undefined,
  rawCode?: string | null
): string {
  const entity = normalizeOrgProductMetricCode(entityCode);
  const code = normalizeOrgProductMetricCode(rawCode);
  if (!entity || !code) return "";
  const dottedPattern = /^[A-Z][A-Z0-9]*\.\d{2}(?:\.\d{2})*(?:\.\d{3})?$/;
  if (dottedPattern.test(code) && code.split(".", 1)[0] === entity) return code;
  if (!code.startsWith(entity)) return "";
  const rest = code.slice(entity.length);
  if (!rest || !/^\d+$/.test(rest)) return "";
  let parts: string[];
  if (rest.length % 2 === 0) {
    parts = rest.match(/.{1,2}/g) ?? [];
  } else if (rest.length >= 3 && (rest.length - 3) % 2 === 0) {
    const prefix = rest.slice(0, -3);
    parts = [...(prefix.match(/.{1,2}/g) ?? []), rest.slice(-3)];
  } else {
    return "";
  }
  const ref = `${entity}.${parts.join(".")}`;
  return dottedPattern.test(ref) ? ref : "";
}

