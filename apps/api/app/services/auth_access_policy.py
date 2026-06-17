from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


@dataclass(frozen=True)
class AuthAccessDecision:
    allowed: bool
    status_code: int | None = None
    detail: str | None = None
    clear_session_cookie: bool = False
    requires_session_context: bool = False


def role_name_from_permission(permission_type: int) -> str:
    if permission_type == 1:
        return "全权管理员"
    if permission_type == 2:
        return "数据录入用户"
    return "数据浏览用户"


def permission_set(permission_type: int) -> set[int]:
    if permission_type == 1:
        return {1, 2, 3}
    if permission_type == 2:
        return {1, 2}
    return {1}


def auth_request_access(
    method: str,
    path: str,
    session_ctx: dict[str, Any] | None,
) -> AuthAccessDecision:
    if method.upper() == "OPTIONS":
        return AuthAccessDecision(allowed=True)
    if not path.startswith("/api"):
        return AuthAccessDecision(allowed=True)
    if path in {"/api/health", "/api/login"}:
        return AuthAccessDecision(allowed=True)
    if session_ctx is None:
        if path == "/api/session":
            return AuthAccessDecision(allowed=False, status_code=401, detail="未登录")
        return AuthAccessDecision(
            allowed=False,
            status_code=401,
            detail="未登录，请先登录",
            clear_session_cookie=True,
        )
    if int(session_ctx.get("must_change_password", 0)) == 1:
        if path not in {"/api/session", "/api/change-password-first-login", "/api/logout"}:
            return AuthAccessDecision(allowed=False, status_code=403, detail="首次登录请先修改密码")
        return AuthAccessDecision(allowed=True, requires_session_context=True)

    required_permission = path_required_permission(path, method)
    if required_permission is not None:
        allowed = permission_set(int(session_ctx["permission_type"]))
        if required_permission not in allowed:
            return AuthAccessDecision(allowed=False, status_code=403, detail="权限不足")
    return AuthAccessDecision(allowed=True, requires_session_context=True)


def path_required_permission(path: str, method: str) -> int | None:
    if path.startswith("/api/system"):
        return 3
    if path.startswith("/api/org-product-tree"):
        return 3 if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} else 1
    if path.startswith("/api/org-product-metrics"):
        return 3 if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} else 1
    if path.startswith("/api/org-product-data-entry"):
        return 2
    if path.startswith("/api/org-product-output"):
        return 2 if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} else 1
    if path.startswith("/api/budget-subject-catalog"):
        return 3
    if path.startswith("/api/dept-accounts"):
        return 3
    if path.startswith("/api/org-product-runtime-products"):
        return 3 if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} else 1
    if path.startswith("/api/budget-actual-batch"):
        return 2
    if path.startswith("/api/budget-simulation"):
        return 2
    if path.startswith("/api/expense-actual-import"):
        return 2
    if path.startswith("/api/expense-budget-entry"):
        return 2
    if path.startswith("/api/bi-ai-subject-mapping/reload"):
        return 3
    if path.startswith("/api/bi-ai-subject-mapping"):
        return 1
    if path.startswith("/api/expense-forecast"):
        return 2
    if path.startswith("/api/budget-summary") or path.startswith("/api/compare-summary"):
        return 1
    if path.startswith("/api/budget-output"):
        return 1
    if path.startswith("/api/expense-budget-execution/admin"):
        return 3
    if path.startswith("/api/expense-budget-execution"):
        return 1
    if path.startswith("/api/business-cost-income-ratio/admin"):
        return 3
    if path.startswith("/api/business-cost-income-ratio/import") or path.startswith(
        "/api/business-cost-income-ratio/template"
    ):
        return 2
    if path.startswith("/api/business-cost-income-ratio/input"):
        return 2
    if path.startswith("/api/business-cost-income-ratio"):
        return 1
    if path.startswith("/api/input-output-topic-overview"):
        return 1
    if path == "/api/global-refresh-status":
        return 1
    if path.startswith("/api/chart"):
        return 1
    if path.startswith("/api/agent"):
        return 1
    if path.startswith("/api/smart-reports/blueprints") and method.upper() in {
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    }:
        return 3
    if path.startswith("/api/smart-reports/templates") and method.upper() in {
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    }:
        return 3
    if path.startswith("/api/smart-reports/calc-metrics") and method.upper() in {
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    }:
        return 3
    if path.startswith("/api/smart-reports"):
        return 1
    if path.startswith("/api/smart-ppt"):
        return 1
    return None


def validate_password_policy(password: str) -> None:
    text = password or ""
    if len(text) < 8:
        raise HTTPException(status_code=400, detail="密码至少 8 位")
    has_alpha = any(ch.isalpha() for ch in text)
    if not has_alpha:
        raise HTTPException(status_code=400, detail="密码至少包含 1 个字母，且区分大小写")
