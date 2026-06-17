/** 默认空字符串：开发态走 Vite proxy（`/api` -> 127.0.0.1:8009）；生产若前后端不同源请设 `VITE_API_BASE` */
const viteEnv = (import.meta as ImportMeta & { env?: { VITE_API_BASE?: string } }).env;
const base = viteEnv?.VITE_API_BASE?.replace(/\/$/, "") ?? "";

export function buildApiUrl(path: string): string {
  return `${base}${path}`;
}

export async function readErrorMessage(r: Response): Promise<string> {
  const fallback = r.statusText || `HTTP ${r.status}`;
  const text = await r.text();
  if (!text) return fallback;
  try {
    const json = JSON.parse(text) as { detail?: unknown };
    if (typeof json.detail === "string") return json.detail;
    if (json.detail !== undefined) return JSON.stringify(json.detail);
  } catch {
    // non-JSON error payload, keep raw text
  }
  return text;
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(buildApiUrl(path), { credentials: "include" });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  return r.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  return r.json() as Promise<T>;
}

export async function apiPostBlob(path: string, body: unknown): Promise<{ blob: Blob; filename: string | null }> {
  const r = await fetch(buildApiUrl(path), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  return { blob: await r.blob(), filename: readDownloadFilename(r, "") || null };
}

export async function apiGetBlob(path: string, fallbackName: string): Promise<{ blob: Blob; filename: string }> {
  const r = await fetch(buildApiUrl(path), { credentials: "include" });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  return { blob: await r.blob(), filename: readDownloadFilename(r, fallbackName) };
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  return r.json() as Promise<T>;
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  return r.json() as Promise<T>;
}

export async function apiPostForm<T>(path: string, formData: FormData): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  return r.json() as Promise<T>;
}

export async function apiDelete(path: string): Promise<void> {
  const r = await fetch(buildApiUrl(path), { method: "DELETE", credentials: "include" });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
}

export function readDownloadFilename(response: Response, fallbackName: string): string {
  const disposition = response.headers.get("Content-Disposition") || "";
  const encodedMatch = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  const quotedMatch = /filename=\"?([^\";]+)\"?/i.exec(disposition);
  return encodedMatch?.[1] ? decodeURIComponent(encodedMatch[1]) : quotedMatch?.[1] ?? fallbackName;
}

export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const { blob, filename } = await apiGetBlob(path, fallbackName);
  downloadBlob(blob, filename);
}
