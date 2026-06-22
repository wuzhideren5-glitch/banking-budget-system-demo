/**
 * 月内公式引用规范（与 OrgProduct_RollingForecast_Calculation_PDD §4.2 一致）
 * - 同表：科目代码（如 A01.01）
 * - 跨表（同机构）：表名/科目代码（如 损益表/A01.01）
 * - 跨机构：机构代码/表名/科目代码（如 A01/损益表/A01.01）
 */

export type ParsedFormulaRef =
  | { kind: "local"; raw: string; metricCodeRaw: string; metricCodeNormalized: string }
  | { kind: "cross_table"; raw: string; tableName: string; metricCodeRaw: string; metricCodeNormalized: string }
  | { kind: "cross_entity"; raw: string; entityCode: string; tableName: string; metricCodeRaw: string; metricCodeNormalized: string };

export function normalizeFormulaRefText(input: string): string {
  return String(input || "")
    .trim()
    .toUpperCase()
    .replace(/\u200b/g, "")
    .replace(/\s+/g, "")
    .replace(/（/g, "(")
    .replace(/）/g, ")")
    .replace(/\./g, "");
}

/** 展示态「代码+名称」连写时，避免名称首字母被正则吃进代码段。 */
function glueMetricCodeAndName(displayCode: string, name: string): string {
  const code = String(displayCode || "");
  const metricName = String(name || "");
  if (!code || !metricName) return `${code}${metricName}`;
  if (/[A-Za-z0-9]$/.test(code) && /^[A-Za-z0-9]/.test(metricName)) {
    return `${code}\u200b${metricName}`;
  }
  return `${code}${metricName}`;
}

/** 用已知科目代码集合纠正展示态连写导致的尾部粘连（如 AA90010301IT → AA90010301）。 */
export function snapNormalizedMetricCode(normalized: string, knownCodes: Set<string> | null | undefined): string {
  const token = String(normalized || "").trim();
  if (!token || !knownCodes || knownCodes.size === 0) return token;
  if (knownCodes.has(token)) return token;
  let best = "";
  knownCodes.forEach((code) => {
    if (token.startsWith(code) && code.length > best.length) {
      best = code;
    }
  });
  return best && token.length > best.length ? best : token;
}

export function knownCodesForFormulaRef(
  ref: ParsedFormulaRef,
  opts: {
    currentEntityId: string;
    currentTableName: string;
    entityIdByCode: Map<string, string>;
    knownCodesByEntityTableKey: Map<string, Set<string>>;
  }
): Set<string> | null {
  if (ref.kind === "local") {
    return opts.knownCodesByEntityTableKey.get(`${opts.currentEntityId}::${opts.currentTableName}`) ?? null;
  }
  if (ref.kind === "cross_table") {
    return opts.knownCodesByEntityTableKey.get(`${opts.currentEntityId}::${ref.tableName}`) ?? null;
  }
  const entityId = opts.entityIdByCode.get(ref.entityCode) ?? "";
  if (!entityId) return null;
  return opts.knownCodesByEntityTableKey.get(`${entityId}::${ref.tableName}`) ?? null;
}

export function resolvedMetricCodeNormalized(
  ref: ParsedFormulaRef,
  opts: {
    currentEntityId: string;
    currentTableName: string;
    entityIdByCode: Map<string, string>;
    knownCodesByEntityTableKey: Map<string, Set<string>>;
  }
): string {
  const knownCodes = knownCodesForFormulaRef(ref, opts);
  return snapNormalizedMetricCode(ref.metricCodeNormalized, knownCodes);
}

// 与 formatMetricCodeForDisplay 一致：机构前缀 + 每段 2 位数字/字母，避免把指标名称吃进末段（如 .01+IT → .01IT）
const METRIC_CODE_TOKEN_RE = String.raw`[A-Za-z][A-Za-z0-9]*(?:\.[0-9A-Z]{2})+`;
const CROSS_ENTITY_REF_RE = new RegExp(
  `([A-Za-z0-9]{1,6})[\\/|]([^\\/|\\s()+\\-*.,]+)[\\/|](${METRIC_CODE_TOKEN_RE})`,
  "g"
);
const CROSS_TABLE_REF_RE = new RegExp(`([^\\/|\\s()+\\-*.,]+?表)[\\/|](${METRIC_CODE_TOKEN_RE})`, "g");
const LOCAL_CODE_RE = new RegExp(String.raw`\b${METRIC_CODE_TOKEN_RE}\b`, "g");

export function parseFormulaRefs(formula: string): ParsedFormulaRef[] {
  const text = String(formula || "");
  const out: ParsedFormulaRef[] = [];
  const seen = new Set<string>();
  let scrubbed = text;

  for (const m of text.matchAll(CROSS_ENTITY_REF_RE)) {
    const raw = m[0];
    const entityCode = String(m[1] || "").trim().toUpperCase();
    const tableName = String(m[2] || "").trim();
    const metricCodeRaw = String(m[3] || "").trim().toUpperCase();
    const metricCodeNormalized = normalizeFormulaRefText(metricCodeRaw);
    const key = `entity:${entityCode}|${tableName}|${metricCodeNormalized}`;
    if (!seen.has(key)) {
      seen.add(key);
      out.push({ kind: "cross_entity", raw, entityCode, tableName, metricCodeRaw, metricCodeNormalized });
    }
    scrubbed = scrubbed.split(raw).join(" ");
  }

  for (const m of scrubbed.matchAll(CROSS_TABLE_REF_RE)) {
    const raw = m[0];
    const tableName = String(m[1] || "").trim();
    const metricCodeRaw = String(m[2] || "").trim().toUpperCase();
    const metricCodeNormalized = normalizeFormulaRefText(metricCodeRaw);
    const key = `table:${tableName}|${metricCodeNormalized}`;
    if (!seen.has(key)) {
      seen.add(key);
      out.push({ kind: "cross_table", raw, tableName, metricCodeRaw, metricCodeNormalized });
    }
    scrubbed = scrubbed.split(raw).join(" ");
  }

  for (const m of scrubbed.matchAll(LOCAL_CODE_RE)) {
    const metricCodeRaw = String(m[0] || "").trim().toUpperCase();
    const metricCodeNormalized = normalizeFormulaRefText(metricCodeRaw);
    if (!metricCodeNormalized) continue;
    const key = `local:${metricCodeNormalized}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ kind: "local", raw: metricCodeRaw, metricCodeRaw, metricCodeNormalized });
  }
  return out;
}

export type FormulaRefInfo = { displayCode: string; name: string };

export function buildFormulaInsertText(
  activeEntityCode: string,
  currentTableName: string,
  sourceEntityCode: string,
  sourceEntityName: string,
  sourceTableName: string,
  sourceMetricDisplayCode: string,
  sourceMetricName: string
): string {
  const srcCode = String(sourceEntityCode || "").trim().toUpperCase();
  const activeCode = String(activeEntityCode || "").trim().toUpperCase();
  const srcTable = String(sourceTableName || "").trim();
  const curTable = String(currentTableName || "").trim();
  const displayCode = String(sourceMetricDisplayCode || "").trim();
  const name = String(sourceMetricName || "").trim();
  const entityName = String(sourceEntityName || "").trim();

  if (srcCode === activeCode && srcTable === curTable) {
    return `${entityName}${glueMetricCodeAndName(displayCode, name)}`;
  }
  if (srcCode === activeCode) {
    return `${srcTable}/${displayCode}`;
  }
  return `${srcCode}/${srcTable}/${displayCode}`;
}

export function decorateFormulaTextForDisplay(
  formula: string,
  baseEntityId: string,
  baseTableName: string,
  entityIdByCode: Map<string, string>,
  metricRefInfoByEntityTableKey: Map<string, Map<string, FormulaRefInfo>>,
  getEntityName: (entityId: string, fallbackCode: string) => string
): string {
  const raw = String(formula || "");
  if (!raw.trim()) return "";

  const tableNameTrimmed = String(baseTableName || "").trim();
  const localPrefix = getEntityName(baseEntityId, "");
  const localInfoMap = metricRefInfoByEntityTableKey.get(`${baseEntityId}::${tableNameTrimmed}`) ?? null;

  let out = raw;
  const placeholders: Array<{ placeholder: string; replacement: string }> = [];

  parseFormulaRefs(raw).forEach((ref, idx) => {
    if (ref.kind === "cross_entity") {
      const placeholder = `__EREF_${idx}__`;
      const entityId = entityIdByCode.get(ref.entityCode) ?? "";
      const entityName = getEntityName(entityId, ref.entityCode);
      const infoMap = entityId ? metricRefInfoByEntityTableKey.get(`${entityId}::${ref.tableName}`) ?? null : null;
      const normalized = snapNormalizedMetricCode(ref.metricCodeNormalized, infoMap ? new Set(infoMap.keys()) : null);
      const info = infoMap?.get(normalized) ?? null;
      const replacement = info?.name ? `${entityName}${glueMetricCodeAndName(info.displayCode, info.name)}` : ref.raw;
      placeholders.push({ placeholder, replacement });
      out = out.split(ref.raw).join(placeholder);
      return;
    }
    if (ref.kind === "cross_table") {
      const placeholder = `__TREF_${idx}__`;
      const infoMap = metricRefInfoByEntityTableKey.get(`${baseEntityId}::${ref.tableName}`) ?? null;
      const normalized = snapNormalizedMetricCode(ref.metricCodeNormalized, infoMap ? new Set(infoMap.keys()) : null);
      const info = infoMap?.get(normalized) ?? null;
      const replacement = info?.name ? `${localPrefix}${glueMetricCodeAndName(info.displayCode, info.name)}` : ref.raw;
      placeholders.push({ placeholder, replacement });
      out = out.split(ref.raw).join(placeholder);
    }
  });

  const hanRe = /[\p{Script=Han}]/u;
  if (localInfoMap && localPrefix) {
    out = out.replace(LOCAL_CODE_RE, (m, offset, full) => {
      const before = offset > 0 ? String(full[offset - 1] || "") : "";
      const after = offset + m.length < String(full).length ? String(full[offset + m.length] || "") : "";
      if ((before && hanRe.test(before)) || (after && hanRe.test(after))) return m;
      const normalized = snapNormalizedMetricCode(normalizeFormulaRefText(m), new Set(localInfoMap.keys()));
      const info = localInfoMap.get(normalized) ?? null;
      if (!info?.name) return m;
      return `${localPrefix}${glueMetricCodeAndName(info.displayCode, info.name)}`;
    });
  }

  placeholders.forEach(({ placeholder, replacement }) => {
    out = out.split(placeholder).join(replacement);
  });
  return out;
}

export function canonicalizeFormulaForStorage(
  displayText: string,
  activeEntityId: string,
  activeEntityCode: string,
  activeEntityName: string,
  currentTableName: string,
  metricRefInfoByEntityTableKey: Map<string, Map<string, FormulaRefInfo>>,
  entityIdByCode: Map<string, string>,
  getEntityName: (entityId: string) => string
): string {
  let out = String(displayText || "").replace(/\u200b/g, "");
  if (!out.trim()) return "";

  const prefix = String(activeEntityName || "").trim();
  const activeCode = String(activeEntityCode || "").trim().toUpperCase();
  const curTable = String(currentTableName || "").trim();

  const sameTableKey = `${activeEntityId}::${curTable}`;
  const sameTableMap = metricRefInfoByEntityTableKey.get(sameTableKey) ?? null;
  if (sameTableMap && prefix) {
    sameTableMap.forEach((info) => {
      const displayCode = String(info.displayCode || "").trim();
      const name = String(info.name || "").trim();
      if (!displayCode || !name) return;
      const decorated = `${prefix}${glueMetricCodeAndName(displayCode, name)}`;
      if (out.includes(decorated)) out = out.split(decorated).join(displayCode);
      const decoratedWithoutPrefix = glueMetricCodeAndName(displayCode, name);
      if (out.includes(decoratedWithoutPrefix)) out = out.split(decoratedWithoutPrefix).join(displayCode);
    });
  }

  metricRefInfoByEntityTableKey.forEach((infoMap, tableKey) => {
    const [entityId, tableName] = tableKey.split("::");
    if (entityId !== activeEntityId || tableName === curTable) return;
    infoMap.forEach((info) => {
      const displayCode = String(info.displayCode || "").trim();
      const name = String(info.name || "").trim();
      if (!displayCode || !name || !prefix) return;
      const decorated = `${prefix}${glueMetricCodeAndName(displayCode, name)}`;
      if (out.includes(decorated)) {
        out = out.split(decorated).join(`${tableName}/${displayCode}`);
      }
    });
  });

  // 将同机构误写的三段位改为两段位：AA/损益表/code → 损益表/code
  parseFormulaRefs(out).forEach((ref) => {
    if (ref.kind !== "cross_entity") return;
    if (ref.entityCode !== activeCode) return;
    if (ref.tableName === curTable) return;
    const twoPart = `${ref.tableName}/${ref.metricCodeRaw}`;
    if (out.includes(ref.raw)) out = out.split(ref.raw).join(twoPart);
  });

  // 跨机构：机构名+代码+名称 → 机构/表/代码
  entityIdByCode.forEach((entityId, entityCode) => {
    if (entityId === activeEntityId) return;
    const entityName = String(getEntityName(entityId) || "").trim();
    metricRefInfoByEntityTableKey.forEach((infoMap, tableKey) => {
      if (!tableKey.startsWith(`${entityId}::`)) return;
      const tableName = tableKey.slice(entityId.length + 2);
      infoMap.forEach((info) => {
        const displayCode = String(info.displayCode || "").trim();
        const name = String(info.name || "").trim();
        if (!displayCode || !name) return;
        const canonical = `${entityCode}/${tableName}/${displayCode}`;
        if (entityName) {
          const decoratedFull = `${entityName}${glueMetricCodeAndName(displayCode, name)}`;
          if (out.includes(decoratedFull)) out = out.split(decoratedFull).join(canonical);
        }
        const decorated = glueMetricCodeAndName(displayCode, name);
        if (out.includes(decorated)) out = out.split(decorated).join(canonical);
      });
    });
  });

  return out;
}

export function validateFormulaText(
  formula: string,
  opts: {
    currentKnownCodes: Set<string>;
    selfCodeNormalized: string;
    entityIdByCode: Map<string, string>;
    knownCodesByEntityTableKey: Map<string, Set<string>>;
    currentEntityId: string;
    currentEntityCode: string;
    currentTableName: string;
  }
): string | null {
  const text = String(formula || "");
  if (!text.trim()) return null;
  if (/[^\p{L}\p{N}+\-*/^%(),.\/|<>=!:"'\s]/u.test(text)) {
    return "公式包含不支持的字符。仅支持数字/字母/中文、点、空格、加减乘除、括号、逗号、比较符，以及引用分隔符 / 或 |。";
  }
  let balance = 0;
  for (const ch of text) {
    if (ch === "(") balance += 1;
    if (ch === ")") balance -= 1;
    if (balance < 0) return "括号不匹配：右括号数量多于左括号。";
  }
  if (balance !== 0) return "括号不匹配：请检查左括号与右括号数量。";

  const refs = parseFormulaRefs(text);
  const refResolveOpts = {
    currentEntityId: opts.currentEntityId,
    currentTableName: opts.currentTableName,
    entityIdByCode: opts.entityIdByCode,
    knownCodesByEntityTableKey: opts.knownCodesByEntityTableKey,
  };
  const missing: string[] = [];
  let hasSelf = false;
  for (const ref of refs) {
    const metricCodeNormalized = resolvedMetricCodeNormalized(ref, refResolveOpts);
    if (ref.kind === "local") {
      if (opts.selfCodeNormalized && metricCodeNormalized === opts.selfCodeNormalized) hasSelf = true;
      if (!opts.currentKnownCodes.has(metricCodeNormalized)) missing.push(ref.metricCodeRaw);
      continue;
    }
    if (ref.kind === "cross_table") {
      const tableKey = `${opts.currentEntityId}::${ref.tableName}`;
      const codeSet = opts.knownCodesByEntityTableKey.get(tableKey);
      const isSelf =
        String(ref.tableName).trim() === String(opts.currentTableName).trim() &&
        opts.selfCodeNormalized &&
        metricCodeNormalized === opts.selfCodeNormalized;
      if (isSelf) hasSelf = true;
      if (!codeSet || !codeSet.has(metricCodeNormalized)) missing.push(`${ref.tableName}/${ref.metricCodeRaw}`);
      continue;
    }
    const entityId = opts.entityIdByCode.get(ref.entityCode);
    if (!entityId) {
      missing.push(`${ref.entityCode}/${ref.tableName}/${ref.metricCodeRaw}`);
      continue;
    }
    const tableKey = `${entityId}::${ref.tableName}`;
    const codeSet = opts.knownCodesByEntityTableKey.get(tableKey);
    const isSelf =
      entityId === opts.currentEntityId &&
      String(ref.tableName).trim() === String(opts.currentTableName).trim() &&
      opts.selfCodeNormalized &&
      metricCodeNormalized === opts.selfCodeNormalized;
    if (isSelf) hasSelf = true;
    if (!codeSet || !codeSet.has(metricCodeNormalized)) {
      missing.push(`${ref.entityCode}/${ref.tableName}/${ref.metricCodeRaw}`);
    }
  }
  if (hasSelf) return "公式不允许引用自身（会形成循环依赖）。";
  if (missing.length > 0) {
    const unique = [...new Set(missing)];
    const shown = unique.slice(0, 6);
    const suffix = unique.length > shown.length ? ` 等${unique.length}项` : "";
    return `公式引用缺失：${shown.join("、")}${suffix}`;
  }
  return null;
}

/** 将公式引用解析为依赖的 entityId + 表名 + 指标 id（用于循环依赖检测） */
export function resolveFormulaRefDependency(
  ref: ParsedFormulaRef,
  fromEntityId: string,
  fromTableName: string,
  entityIdByCode: Map<string, string>,
  codeToMetricIdByEntityTableKey: Map<string, Map<string, string>>
): { entityId: string; tableName: string; metricId: string } | null {
  const snapFromTableKey = (tableKey: string, normalized: string): string => {
    const codeMap = codeToMetricIdByEntityTableKey.get(tableKey);
    return snapNormalizedMetricCode(normalized, codeMap ? new Set(codeMap.keys()) : null);
  };
  if (ref.kind === "local") {
    const tableKey = `${fromEntityId}::${fromTableName}`;
    const metricCodeNormalized = snapFromTableKey(tableKey, ref.metricCodeNormalized);
    const depId = codeToMetricIdByEntityTableKey.get(tableKey)?.get(metricCodeNormalized);
    if (!depId) return null;
    return { entityId: fromEntityId, tableName: fromTableName, metricId: depId };
  }
  if (ref.kind === "cross_table") {
    const tableKey = `${fromEntityId}::${ref.tableName}`;
    const metricCodeNormalized = snapFromTableKey(tableKey, ref.metricCodeNormalized);
    const depId = codeToMetricIdByEntityTableKey.get(tableKey)?.get(metricCodeNormalized);
    if (!depId) return null;
    return { entityId: fromEntityId, tableName: ref.tableName, metricId: depId };
  }
  const depEntityId = entityIdByCode.get(ref.entityCode);
  if (!depEntityId) return null;
  const depTableName = String(ref.tableName || "").trim();
  const tableKey = `${depEntityId}::${depTableName}`;
  const metricCodeNormalized = snapFromTableKey(tableKey, ref.metricCodeNormalized);
  const depId = codeToMetricIdByEntityTableKey.get(tableKey)?.get(metricCodeNormalized);
  if (!depId) return null;
  return { entityId: depEntityId, tableName: depTableName, metricId: depId };
}

export const FORMULA_REF_FORMAT_HINT =
  "引用格式：同表写科目代码；同机构跨表写「表名/代码」如 损益表/A01.01；跨机构写「机构/表名/代码」如 A01/损益表/A01.01。";

export const AI_FORMULA_RULES_HINT = `规则识别（未接入大模型）支持：
· 按指标名称：目标名 = 来源名1 + 来源名2（同一张表内按名称匹配）
· 当前选中指标：直接写表达式或「等于…一级科目贷款利息收入…的和」
· 跨产品汇总：三级产品一级代码相加等于 AA 某一级代码（见帮助示例）
优先记名称即可；系统会解析为规范引用。复杂自然语言建议手写公式或后续接入大模型。`;
