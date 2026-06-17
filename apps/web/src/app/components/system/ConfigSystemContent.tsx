import { useEffect, useMemo, useRef, useState } from "react";
import {
  createSystemDatabase,
  createSystemVersion,
  deleteSystemDatabase,
  deleteSystemVersion,
  getCompareSummarySyncLatest,
  getEditShowVersionState,
  listSystemDatabases,
  listSystemDatabaseVersions,
  listSystemPeriodYears,
  renameSystemVersion,
  saveEditShowVersionState,
  syncSystemDatabases,
  type EditShowVersionStateDto,
  type CompareSyncLatestStatusDto,
  type SystemDatabaseRowDto,
  type SystemVersionRowDto,
} from "@/lib/system/systemApi";

type TabId = "database" | "version" | "edit_show";

export function ConfigSystemContent() {
  const [activeTab, setActiveTab] = useState<TabId>("database");
  const [databases, setDatabases] = useState<SystemDatabaseRowDto[]>([]);
  const [loadingDb, setLoadingDb] = useState(false);
  const [selectedDbId, setSelectedDbId] = useState<number | null>(null);
  const [versions, setVersions] = useState<SystemVersionRowDto[]>([]);
  const [versionsCache, setVersionsCache] = useState<Record<number, SystemVersionRowDto[]>>({});
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [periodYears, setPeriodYears] = useState<number[]>([]);
  const [newDbYear, setNewDbYear] = useState<number | "">("");
  const [newDbVersionName, setNewDbVersionName] = useState("");
  const [creatingDb, setCreatingDb] = useState(false);
  const [deletingDb, setDeletingDb] = useState(false);
  const [newVersionName, setNewVersionName] = useState("");
  const [newVersionParentId, setNewVersionParentId] = useState<number | "">("");
  const [newVersionCurrentMonth, setNewVersionCurrentMonth] = useState<number>(1);
  const [creatingVersion, setCreatingVersion] = useState(false);
  const [deleteVersionId, setDeleteVersionId] = useState<number | "">("");
  const [deletingVersion, setDeletingVersion] = useState(false);
  const [versionNameDrafts, setVersionNameDrafts] = useState<Record<string, string>>({});
  const [savingVersionNameId, setSavingVersionNameId] = useState<number | null>(null);
  const [editState, setEditState] = useState<EditShowVersionStateDto>({ edit: null, shows: [] });
  const [savingEditShow, setSavingEditShow] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [compareSyncLatest, setCompareSyncLatest] = useState<CompareSyncLatestStatusDto | null>(null);
  const lastSavedEditShowSnapshotRef = useRef<string>("");
  const prevTabRef = useRef<TabId>("database");
  const versionsFetchSeqRef = useRef(0);
  const tabOptions: Array<{ id: TabId; label: string; description: string }> = [
    {
      id: "database",
      label: "数据库文件维护",
      description: "管理年度数据库文件，支持扫描同步、新增与删除。",
    },
    {
      id: "version",
      label: "数据库版本管理",
      description: "管理选中数据库的版本，支持继承与当前月份设置。",
    },
    {
      id: "edit_show",
      label: "编辑与展示版本设置",
      description: "设置当前可编辑版本，以及最多5层对比展示版本。",
    },
  ];

  const versionDraftKey = (dbId: number | null, versionId: number) =>
    `${dbId ?? 0}:${versionId}`;

  const fetchDatabases = async (syncFirst = false) => {
    setLoadingDb(true);
    setLoadError(null);
    try {
      const rows = syncFirst ? await syncSystemDatabases() : await listSystemDatabases();
      setDatabases(rows);
      if (!selectedDbId || !rows.some((r) => r.id === selectedDbId)) {
        setSelectedDbId(rows[0]?.id ?? null);
      }
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载数据库清单失败");
    } finally {
      setLoadingDb(false);
    }
  };

  const fetchVersions = async (dbId: number | null) => {
    const seq = ++versionsFetchSeqRef.current;
    if (!dbId) {
      setVersions([]);
      setLoadingVersions(false);
      return;
    }
    setLoadingVersions(true);
    try {
      const rows = await listSystemDatabaseVersions(dbId);
      if (versionsFetchSeqRef.current !== seq) return;
      setVersions(rows);
      setVersionsCache((prev) => ({ ...prev, [dbId]: rows }));
    } catch (e) {
      if (versionsFetchSeqRef.current !== seq) return;
      setLoadError(e instanceof Error ? e.message : "加载版本列表失败");
      setVersions([]);
    } finally {
      if (versionsFetchSeqRef.current !== seq) return;
      setLoadingVersions(false);
    }
  };

  const ensureVersionsLoaded = async (dbId: number | null) => {
    if (!dbId) return;
    if (versionsCache[dbId]) return;
    try {
      const rows = await listSystemDatabaseVersions(dbId);
      setVersionsCache((prev) => ({ ...prev, [dbId]: rows }));
      if (selectedDbId === dbId) setVersions(rows);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载版本列表失败");
    }
  };

  const fetchPeriodYears = async () => {
    try {
      const rows = await listSystemPeriodYears();
      const years = rows.map((r) => Number(r.year)).filter((y) => Number.isFinite(y));
      setPeriodYears(years);
      if (!newDbYear && years.length > 0) setNewDbYear(years[0]);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载年份失败");
    }
  };

  const fetchEditShow = async () => {
    try {
      const state = await getEditShowVersionState();
      setEditState(state);
      const normalizedShows = (state.shows ?? [])
        .filter((s) => s.data_file_id && s.version_id)
        .sort((a, b) => a.level - b.level)
        .map((s) => ({ level: s.level, data_file_id: s.data_file_id, version_id: s.version_id }));
      const normalizedEdit =
        state.edit && state.edit.data_file_id && state.edit.version_id
          ? { data_file_id: state.edit.data_file_id, version_id: state.edit.version_id }
          : null;
      lastSavedEditShowSnapshotRef.current = JSON.stringify({
        edit: normalizedEdit,
        shows: normalizedShows,
      });
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载编辑/展示配置失败");
    }
  };

  const fetchCompareSyncLatest = async () => {
    try {
      const row = await getCompareSummarySyncLatest();
      setCompareSyncLatest(row);
    } catch {
      setCompareSyncLatest(null);
    }
  };

  useEffect(() => {
    void fetchDatabases();
    void fetchEditShow();
    void fetchPeriodYears();
    void fetchCompareSyncLatest();
  }, []);

  useEffect(() => {
    // 切换数据库后，重置和“版本”绑定的临时选择，避免沿用旧库的版本ID。
    setVersions([]);
    setLoadingVersions(!!selectedDbId);
    setNewVersionParentId("");
    setDeleteVersionId("");
    setSavingVersionNameId(null);
    void fetchVersions(selectedDbId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDbId]);

  useEffect(() => {
    setVersionNameDrafts((prev) => {
      const next = { ...prev };
      const prefix = `${selectedDbId ?? 0}:`;
      for (const v of versions) {
        const key = versionDraftKey(selectedDbId, v.version_id);
        if (next[key] === undefined) next[key] = v.version_name;
      }
      Object.keys(next).forEach((k) => {
        if (!k.startsWith(prefix)) return;
        const rawVersionId = Number(k.slice(prefix.length));
        if (!versions.some((vv) => vv.version_id === rawVersionId)) delete next[k];
      });
      return next;
    });
  }, [versions, selectedDbId]);

  useEffect(() => {
    const ids = new Set<number>();
    if (editState.edit?.data_file_id) ids.add(editState.edit.data_file_id);
    editState.shows.forEach((s) => {
      if (s.data_file_id) ids.add(s.data_file_id);
    });
    ids.forEach((id) => {
      void ensureVersionsLoaded(id);
    });
  }, [editState, versionsCache]);

  const versionsByDb = useMemo(() => {
    const map = new Map<number, SystemVersionRowDto[]>();
    Object.entries(versionsCache).forEach(([k, v]) => map.set(Number(k), v));
    if (selectedDbId) map.set(selectedDbId, versions);
    return map;
  }, [versionsCache, selectedDbId, versions]);

  const getVersionOptions = (dbId: number | null): SystemVersionRowDto[] => {
    if (!dbId) return [];
    return versionsByDb.get(dbId) ?? [];
  };

  const getVersionById = (dbId: number | null, versionId: number | null) => {
    if (!dbId || !versionId) return null;
    return getVersionOptions(dbId).find((v) => v.version_id === versionId) ?? null;
  };

  const formatDateTime = (raw: string) => raw.replace("T", " ").replace("Z", "");

  /** 与 version.current_month 口径一致，纯中文说明（供展示版本各行展示） */
  const formatMonthRuleChinese = (currentMonth: number) => {
    if (currentMonth === 13) {
      return "当前月份口径为13：全年可编辑实际数字，预算数字不可录入。";
    }
    if (currentMonth <= 1) {
      return "当前月份是1月，此前无可编辑实际数字，1月及以后可编辑预算数字。";
    }
    if (currentMonth >= 2 && currentMonth <= 12) {
      return `当前月份是${currentMonth}月，所以${currentMonth}月前可编辑实际数字，${currentMonth}月及以后可编辑预算数字。`;
    }
    return `当前月份为 ${currentMonth}，请与系统管理员核对口径。`;
  };

  const setEditSelection = (key: "data_file_id" | "version_id", value: number | null) => {
    const current = editState.edit ?? { data_file_id: 0, version_id: 0 };
    const next =
      key === "data_file_id"
        ? { data_file_id: value ?? 0, version_id: 0 }
        : { ...current, version_id: value ?? 0 };
    if (key === "data_file_id") {
      void ensureVersionsLoaded(next.data_file_id || null);
    }
    setEditState({
      ...editState,
      edit: next.data_file_id || next.version_id ? next : null,
    });
  };

  const showRows = useMemo(() => {
    const byLevel = new Map(editState.shows.map((s) => [s.level, s]));
    return [1, 2, 3, 4, 5].map((level) => byLevel.get(level) ?? null);
  }, [editState.shows]);
  const activeTabMeta = tabOptions.find((t) => t.id === activeTab) ?? tabOptions[0];

  const setShowSelection = (level: number, key: "data_file_id" | "version_id", value: number | null) => {
    const byLevel = new Map(editState.shows.map((s) => [s.level, { ...s }]));
    const existing = byLevel.get(level) ?? { level, data_file_id: 0, version_id: 0 };
    const next =
      key === "data_file_id"
        ? { ...existing, data_file_id: value ?? 0, version_id: 0 }
        : { ...existing, version_id: value ?? 0 };
    if (key === "data_file_id") {
      void ensureVersionsLoaded(next.data_file_id || null);
    }
    if (next.data_file_id || next.version_id) {
      byLevel.set(level, next);
    } else {
      byLevel.delete(level);
    }

    // 级联规则：若上一级为空，下一级全部清空
    for (let i = 2; i <= 5; i += 1) {
      if (!byLevel.get(i - 1)) byLevel.delete(i);
    }

    const normalized = Array.from(byLevel.values()).sort((a, b) => a.level - b.level);
    setEditState({ ...editState, shows: normalized });
  };

  const buildEditShowPayload = (): EditShowVersionStateDto => {
    return {
      edit: editState.edit && editState.edit.data_file_id && editState.edit.version_id ? editState.edit : null,
      shows: editState.shows.filter((s) => s.data_file_id && s.version_id).sort((a, b) => a.level - b.level),
    };
  };

  const validateEditShowSelection = (): string | null => {
    const editDb = Number(editState.edit?.data_file_id ?? 0);
    const editVersion = Number(editState.edit?.version_id ?? 0);
    if ((editDb > 0 && editVersion <= 0) || (editDb <= 0 && editVersion > 0)) {
      return "当前可编辑版本：选择数据库后必须同时选择版本。";
    }
    for (const row of editState.shows) {
      const dbId = Number(row.data_file_id ?? 0);
      const versionId = Number(row.version_id ?? 0);
      if ((dbId > 0 && versionId <= 0) || (dbId <= 0 && versionId > 0)) {
        return `展示版本层级 ${row.level}：选择数据库后必须同时选择版本。`;
      }
    }
    return null;
  };

  const snapshotEditShowPayload = (payload: EditShowVersionStateDto): string => {
    const normalizedShows = (payload.shows ?? []).map((s) => ({
      level: s.level,
      data_file_id: s.data_file_id,
      version_id: s.version_id,
    }));
    const normalizedEdit =
      payload.edit && payload.edit.data_file_id && payload.edit.version_id
        ? { data_file_id: payload.edit.data_file_id, version_id: payload.edit.version_id }
        : null;
    return JSON.stringify({ edit: normalizedEdit, shows: normalizedShows });
  };

  const persistEditShow = async (silent = false) => {
    if (savingEditShow) return false;
    const validationError = validateEditShowSelection();
    if (validationError) {
      setLoadError(validationError);
      if (!silent) {
        alert(validationError);
      }
      return false;
    }
    setSavingEditShow(true);
    setLoadError(null);
    try {
      const payload = buildEditShowPayload();
      const saved = await saveEditShowVersionState(payload);
      setEditState(saved);
      lastSavedEditShowSnapshotRef.current = snapshotEditShowPayload(saved);
      window.dispatchEvent(new CustomEvent("budget-version-snapshot-changed"));
      await fetchCompareSyncLatest();
      if (!silent) {
        alert("编辑版本与展示版本已保存。对比透视与聚合结果请在“预算事实刷新跑批”中生成。");
      }
      return true;
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "保存失败");
      if (!silent) {
        alert(e instanceof Error ? e.message : "保存失败");
      }
      return false;
    } finally {
      setSavingEditShow(false);
    }
  };

  const saveEditShow = async () => {
    await persistEditShow(false);
  };

  useEffect(() => {
    const previous = prevTabRef.current;
    prevTabRef.current = activeTab;
    if (previous !== "edit_show" || activeTab === "edit_show") return;
    void (async () => {
      if (savingEditShow) return;
      const payload = buildEditShowPayload();
      const currentSnapshot = snapshotEditShowPayload(payload);
      if (currentSnapshot !== lastSavedEditShowSnapshotRef.current) {
        await persistEditShow(true);
      }
      window.dispatchEvent(new CustomEvent("budget-version-snapshot-changed"));
      await fetchCompareSyncLatest();
    })().catch(() => {
      // 静默失败：用户已经离开当前页签，避免打断操作流。
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const createDatabase = async () => {
    if (!newDbYear || !newDbVersionName.trim()) {
      alert("请先选择年度并填写首版本名称");
      return;
    }
    setCreatingDb(true);
    try {
      await createSystemDatabase(Number(newDbYear), newDbVersionName.trim());
      await fetchDatabases(true);
      await fetchPeriodYears();
      setNewDbVersionName("");
      alert(`已创建 budget_${newDbYear}.db`);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "创建数据库失败");
    } finally {
      setCreatingDb(false);
    }
  };

  const deleteDatabase = async () => {
    if (!selectedDbId) {
      alert("请先选择要删除的数据库");
      return;
    }
    const selectedDb = databases.find((d) => d.id === selectedDbId);
    if (!selectedDb) return;
    if (!confirm(`确认删除数据库文件 ${selectedDb.data_file_name} 吗？该操作不可恢复。`)) return;
    if (
      !confirm(
        `再次确认：即将删除 ${selectedDb.data_file_name}\n文件路径：${selectedDb.file_path}\n建议先备份该文件后再删除。`,
      )
    ) return;
    setDeletingDb(true);
    try {
      await deleteSystemDatabase(selectedDbId);
      await fetchDatabases(true);
      await fetchEditShow();
      alert(`已删除 ${selectedDb.data_file_name}`);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "删除数据库失败");
    } finally {
      setDeletingDb(false);
    }
  };

  const createVersion = async () => {
    if (!selectedDbId) {
      alert("请先选择数据库");
      return;
    }
    if (!newVersionName.trim()) {
      alert("请输入新版本名称");
      return;
    }
    if (!Number.isInteger(newVersionCurrentMonth) || newVersionCurrentMonth < 1 || newVersionCurrentMonth > 13) {
      alert("当前月份必须是 1-13 的整数");
      return;
    }
    setCreatingVersion(true);
    try {
      await createSystemVersion(selectedDbId, {
        version_name: newVersionName.trim(),
        parent_version_id: newVersionParentId ? Number(newVersionParentId) : null,
        current_month: newVersionCurrentMonth,
      });
      await fetchVersions(selectedDbId);
      setNewVersionName("");
      setNewVersionParentId("");
      setNewVersionCurrentMonth(1);
      alert("版本创建成功");
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "创建版本失败");
    } finally {
      setCreatingVersion(false);
    }
  };

  const saveVersionName = async (v: SystemVersionRowDto) => {
    if (!selectedDbId) return;
    const draftKey = versionDraftKey(selectedDbId, v.version_id);
    const draft = (versionNameDrafts[draftKey] ?? v.version_name).trim();
    if (!draft) {
      alert("版本名称不能为空");
      setVersionNameDrafts((prev) => ({ ...prev, [draftKey]: v.version_name }));
      return;
    }
    if (draft === v.version_name) return;
    setSavingVersionNameId(v.version_id);
    setLoadError(null);
    try {
      const row = await renameSystemVersion(selectedDbId, v.version_id, draft);
      setVersionNameDrafts((prev) => ({
        ...prev,
        [versionDraftKey(selectedDbId, row.version_id)]: row.version_name,
      }));
      await fetchVersions(selectedDbId);
      window.dispatchEvent(new CustomEvent("budget-version-snapshot-changed"));
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "保存版本名称失败");
    } finally {
      setSavingVersionNameId(null);
    }
  };

  const deleteVersion = async () => {
    if (!selectedDbId) {
      alert("请先选择数据库");
      return;
    }
    const versionId = Number(deleteVersionId);
    if (!versionId || !Number.isInteger(versionId) || versionId <= 0) {
      alert("请选择要删除的版本ID");
      return;
    }
    if (!confirm(`确认删除版本 ${versionId} 吗？该版本的预算数据与汇总数据将一并删除。`)) return;
    setDeletingVersion(true);
    try {
      await deleteSystemVersion(selectedDbId, versionId);
      await fetchVersions(selectedDbId);
      await fetchEditShow();
      setDeleteVersionId("");
      alert("版本删除成功");
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "删除版本失败");
    } finally {
      setDeletingVersion(false);
    }
  };

  return (
    <div className="bb-page overflow-auto">
      <h3 className="bb-page-title">系统设定控制</h3>
      <div className="bb-tabs">
        <div role="tablist" aria-label="系统设定功能标签页" className="flex items-end gap-1">
          {tabOptions.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 text-xs border rounded-t-md transition-colors ${
                  isActive
                    ? "bg-white text-blue-700 border-gray-300 border-b-white font-medium"
                    : "bg-gray-100 text-gray-700 border-gray-300 hover:bg-gray-200"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>
      <p className="bb-page-subtitle">{activeTabMeta.description}</p>

      {loadError && <div className="bb-status-banner bb-status-banner-danger">{loadError}</div>}

      {activeTab === "database" && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => void fetchDatabases(true)}
              className="bb-btn bb-btn-warning"
            >
              扫描并同步 data 目录
            </button>
            {loadingDb && <span className="text-xs text-[var(--bb-text-muted)]">正在同步数据库清单...</span>}
          </div>
          <div className="bb-panel p-3">
            <div className="bb-panel-title mb-2">新建年度库</div>
            <div className="flex items-center gap-2 flex-wrap">
              <label className="text-xs text-[var(--bb-text)]">年度</label>
              <select
                value={newDbYear}
                onChange={(e) => setNewDbYear(e.target.value ? Number(e.target.value) : "")}
                className="bb-select"
              >
                <option value="">选择年度</option>
                {periodYears.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
              <label className="text-xs text-[var(--bb-text)]">首版本名称</label>
              <input
                value={newDbVersionName}
                onChange={(e) => setNewDbVersionName(e.target.value)}
                placeholder="例如：V2026.01.01"
                className="bb-input w-52"
              />
              <button
                onClick={() => void createDatabase()}
                className="bb-btn bb-btn-primary ml-auto"
                disabled={creatingDb}
              >
                {creatingDb ? "创建中..." : "新增年度库"}
              </button>
              <button
                onClick={() => void deleteDatabase()}
                className="bb-btn bb-btn-danger"
                disabled={!selectedDbId || deletingDb}
              >
                {deletingDb ? "删除中..." : "删除选中库"}
              </button>
            </div>
          </div>
          <table className="bb-table bb-table-dense">
            <thead >
              <tr>
                <th >ID</th>
                <th >文件名</th>
                <th >年份</th>
                <th >创建时间</th>
                <th >文件路径</th>
              </tr>
            </thead>
            <tbody>
              {databases.map((db) => (
                <tr
                  key={db.id}
                  onClick={() => setSelectedDbId(db.id)}
                  className={`cursor-pointer ${selectedDbId === db.id ? "bg-blue-50" : ""}`}
                >
                  <td >{db.id}</td>
                  <td >{db.data_file_name}</td>
                  <td >{db.year}</td>
                  <td >{formatDateTime(db.create_time)}</td>
                  <td >{db.file_path}</td>
                </tr>
              ))}
              {!databases.length && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-[var(--bb-text-muted)]">
                    暂无数据库记录
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === "version" && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <label className="text-xs text-[var(--bb-text)]">选择数据库：</label>
            <select
              value={selectedDbId ?? ""}
              onChange={(e) => setSelectedDbId(e.target.value ? Number(e.target.value) : null)}
              className="bb-select"
            >
              <option value="">请选择</option>
              {databases.map((db) => (
                <option key={db.id} value={db.id}>
                  {db.data_file_name}（{db.year}）
                </option>
              ))}
            </select>
            {loadingVersions && <span className="text-xs text-[var(--bb-text-muted)]">正在加载版本...</span>}
          </div>
          <div className="bb-panel p-3">
            <div className="bb-panel-title mb-2">新建版本</div>
            <div className="flex items-center gap-2 flex-wrap">
              <label className="text-xs text-[var(--bb-text)]">版本名称</label>
              <input
                value={newVersionName}
                onChange={(e) => setNewVersionName(e.target.value)}
                placeholder="输入版本名称"
                className="bb-input w-52"
                disabled={!selectedDbId}
              />
              <label className="text-xs text-[var(--bb-text)]">继承父版本</label>
              <select
                value={newVersionParentId}
                onChange={(e) => setNewVersionParentId(e.target.value ? Number(e.target.value) : "")}
                className="bb-select"
                disabled={!selectedDbId}
              >
                <option value="">全新版本（不继承）</option>
                {versions.map((v) => (
                  <option key={v.version_id} value={v.version_id}>
                    {v.version_id} - {v.version_name}
                  </option>
                ))}
              </select>
              <label className="text-xs text-[var(--bb-text)]">当前月份</label>
              <select
                value={newVersionCurrentMonth}
                onChange={(e) => setNewVersionCurrentMonth(Number(e.target.value))}
                className="bb-select"
                disabled={!selectedDbId}
              >
                {Array.from({ length: 13 }, (_, i) => i + 1).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <span className="text-xs text-red-600">当前月份选定后不得更改</span>
              <button
                onClick={() => void createVersion()}
                className="bb-btn bb-btn-primary ml-auto"
                disabled={!selectedDbId || creatingVersion}
              >
                {creatingVersion ? "创建中..." : "新增版本"}
              </button>
            </div>
            <p className="text-[11px] text-[var(--bb-text-muted)] mt-2">
              当前月份规则：预算允许录入 {`current_month..12`}，实际允许录入 {`1..current_month-1`}；13 表示预算全禁用、全年实际。
            </p>
          </div>
          <div className="bb-panel p-3">
            <div className="bb-panel-title mb-2">删除版本</div>
            <div className="flex items-center gap-2 flex-wrap">
              <label className="text-xs text-[var(--bb-text)]">版本ID</label>
              <select
                value={deleteVersionId}
                onChange={(e) => setDeleteVersionId(e.target.value ? Number(e.target.value) : "")}
                className="bb-select"
                disabled={!selectedDbId}
              >
                <option value="">请选择版本</option>
                {versions.map((v) => (
                  <option key={v.version_id} value={v.version_id}>
                    {v.version_id} - {v.version_name}
                  </option>
                ))}
              </select>
              <button
                onClick={() => void deleteVersion()}
                className="bb-btn bb-btn-danger ml-auto"
                disabled={!selectedDbId || deletingVersion}
              >
                {deletingVersion ? "删除中..." : "删除版本"}
              </button>
            </div>
          </div>
          <table className="bb-table bb-table-dense">
            <thead >
              <tr>
                <th >版本ID</th>
                <th className="min-w-[12rem]">版本名称（可编辑）</th>
                <th >创建时间</th>
                <th >当前月份</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.version_id}>
                  <td >{v.version_id}</td>
                  <td >
                    <div className="flex items-center gap-1">
                      <input
                        type="text"
                        className="bb-grid-input flex-1 min-w-0 max-w-[18rem]"
                        value={versionNameDrafts[versionDraftKey(selectedDbId, v.version_id)] ?? v.version_name}
                        onChange={(e) =>
                          setVersionNameDrafts((prev) => ({
                            ...prev,
                            [versionDraftKey(selectedDbId, v.version_id)]: e.target.value,
                          }))
                        }
                        onBlur={() => void saveVersionName(v)}
                        disabled={savingVersionNameId === v.version_id}
                        title="修改后失焦保存；版本 ID、创建时间、当前月份不可在此修改"
                      />
                      {savingVersionNameId === v.version_id && (
                        <span className="text-[10px] text-gray-500 whitespace-nowrap">保存中…</span>
                      )}
                    </div>
                  </td>
                  <td >{formatDateTime(v.version_date_time)}</td>
                  <td >{v.current_month}</td>
                </tr>
              ))}
              {!versions.length && (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-[var(--bb-text-muted)]">
                    未选择数据库或该库暂无版本
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === "edit_show" && (
        <div className="space-y-4">
          <div className="bb-panel p-3">
            <div className="bb-panel-title mb-2">当前可编辑版本（唯一）</div>
            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-700 whitespace-nowrap">选择预算年度</span>
                <select
                  value={editState.edit?.data_file_id ?? ""}
                  onChange={(e) => setEditSelection("data_file_id", e.target.value ? Number(e.target.value) : null)}
                  className="bb-select min-w-[14rem]"
                >
                  <option value="">选择数据库</option>
                  {databases.map((db) => (
                    <option key={db.id} value={db.id}>
                      {db.data_file_name}（{db.year}）
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-700 whitespace-nowrap">选择预算版本</span>
                <select
                  value={editState.edit?.version_id ?? ""}
                  onChange={(e) => setEditSelection("version_id", e.target.value ? Number(e.target.value) : null)}
                  className="bb-select min-w-[16rem]"
                  disabled={!editState.edit?.data_file_id}
                >
                  <option value="">选择版本</option>
                  {getVersionOptions(editState.edit?.data_file_id ?? null).map((v) => (
                    <option key={v.version_id} value={v.version_id}>
                      {v.version_id} - {v.version_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="bb-panel p-3">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="text-xs font-medium text-gray-800">展示版本（最多5层，需按顺序选择）</div>
              <div className="text-[11px] text-[var(--bb-text-muted)]">
                {compareSyncLatest?.job_id ? (
                  <>
                    最近跑批同步：{(compareSyncLatest.status ?? "unknown").toUpperCase()}{" "}
                    {formatDateTime(compareSyncLatest.end_time ?? compareSyncLatest.start_time ?? "")}
                  </>
                ) : (
                  "最近跑批同步：暂无记录"
                )}
              </div>
            </div>
            <div className="space-y-2">
              {showRows.map((row, idx) => {
                const level = idx + 1;
                const prevRow = showRows[idx - 1];
                const prevSelected =
                  level === 1 || (!!prevRow?.data_file_id && !!prevRow?.version_id);
                return (
                  <div key={level} className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-gray-700 w-16">层级 {level}</span>
                    <select
                      value={row?.data_file_id ?? ""}
                      onChange={(e) => setShowSelection(level, "data_file_id", e.target.value ? Number(e.target.value) : null)}
                      className="bb-select"
                      disabled={!prevSelected}
                    >
                      <option value="">选择数据库</option>
                      {databases.map((db) => (
                        <option key={db.id} value={db.id}>
                          {db.data_file_name}（{db.year}）
                        </option>
                      ))}
                    </select>
                    <select
                      value={row?.version_id ?? ""}
                      onChange={(e) => setShowSelection(level, "version_id", e.target.value ? Number(e.target.value) : null)}
                      className="bb-select"
                      disabled={!prevSelected || !row?.data_file_id}
                    >
                      <option value="">选择版本</option>
                      {getVersionOptions(row?.data_file_id ?? null).map((v) => (
                        <option key={v.version_id} value={v.version_id}>
                          {v.version_id} - {v.version_name}
                        </option>
                      ))}
                    </select>
                    {row?.data_file_id && row?.version_id && (
                      <span className="text-[11px] text-blue-700">
                        {(() => {
                          const v = getVersionById(row.data_file_id, row.version_id);
                          return v
                            ? formatMonthRuleChinese(v.current_month)
                            : "版本信息加载中...";
                        })()}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
            <p className="text-[11px] text-[var(--bb-text-muted)] mt-2">
              提示：保存后 compare 同步会按每个层级所选版本的 current_month 口径取数（month&lt;current_month 取实际，month&gt;=current_month 取预算）。
            </p>
          </div>

          <button
            onClick={() => void saveEditShow()}
            disabled={savingEditShow}
            className="bb-btn bb-btn-primary"
          >
            {savingEditShow ? "保存中..." : "保存并同步数据"}
          </button>
        </div>
      )}
    </div>
  );
}
