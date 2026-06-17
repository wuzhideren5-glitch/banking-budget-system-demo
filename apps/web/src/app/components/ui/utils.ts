export type ClassValue = string | number | false | null | undefined | ClassValue[] | Record<string, boolean | undefined | null>;

export function cn(...inputs: ClassValue[]) {
  const parts: string[] = [];
  const walk = (value: ClassValue) => {
    if (!value) return;
    if (typeof value === "string" || typeof value === "number") {
      parts.push(String(value));
      return;
    }
    if (Array.isArray(value)) {
      value.forEach(walk);
      return;
    }
    Object.entries(value).forEach(([key, enabled]) => {
      if (enabled) parts.push(key);
    });
  };
  inputs.forEach(walk);
  return parts.join(" ");
}
