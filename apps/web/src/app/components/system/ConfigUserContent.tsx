import { useEffect, useState } from "react";
import {
  changeSystemUserPermission,
  createSystemUser,
  deleteSystemUser,
  listSystemUsers,
  renameSystemUser,
  resetSystemUserFirstPassword,
  setSystemUserFirstLoginFlag,
  type SystemUserRowDto,
} from "@/lib/system/systemApi";

const permissionName = (v: number) => {
  if (v === 1) return "全权管理员（1/2/3）";
  if (v === 2) return "数据录入用户（1/2）";
  if (v === 3) return "数据浏览用户（1）";
  return `未知(${v})`;
};

export function ConfigUserContent() {
  const [users, setUsers] = useState<SystemUserRowDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newUserName, setNewUserName] = useState("");
  const [newUserPermission, setNewUserPermission] = useState<number>(3);
  const [newUserFirstPwd, setNewUserFirstPwd] = useState("");
  const [creating, setCreating] = useState(false);

  const loadUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listSystemUsers();
      setUsers(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载用户失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadUsers();
  }, []);

  const createUser = async () => {
    if (!newUserName.trim() || !newUserFirstPwd.trim()) {
      alert("请填写用户名和首次登录密码");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      await createSystemUser({
        user_name: newUserName.trim(),
        first_login_password: newUserFirstPwd,
        permission_type: newUserPermission,
      });
      setNewUserName("");
      setNewUserFirstPwd("");
      setNewUserPermission(3);
      await loadUsers();
      alert("用户创建成功");
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建用户失败");
    } finally {
      setCreating(false);
    }
  };

  const renameUser = async (user: SystemUserRowDto) => {
    const nextName = prompt("请输入新用户名", user.user_name);
    if (!nextName || !nextName.trim() || nextName.trim() === user.user_name) return;
    try {
      await renameSystemUser(user.id, nextName.trim());
      await loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "修改用户名失败");
    }
  };

  const changePermission = async (user: SystemUserRowDto, permission: number) => {
    if (permission === user.permission_type) return;
    try {
      await changeSystemUserPermission(user.id, permission);
      await loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "更新权限失败");
    }
  };

  const resetFirstPassword = async (user: SystemUserRowDto) => {
    const pwd = prompt(`请输入 ${user.user_name} 的新首次登录密码（至少8位，至少包含1个字母，区分大小写）`);
    if (!pwd) return;
    try {
      await resetSystemUserFirstPassword(user.id, pwd);
      await loadUsers();
      alert("首次登录密码已重置");
    } catch (e) {
      setError(e instanceof Error ? e.message : "重置首次密码失败");
    }
  };

  const setFirstLoginFlag = async (user: SystemUserRowDto, flag: number) => {
    if (flag === user.first_login_flag) return;
    try {
      await setSystemUserFirstLoginFlag(user.id, flag);
      await loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "修改首次登录标记失败");
    }
  };

  const deleteUser = async (user: SystemUserRowDto) => {
    if (!confirm(`确认删除用户 ${user.user_name} 吗？`)) return;
    try {
      await deleteSystemUser(user.id);
      await loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除用户失败");
    }
  };

  return (
    <div className="bb-page overflow-auto">
      <div className="bb-page-header">
        <div>
          <h3 className="bb-page-title">用户和权限管理</h3>
          <p className="bb-page-subtitle">统一维护用户、权限类型和首次登录状态。</p>
        </div>
      </div>

      <div className="bb-panel p-3">
        <div className="bb-panel-title mb-2">新增用户</div>
        <div className="flex items-center gap-2 flex-wrap">
          <input
            value={newUserName}
            onChange={(e) => setNewUserName(e.target.value)}
            placeholder="用户名（不可重复）"
            className="bb-input w-48"
          />
          <input
            value={newUserFirstPwd}
            onChange={(e) => setNewUserFirstPwd(e.target.value)}
            placeholder="首次登录密码"
            className="bb-input w-52"
          />
          <select
            value={newUserPermission}
            onChange={(e) => setNewUserPermission(Number(e.target.value))}
            className="bb-select"
          >
            <option value={1}>全权管理员</option>
            <option value={2}>数据录入用户</option>
            <option value={3}>数据浏览用户</option>
          </select>
          <button
            onClick={() => void createUser()}
            disabled={creating}
            className="bb-btn bb-btn-primary"
          >
            {creating ? "创建中..." : "新增用户"}
          </button>
          <button
            onClick={() => void loadUsers()}
            disabled={loading}
            className="bb-btn bb-btn-secondary"
          >
            刷新
          </button>
        </div>
        <p className="text-[11px] text-[var(--bb-text-muted)] mt-2">
          密码规则：至少8位，至少包含1个字母，且区分大小写。
        </p>
      </div>

      {error && <div className="bb-status-banner bb-status-banner-danger">{error}</div>}

      <div className="bb-table-wrap">
      <table className="bb-table bb-table-dense">
        <thead>
          <tr>
            <th>ID</th>
            <th>用户名</th>
            <th>用户类型</th>
            <th>首次登录标记</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.id}</td>
              <td>{u.user_name}</td>
              <td>
                <select
                  value={u.permission_type}
                  onChange={(e) => void changePermission(u, Number(e.target.value))}
                  className="bb-select h-7"
                >
                  <option value={1}>全权管理员</option>
                  <option value={2}>数据录入用户</option>
                  <option value={3}>数据浏览用户</option>
                </select>
                <span className="ml-2 text-[var(--bb-text-muted)]">{permissionName(u.permission_type)}</span>
              </td>
              <td>
                <select
                  value={u.first_login_flag}
                  onChange={(e) => void setFirstLoginFlag(u, Number(e.target.value))}
                  className="bb-select h-7"
                >
                  <option value={1}>1（首次）</option>
                  <option value={0}>0（非首次）</option>
                </select>
              </td>
              <td>{u.create_time}</td>
              <td>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <button
                    onClick={() => void renameUser(u)}
                    className="bb-btn bb-btn-secondary"
                  >
                    改名
                  </button>
                  <button
                    onClick={() => void resetFirstPassword(u)}
                    className="bb-btn bb-btn-warning"
                  >
                    重置首次密码
                  </button>
                  <button
                    onClick={() => void deleteUser(u)}
                    className="bb-btn bb-btn-danger"
                  >
                    删除
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {!users.length && (
            <tr>
              <td colSpan={6} className="py-6 text-center text-[var(--bb-text-muted)]">
                暂无用户
              </td>
            </tr>
          )}
        </tbody>
      </table>
      </div>
    </div>
  );
}
