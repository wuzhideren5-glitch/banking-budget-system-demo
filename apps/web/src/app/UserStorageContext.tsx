import { createContext, useContext, useMemo, type ReactNode } from "react";

const UserStorageContext = createContext<number | null>(null);

/**
 * 将 localStorage 按登录用户隔离（同一浏览器下多账号切换互不覆盖）。
 * 主界面仅在已登录时挂载 Provider。
 */
export function UserStorageProvider({
  userId,
  children,
}: {
  userId: number;
  children: ReactNode;
}) {
  return <UserStorageContext.Provider value={userId}>{children}</UserStorageContext.Provider>;
}

export function useUserStorageId(): number | null {
  return useContext(UserStorageContext);
}

/** 稳定片段，如 u3；无上下文时为 anon */
export function useUserStorageKeyPrefix(): string {
  const id = useContext(UserStorageContext);
  return useMemo(() => {
    if (id == null || !Number.isFinite(id)) return "anon";
    return `u${id}`;
  }, [id]);
}
