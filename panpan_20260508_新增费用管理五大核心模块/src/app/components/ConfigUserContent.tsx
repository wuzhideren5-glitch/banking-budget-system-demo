import { useEffect, useState } from "react";
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  type SystemUserRowDto,
} from "@/lib/api";

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
      const rows = await apiGet<SystemUserRowDto[]>("/api/system/users");
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
      await apiPost<SystemUserRowDto>("/api/system/users", {
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
      await apiPatch<SystemUserRowDto>(`/api/system/users/${user.id}`, {
        user_name: nextName.trim(),
      });
      await loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "修改用户名失败");
    }
  };

  const changePermission = async (user: SystemUserRowDto, permission: number) => {
    if (permission === user.permission_type) return;
    try {
      await apiPatch<SystemUserRowDto>(`/api/system/users/${user.id}`, {
        permission_type: permission,
      });
      await loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "更新权限失败");
    }
  };

  const resetFirstPassword = async (user: SystemUserRowDto) => {
    const pwd = prompt(`请输入 ${user.user_name} 的新首次登录密码（至少8位，至少包含1个字母，区分大小写）`);
    if (!pwd) return;
    try {
      await apiPatch<SystemUserRowDto>(`/api/system/users/${user.id}/reset-first-password`, {
        first_login_password: pwd,
      });
      await loadUsers();
      alert("首次登录密码已重置");
    } catch (e) {
      setError(e instanceof Error ? e.message : "重置首次密码失败");
    }
  };

  const setFirstLoginFlag = async (user: SystemUserRowDto, flag: number) => {
    if (flag === user.first_login_flag) return;
    try {
      await apiPatch<SystemUserRowDto>(`/api/system/users/${user.id}/first-login-flag`, {
        first_login_flag: flag,
      });
      await loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "修改首次登录标记失败");
    }
  };

  const deleteUser = async (user: SystemUserRowDto) => {
    if (!confirm(`确认删除用户 ${user.user_name} 吗？`)) return;
    try {
      await apiDelete(`/api/system/users/${user.id}`);
      await loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除用户失败");
    }
  };

  return (
    <div className="p-4 h-full overflow-auto">
      <h3 className="text-sm font-medium text-gray-800 mb-3">用户和权限管理</h3>

      <div className="border border-gray-300 rounded p-3 mb-4">
        <div className="text-xs font-medium text-gray-800 mb-2">新增用户</div>
        <div className="flex items-center gap-2 flex-wrap">
          <input
            value={newUserName}
            onChange={(e) => setNewUserName(e.target.value)}
            placeholder="用户名（不可重复）"
            className="border border-gray-300 rounded px-2 py-1 text-xs w-48"
          />
          <input
            value={newUserFirstPwd}
            onChange={(e) => setNewUserFirstPwd(e.target.value)}
            placeholder="首次登录密码"
            className="border border-gray-300 rounded px-2 py-1 text-xs w-52"
          />
          <select
            value={newUserPermission}
            onChange={(e) => setNewUserPermission(Number(e.target.value))}
            className="border border-gray-300 rounded px-2 py-1 text-xs"
          >
            <option value={1}>全权管理员</option>
            <option value={2}>数据录入用户</option>
            <option value={3}>数据浏览用户</option>
          </select>
          <button
            onClick={() => void createUser()}
            disabled={creating}
            className="px-3 py-1.5 text-xs rounded bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-60"
          >
            {creating ? "创建中..." : "新增用户"}
          </button>
          <button
            onClick={() => void loadUsers()}
            disabled={loading}
            className="px-3 py-1.5 text-xs rounded bg-gray-100 text-gray-700 hover:bg-gray-200 border border-gray-300"
          >
            刷新
          </button>
        </div>
        <p className="text-[11px] text-gray-500 mt-2">
          密码规则：至少8位，至少包含1个字母，且区分大小写。
        </p>
      </div>

      {error && <div className="mb-3 text-xs text-red-600">{error}</div>}

      <table className="w-full text-xs border-collapse">
        <thead className="bg-gray-100">
          <tr>
            <th className="border border-gray-300 px-2 py-1 text-left">ID</th>
            <th className="border border-gray-300 px-2 py-1 text-left">用户名</th>
            <th className="border border-gray-300 px-2 py-1 text-left">用户类型</th>
            <th className="border border-gray-300 px-2 py-1 text-left">首次登录标记</th>
            <th className="border border-gray-300 px-2 py-1 text-left">创建时间</th>
            <th className="border border-gray-300 px-2 py-1 text-left">操作</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td className="border border-gray-300 px-2 py-1">{u.id}</td>
              <td className="border border-gray-300 px-2 py-1">{u.user_name}</td>
              <td className="border border-gray-300 px-2 py-1">
                <select
                  value={u.permission_type}
                  onChange={(e) => void changePermission(u, Number(e.target.value))}
                  className="border border-gray-300 rounded px-1 py-0.5 text-xs"
                >
                  <option value={1}>全权管理员</option>
                  <option value={2}>数据录入用户</option>
                  <option value={3}>数据浏览用户</option>
                </select>
                <span className="ml-2 text-gray-500">{permissionName(u.permission_type)}</span>
              </td>
              <td className="border border-gray-300 px-2 py-1">
                <select
                  value={u.first_login_flag}
                  onChange={(e) => void setFirstLoginFlag(u, Number(e.target.value))}
                  className="border border-gray-300 rounded px-1 py-0.5 text-xs"
                >
                  <option value={1}>1（首次）</option>
                  <option value={0}>0（非首次）</option>
                </select>
              </td>
              <td className="border border-gray-300 px-2 py-1">{u.create_time}</td>
              <td className="border border-gray-300 px-2 py-1">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <button
                    onClick={() => void renameUser(u)}
                    className="px-2 py-1 rounded bg-gray-100 border border-gray-300 hover:bg-gray-200"
                  >
                    改名
                  </button>
                  <button
                    onClick={() => void resetFirstPassword(u)}
                    className="px-2 py-1 rounded bg-orange-100 border border-orange-300 hover:bg-orange-200"
                  >
                    重置首次密码
                  </button>
                  <button
                    onClick={() => void deleteUser(u)}
                    className="px-2 py-1 rounded bg-red-100 border border-red-300 hover:bg-red-200 text-red-700"
                  >
                    删除
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {!users.length && (
            <tr>
              <td colSpan={6} className="border border-gray-300 px-2 py-3 text-center text-gray-500">
                暂无用户
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
