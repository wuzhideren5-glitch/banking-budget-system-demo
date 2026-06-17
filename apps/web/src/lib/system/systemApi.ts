import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "@/lib/shared/api";

export type SessionInfo = {
  user_id: number;
  software_version: string;
  budget_year: number;
  version_id: number;
  version_name: string;
  version_date_time: string;
  user_display_name: string;
  user_role: string;
  permission_type: number;
  first_login_required: boolean;
  db_connected: boolean;
  last_global_calc_refresh_time: string | null;
};

export type GlobalRefreshAnnualStatusDto = {
  data_file_name: string;
  year: number;
  refresh_time_a: string | null;
};

export type GlobalRefreshStatusDto = {
  annual_items: GlobalRefreshAnnualStatusDto[];
  compare_refresh_time_b: string | null;
  next_planned_refresh_time_c: string | null;
};

export type VersionSnapshotItemDto = {
  label: string;
  budget_year: number;
  version_id: number;
  version_name: string;
  current_month?: number;
};

export type VersionSnapshotResponseDto = {
  items: VersionSnapshotItemDto[];
};

export type LoginRequestDto = {
  user_name: string;
  password: string;
};

export type LoginResponseDto = {
  ok: boolean;
  need_change_password: boolean;
  user_name: string;
  permission_type: number;
};

export type SystemDatabaseRowDto = {
  id: number;
  data_file_name: string;
  year: number;
  create_time: string;
  file_path: string;
};

export type SystemVersionRowDto = {
  version_id: number;
  version_name: string;
  version_date_time: string;
  current_month: number;
};

export type EditVersionSelectionDto = {
  data_file_id: number;
  version_id: number;
};

export type EditShowVersionSelectionDto = {
  level: number;
  data_file_id: number;
  version_id: number;
};

export type EditShowVersionStateDto = {
  edit: EditVersionSelectionDto | null;
  shows: EditShowVersionSelectionDto[];
};

export type SystemUserRowDto = {
  id: number;
  user_name: string;
  permission_type: number;
  first_login_flag: number;
  create_time: string;
  update_time: string | null;
};

export type CompareSyncLatestStatusDto = {
  job_id: number | null;
  start_time: string | null;
  end_time: string | null;
  trigger_source: string | null;
  status: string | null;
  message: string | null;
};

export function getSession(): Promise<SessionInfo> {
  return apiGet<SessionInfo>("/api/session");
}

export function getVersionSnapshot(): Promise<VersionSnapshotResponseDto> {
  return apiGet<VersionSnapshotResponseDto>("/api/version-snapshot");
}

export function login(payload: LoginRequestDto): Promise<LoginResponseDto> {
  return apiPost<LoginResponseDto>("/api/login", payload);
}

export function changeFirstLoginPassword(newPassword: string): Promise<unknown> {
  return apiPost("/api/change-password-first-login", { new_password: newPassword });
}

export function logout(): Promise<unknown> {
  return apiPost("/api/logout", {});
}

export function getGlobalRefreshStatus(): Promise<GlobalRefreshStatusDto> {
  return apiGet<GlobalRefreshStatusDto>("/api/global-refresh-status");
}

export function listSystemDatabases(): Promise<SystemDatabaseRowDto[]> {
  return apiGet<SystemDatabaseRowDto[]>("/api/system/databases");
}

export function syncSystemDatabases(): Promise<SystemDatabaseRowDto[]> {
  return apiPost<SystemDatabaseRowDto[]>("/api/system/databases/sync", {});
}

export function listSystemDatabaseVersions(dbId: number): Promise<SystemVersionRowDto[]> {
  return apiGet<SystemVersionRowDto[]>(`/api/system/databases/${dbId}/versions`);
}

export function listSystemPeriodYears(): Promise<Array<{ year: number }>> {
  return apiGet<Array<{ year: number }>>("/api/system/period-years");
}

export function getEditShowVersionState(): Promise<EditShowVersionStateDto> {
  return apiGet<EditShowVersionStateDto>("/api/system/edit-show-version");
}

export function saveEditShowVersionState(payload: EditShowVersionStateDto): Promise<EditShowVersionStateDto> {
  return apiPut<EditShowVersionStateDto>("/api/system/edit-show-version", payload);
}

export function getCompareSummarySyncLatest(): Promise<CompareSyncLatestStatusDto> {
  return apiGet<CompareSyncLatestStatusDto>("/api/compare-summary/sync/latest");
}

export function createSystemDatabase(year: number, firstVersionName: string): Promise<SystemDatabaseRowDto> {
  return apiPost<SystemDatabaseRowDto>("/api/system/databases", {
    year,
    first_version_name: firstVersionName,
  });
}

export function deleteSystemDatabase(dbId: number): Promise<void> {
  return apiDelete(`/api/system/databases/${dbId}`);
}

export function createSystemVersion(
  dbId: number,
  payload: { version_name: string; parent_version_id: number | null; current_month: number },
): Promise<SystemVersionRowDto> {
  return apiPost<SystemVersionRowDto>(`/api/system/databases/${dbId}/versions`, payload);
}

export function renameSystemVersion(dbId: number, versionId: number, versionName: string): Promise<SystemVersionRowDto> {
  return apiPatch<SystemVersionRowDto>(`/api/system/databases/${dbId}/versions/${versionId}`, {
    version_name: versionName,
  });
}

export function deleteSystemVersion(dbId: number, versionId: number): Promise<void> {
  return apiDelete(`/api/system/databases/${dbId}/versions/${versionId}`);
}

export function listSystemUsers(): Promise<SystemUserRowDto[]> {
  return apiGet<SystemUserRowDto[]>("/api/system/users");
}

export function createSystemUser(payload: {
  user_name: string;
  first_login_password: string;
  permission_type: number;
}): Promise<SystemUserRowDto> {
  return apiPost<SystemUserRowDto>("/api/system/users", payload);
}

export function renameSystemUser(userId: number, userName: string): Promise<SystemUserRowDto> {
  return apiPatch<SystemUserRowDto>(`/api/system/users/${userId}`, { user_name: userName });
}

export function changeSystemUserPermission(userId: number, permissionType: number): Promise<SystemUserRowDto> {
  return apiPatch<SystemUserRowDto>(`/api/system/users/${userId}`, { permission_type: permissionType });
}

export function resetSystemUserFirstPassword(userId: number, firstLoginPassword: string): Promise<SystemUserRowDto> {
  return apiPatch<SystemUserRowDto>(`/api/system/users/${userId}/reset-first-password`, {
    first_login_password: firstLoginPassword,
  });
}

export function setSystemUserFirstLoginFlag(userId: number, firstLoginFlag: number): Promise<SystemUserRowDto> {
  return apiPatch<SystemUserRowDto>(`/api/system/users/${userId}/first-login-flag`, {
    first_login_flag: firstLoginFlag,
  });
}

export function deleteSystemUser(userId: number): Promise<void> {
  return apiDelete(`/api/system/users/${userId}`);
}
