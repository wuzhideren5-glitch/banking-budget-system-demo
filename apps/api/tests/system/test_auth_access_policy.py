from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace
import unittest

from fastapi import HTTPException
from starlette.responses import JSONResponse


class AuthAccessPolicyTests(unittest.TestCase):
    def _policy(self):
        return importlib.import_module("app.services.auth_access_policy")

    def test_role_names_permission_sets_and_paths_are_owned_by_policy_module(self) -> None:
        policy = self._policy()

        self.assertEqual(policy.role_name_from_permission(1), "全权管理员")
        self.assertEqual(policy.role_name_from_permission(2), "数据录入用户")
        self.assertEqual(policy.role_name_from_permission(99), "数据浏览用户")

        self.assertEqual(policy.permission_set(1), {1, 2, 3})
        self.assertEqual(policy.permission_set(2), {1, 2})
        self.assertEqual(policy.permission_set(3), {1})

        self.assertEqual(policy.path_required_permission("/api/system/users", "GET"), 3)
        self.assertIsNone(policy.path_required_permission("/api/budget-input", "POST"))
        self.assertEqual(policy.path_required_permission("/api/org-product-data-entry", "POST"), 2)
        self.assertEqual(policy.path_required_permission("/api/org-product-runtime-products", "GET"), 1)
        self.assertEqual(policy.path_required_permission("/api/org-product-runtime-products", "POST"), 3)
        self.assertIsNone(policy.path_required_permission("/api/product-types", "GET"))
        self.assertIsNone(policy.path_required_permission("/api/product-types", "POST"))
        self.assertIsNone(policy.path_required_permission("/api/health", "HEAD"))
        self.assertEqual(policy.path_required_permission("/api/dept-accounts", "GET"), 3)
        self.assertEqual(policy.path_required_permission("/api/budget-output/report", "GET"), 1)
        self.assertEqual(policy.path_required_permission("/api/smart-reports/templates", "POST"), 3)
        self.assertEqual(policy.path_required_permission("/api/smart-reports/templates", "GET"), 1)
        self.assertIsNone(policy.path_required_permission("/api/health", "GET"))

    def test_password_policy_keeps_existing_http_error_contract(self) -> None:
        policy = self._policy()

        with self.assertRaises(HTTPException) as short_password:
            policy.validate_password_policy("abc123")
        self.assertEqual(short_password.exception.status_code, 400)
        self.assertEqual(short_password.exception.detail, "密码至少 8 位")

        with self.assertRaises(HTTPException) as no_alpha:
            policy.validate_password_policy("12345678")
        self.assertEqual(no_alpha.exception.status_code, 400)
        self.assertEqual(no_alpha.exception.detail, "密码至少包含 1 个字母，且区分大小写")

        self.assertIsNone(policy.validate_password_policy("abc12345"))

    def test_request_access_decision_matches_current_middleware_contract(self) -> None:
        policy = self._policy()

        self.assertTrue(policy.auth_request_access("GET", "/help", None).allowed)
        self.assertTrue(policy.auth_request_access("OPTIONS", "/api/system/users", None).allowed)
        self.assertTrue(policy.auth_request_access("POST", "/api/login", None).allowed)
        self.assertTrue(policy.auth_request_access("GET", "/api/health", None).allowed)
        self.assertTrue(policy.auth_request_access("HEAD", "/api/health", None).allowed)

        session_missing = policy.auth_request_access("GET", "/api/session", None)
        self.assertFalse(session_missing.allowed)
        self.assertEqual(session_missing.status_code, 401)
        self.assertEqual(session_missing.detail, "未登录")
        self.assertFalse(session_missing.clear_session_cookie)

        api_missing = policy.auth_request_access("GET", "/api/budget-output", None)
        self.assertFalse(api_missing.allowed)
        self.assertEqual(api_missing.status_code, 401)
        self.assertEqual(api_missing.detail, "未登录，请先登录")
        self.assertTrue(api_missing.clear_session_cookie)

        first_login_ctx = {"must_change_password": 1, "permission_type": 1}
        self.assertTrue(policy.auth_request_access("POST", "/api/change-password-first-login", first_login_ctx).allowed)
        first_login_blocked = policy.auth_request_access("GET", "/api/budget-output", first_login_ctx)
        self.assertFalse(first_login_blocked.allowed)
        self.assertEqual(first_login_blocked.status_code, 403)
        self.assertEqual(first_login_blocked.detail, "首次登录请先修改密码")

        browse_ctx = {"must_change_password": 0, "permission_type": 3}
        self.assertTrue(policy.auth_request_access("GET", "/api/budget-output", browse_ctx).allowed)
        denied = policy.auth_request_access("POST", "/api/org-product-data-entry", browse_ctx)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.detail, "权限不足")

    def test_main_no_longer_keeps_auth_policy_helpers(self) -> None:
        main_source = (Path(__file__).parent / "app" / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("def _role_name_from_permission", main_source)
        self.assertNotIn("def _permission_set", main_source)
        self.assertNotIn("def _path_required_permission", main_source)
        self.assertNotIn("def _validate_password_policy", main_source)
        self.assertNotIn("anonymous_allowed", main_source)
        self.assertNotIn('path not in {"/api/session", "/api/change-password-first-login", "/api/logout"}', main_source)
        self.assertNotIn('"权限不足"', main_source)

    def test_auth_request_middleware_module_owns_request_flow(self) -> None:
        middleware_module = importlib.import_module("app.services.auth_request_middleware")

        async def run() -> None:
            loaded_sessions: list[str | None] = []

            async def load_session(session_id: str | None):
                loaded_sessions.append(session_id)
                if session_id == "valid":
                    return {"session_id": "valid", "must_change_password": 0, "permission_type": 1}
                return None

            async def call_next(request):
                return JSONResponse({"user": getattr(request.state, "current_user", None)})

            public_request = SimpleNamespace(
                method="GET",
                url=SimpleNamespace(path="/help"),
                cookies={},
                state=SimpleNamespace(),
            )
            public_response = await middleware_module.build_auth_request_middleware(
                session_cookie_name="budget_session",
                load_session_context=load_session,
            )(public_request, call_next)
            self.assertEqual(public_response.status_code, 200)
            self.assertEqual(loaded_sessions, [])

            missing_request = SimpleNamespace(
                method="GET",
                url=SimpleNamespace(path="/api/budget-output"),
                cookies={},
                state=SimpleNamespace(),
            )
            missing_response = await middleware_module.build_auth_request_middleware(
                session_cookie_name="budget_session",
                load_session_context=load_session,
            )(missing_request, call_next)
            self.assertEqual(missing_response.status_code, 401)
            self.assertIn("budget_session", missing_response.headers.get("set-cookie", ""))

            authed_request = SimpleNamespace(
                method="GET",
                url=SimpleNamespace(path="/api/session"),
                cookies={"budget_session": "valid"},
                state=SimpleNamespace(),
            )
            authed_response = await middleware_module.build_auth_request_middleware(
                session_cookie_name="budget_session",
                load_session_context=load_session,
            )(authed_request, call_next)
            self.assertEqual(authed_response.status_code, 200)
            self.assertEqual(authed_request.state.current_user["session_id"], "valid")

        asyncio.run(run())

    def test_main_no_longer_keeps_auth_request_middleware_flow(self) -> None:
        main_source = (Path(__file__).parent / "app" / "main.py").read_text(encoding="utf-8")

        self.assertIn("build_auth_request_middleware", main_source)
        self.assertNotIn('@app.middleware("http")', main_source)
        self.assertNotIn("request.cookies.get(SESSION_COOKIE_NAME)", main_source)
        self.assertNotIn("request.state.current_user", main_source)


if __name__ == "__main__":
    unittest.main()
