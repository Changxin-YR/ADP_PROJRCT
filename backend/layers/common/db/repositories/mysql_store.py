from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from pymysql.err import IntegrityError

from backend.config.settings import Settings
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.application_repository import ApplicationRepository
from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.repositories.rate_limit_repository import RateLimitRepository
from backend.layers.common.db.repositories.review_repository import ReviewRepository
from backend.layers.common.db.repositories.role_repository import RoleRepository
from backend.layers.common.db.repositories.session_repository import SessionRepository
from backend.layers.common.db.repositories.user_repository import UserRepository
from backend.layers.common.db.repositories.governance_repository import GovernanceRepository
from backend.layers.common.db.repositories.workbench_repository import WorkbenchRepository
from backend.layers.common.db.repositories.auth_admin_store import AuthAdminStoreMixin
from backend.layers.common.db.repositories.auth_session_store import AuthSessionStoreMixin
from backend.layers.common.db.repositories.store_errors import StoreError


class MySqlAuthStore(AuthSessionStoreMixin, AuthAdminStoreMixin):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.users = UserRepository()
        self.applications = ApplicationRepository()
        self.sessions = SessionRepository()
        self.rate_limits = RateLimitRepository()
        self.review = ReviewRepository()
        self.roles = RoleRepository()
        self.governance = GovernanceRepository()
        self.workbench = WorkbenchRepository()
        self.audit = AuditLogger()

    def audit_event(
        self,
        *,
        user_id: int | None = None,
        action: str,
        object_type: str,
        object_id: int | None = None,
        result: str,
        ip_address: str | None = None,
        request_id: str | None = None,
        object_ref: str | None = None,
        reason: str | None = None,
        before: Any = None,
        after: Any = None,
        detail: Any = None,
    ) -> None:
        """统一写入安全与业务审计事件；敏感字段由 AuditLogger 递归脱敏。"""
        with self.transaction() as connection:
            self.audit.write(
                connection,
                user_id=user_id,
                action=action,
                object_type=object_type,
                object_id=object_id,
                result=result,
                ip_address=ip_address,
                request_id=request_id,
                module_code="auth" if action in {"login", "logout", "password_change", "session_revoke"} else "system",
                action_code=action,
                object_ref=object_ref,
                reason=reason,
                before=before,
                after=after,
                detail_json=json.dumps(detail, ensure_ascii=False, default=str) if detail is not None else None,
            )
    def workbench_summary(self, *, user: dict[str, Any]) -> dict[str, Any]:
        with self.transaction() as connection:
            return self.workbench.summary(connection, user=user)

    def list_work_items(self, *, user: dict[str, Any], status: str | None = None, include_history: bool = True, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        modules = self._work_item_modules(set(user.get("permissions") or []))
        scopes = user.get("data_scopes") or []
        roles = {item.get("code") for item in user.get("roles") or []}
        # Unassigned domain work is tenant-safe only for a super admin or an
        # area-scoped reviewer; the current scope schema cannot identify a
        # non-admin farm's organization.
        allow_unassigned = "super_admin" in roles or ("work_item.view" in set(user.get("permissions") or []) and any(item.get("scope_type") == "area" for item in scopes))
        area_ids = sorted({int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")})
        with self.transaction() as connection:
            return self.governance.list_work_items(connection, user_id=int(user["id"]), allowed_modules=modules, allow_unassigned=allow_unassigned, allowed_area_ids=area_ids, status=status, include_history=include_history, page=page, page_size=page_size)

    @staticmethod
    def _work_item_modules(permissions: set[str]) -> list[str]:
        mapping = {
            "master_data.view": "master_data", "production.view": "production", "warehouse.view": "warehouse",
            "purchase.view": "purchase", "sales.view": "sales", "cost.view": "cost",
            "finance.payable.view": "finance", "finance.receivable.view": "finance",
            "data_exchange.view": "data_exchange", "workbench.enter": "workbench",
        }
        return sorted({module for permission, module in mapping.items() if permission in permissions})

    def transition_work_item(self, item_id: int, *, user: dict[str, Any], action: str, expected_version: int | None = None, note: str | None = None) -> dict[str, Any]:
        user_id = int(user["id"])
        modules = self._work_item_modules(set(user.get("permissions") or []))
        scopes = user.get("data_scopes") or []
        roles = {item.get("code") for item in user.get("roles") or []}
        allow_unassigned = "super_admin" in roles or ("work_item.view" in set(user.get("permissions") or []) and any(item.get("scope_type") == "area" for item in scopes))
        area_ids = sorted({int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")})
        with self.transaction() as connection:
            result = self.governance.transition_work_item(connection, item_id=item_id, user_id=user_id, allowed_modules=modules, allow_unassigned=allow_unassigned, allowed_area_ids=area_ids, action=action, expected_version=expected_version, note=note)
            before_status = result.pop("_audit_before_status", None)
            self.audit.write(
                connection,
                user_id=user_id,
                action=f"work_item_{action}",
                object_type="work_item",
                object_id=item_id,
                object_ref=f"work_item:{item_id}",
                result="success",
                ip_address=None,
                module_code="workbench",
                action_code=f"work_item_{action}",
                related_work_item_id=item_id,
                reason=note,
                before={"status": before_status},
                after=result,
            )
            return result

    def list_notifications(self, *, user_id: int, status: str | None = None, include_history: bool = True, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        with self.transaction() as connection:
            return self.governance.list_notifications(connection, user_id=user_id, status=status, include_history=include_history, page=page, page_size=page_size)

    def mark_notification_read(self, notification_id: int, *, user_id: int) -> dict[str, Any]:
        with self.transaction() as connection:
            result = self.governance.mark_notification_read(connection, notification_id=notification_id, user_id=user_id)
            self.audit.write(connection, user_id=user_id, action="notification_read", object_type="notification", object_id=notification_id, object_ref=f"notification:{notification_id}", result="success", ip_address=None, module_code="workbench", action_code="notification_read")
            return result

    def close_notification(self, notification_id: int, *, user_id: int, conclusion: str) -> dict[str, Any]:
        with self.transaction() as connection:
            result = self.governance.close_notification(connection, notification_id=notification_id, user_id=user_id, conclusion=conclusion)
            self.audit.write(connection, user_id=user_id, action="notification_close", object_type="notification", object_id=notification_id, object_ref=f"notification:{notification_id}", result="success", ip_address=None, module_code="workbench", action_code="notification_close", reason=conclusion)
            return result

    def list_audit_logs(self, **filters: Any) -> dict[str, Any]:
        with self.transaction() as connection:
            return self.governance.list_audit_logs(connection, **filters)

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        with get_connection(self.settings) as connection:
            yield connection

    def get_user_by_identifier(self, identifier: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            return self._with_permissions(connection, self.users.find_by_identifier(connection, identifier))

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self.transaction() as connection:
            return self._with_permissions(connection, self.users.find_by_id(connection, user_id))

    def _with_permissions(self, connection: Any, user: dict[str, Any] | None) -> dict[str, Any] | None:
        if user is None:
            return None
        roles, data_scopes, permissions = self.users.permissions(connection, user_id=int(user["id"]))
        return {**user, "roles": roles, "data_scopes": data_scopes, "permissions": permissions}

    def record_failed_login(self, user_id: int, *, threshold: int, lock_minutes: int) -> bool:
        now = datetime.now(timezone.utc)
        locked_until = now + timedelta(minutes=lock_minutes)
        with self.transaction() as connection:
            # Increment and lock decision happen in one row update so concurrent
            # failed attempts cannot all observe the same pre-increment count.
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET failed_login_count = failed_login_count + 1, "
                    "locked_until = CASE WHEN failed_login_count + 1 >= %s THEN %s ELSE NULL END "
                    "WHERE id = %s",
                    (threshold, locked_until, user_id),
                )
                if cursor.rowcount != 1:
                    return False
                cursor.execute("SELECT failed_login_count FROM users WHERE id=%s", (user_id,))
                row = cursor.fetchone() or {}
                return int(row.get("failed_login_count") or 0) >= threshold

    def reset_failed_login(self, user_id: int) -> None:
        with self.transaction() as connection:
            self.users.reset_failed_login(connection, user_id=user_id, logged_in_at=datetime.now(timezone.utc))

    def consume_rate_limit(self, limit_type: str, subject_key: str, *, limit: int, window_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        window_epoch = int(now.timestamp()) // window_seconds * window_seconds
        window_started_at = datetime.fromtimestamp(window_epoch, tz=timezone.utc).replace(tzinfo=None)
        with self.transaction() as connection:
            return self.rate_limits.consume(
                connection,
                limit_type=limit_type,
                subject_key=subject_key,
                window_started_at=window_started_at,
                limit=limit,
            )

    def register_pending(self, payload: dict[str, Any], *, password_hash: str) -> dict[str, Any]:
        try:
            with self.transaction() as connection:
                user_id = self.users.create_pending(
                    connection,
                    phone=payload["phone"],
                    name=payload["name"],
                    password_hash=password_hash,
                )
                application = self.applications.create(
                    connection,
                    user_id=user_id,
                    name=payload["name"],
                    desired_role_id=int(payload["desired_role_id"]),
                    area_id=int(payload["area_id"]),
                    application_note=payload.get("application_note", ""),
                    desired_scope_type=payload.get("desired_scope_type") or None,
                )
                self.audit.write(
                    connection,
                    user_id=user_id,
                    action="register",
                    object_type="registration_application",
                    object_id=application["id"],
                    result="success",
                    ip_address=payload.get("ip_address"),
                )
                user = self.users.find_by_id(connection, user_id)
                return {"user": user, "application": application}
        except IntegrityError as exc:
            if exc.args and exc.args[0] == 1062:
                raise StoreError("PHONE_EXISTS", "该手机号已注册，请直接登录或联系管理员处理", 409) from exc
            raise

    def get_application(self, user_id: int) -> dict[str, Any] | None:
        with self.transaction() as connection:
            return self.applications.latest_for_user(connection, user_id=user_id)

    def resubmit_application(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self.transaction() as connection:
            user = self.users.find_by_id(connection, user_id)
            latest = self.applications.latest_for_user(connection, user_id=user_id)
            if user is None or latest is None or user["status"] != "rejected":
                raise StoreError("APPLICATION_NOT_REJECTED", "当前申请状态不允许重新提交", 409)
            if int(latest["version_no"]) >= 3:
                raise StoreError("REAPPLY_LIMIT_REACHED", "重新提交次数已达到上限", 409)
            application = self.applications.create(
                connection,
                user_id=user_id,
                name=payload["name"],
                desired_role_id=int(payload["desired_role_id"]),
                area_id=int(payload["area_id"]),
                application_note=payload.get("application_note", ""),
                desired_scope_type=payload.get("desired_scope_type") or None,
            )
            self.users.set_status(connection, user_id=user_id, status="pending")
            return application

    def change_password(self, user_id: int, *, password_hash: str, activate: bool) -> None:
        with self.transaction() as connection:
            self.users.update_password(
                connection,
                user_id=user_id,
                password_hash=password_hash,
                status="active" if activate else None,
            )
            with connection.cursor() as cursor:
                cursor.execute("UPDATE sessions SET status='revoked', revoked_at=CURRENT_TIMESTAMP, revoke_reason='password_change' WHERE user_id=%s AND status='active'", (user_id,))
