from __future__ import annotations

from typing import Any, Protocol

from backend.layers.common.governance.lifecycle import parse_positive_integer


class WorkbenchServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class WorkbenchStore(Protocol):
    def workbench_summary(self, *, user: dict[str, Any]) -> dict[str, Any]: ...
    def list_work_items(self, *, user: dict[str, Any], status: str | None, include_history: bool, page: int, page_size: int) -> dict[str, Any]: ...
    def transition_work_item(self, item_id: int, *, user: dict[str, Any], action: str, expected_version: int | None, note: str | None) -> dict[str, Any]: ...
    def list_notifications(self, *, user_id: int, status: str | None, include_history: bool, page: int, page_size: int) -> dict[str, Any]: ...
    def mark_notification_read(self, notification_id: int, *, user_id: int) -> dict[str, Any]: ...
    def close_notification(self, notification_id: int, *, user_id: int, conclusion: str) -> dict[str, Any]: ...


class WorkbenchService:
    def __init__(self, store: WorkbenchStore) -> None:
        self.store = store

    @staticmethod
    def require_permission(user: dict[str, Any], permission: str) -> None:
        permissions = set(user.get("permissions") or [])
        if permission not in permissions:
            raise WorkbenchServiceError("FORBIDDEN", "当前账号没有待办/消息权限", 403)

    def list_work_items(self, user: dict[str, Any], *, status: str | None = None, include_history: bool = True, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        self.require_permission(user, "work_item.view")
        result = self.store.list_work_items(user=user, status=status, include_history=include_history, page=max(1, page), page_size=min(100, max(1, page_size)))
        return {**result, "items": [{**item, "handling_mode": "manual" if item.get("module_code") == "workbench" and item.get("object_type") == "workbench:manual" else "domain"} for item in result["items"]]}

    def summary(self, user: dict[str, Any]) -> dict[str, Any]:
        self.require_permission(user, "workbench.enter")
        summary = self.store.workbench_summary(user=user)
        work_items = self.store.list_work_items(user=user, status=None, include_history=False, page=1, page_size=5)
        notifications = self.store.list_notifications(user_id=int(user["id"]), status=None, include_history=False, page=1, page_size=5)
        summary["kpis"]["todo_open"] = int(work_items["total"])
        summary["todos"] = [
            {
                "id": item["id"], "title": item["title"], "type": item["action_code"],
                "due_at": item.get("due_at") or "未设置期限", "overdue": bool(item.get("overdue")),
            }
            for item in work_items["items"]
        ]
        summary["alerts"] = [
            {
                "id": item["id"], "title": item["title"],
                "level": "high" if item["level"] in {"high", "critical"} else "medium",
                "created_at": item.get("last_occurred_at") or item.get("created_at"),
            }
            for item in notifications["items"]
        ]
        return summary

    def transition_work_item(self, user: dict[str, Any], item_id: int, *, action: str, expected_version: Any = None, note: str | None = None) -> dict[str, Any]:
        self.require_permission(user, "work_item.manage")
        if action not in {"claim", "start", "complete", "cancel"}:
            raise WorkbenchServiceError("VALIDATION_ERROR", "待办操作无效", 400)
        if action == "cancel" and not str(note or "").strip():
            raise WorkbenchServiceError("CANCEL_REASON_REQUIRED", "取消待办必须填写原因", 400)
        normalized_version = None if expected_version is None else parse_positive_integer(
            expected_version,
            code="EXPECTED_VERSION_REQUIRED",
            message="必须提供 expected_version",
        )
        try:
            return self.store.transition_work_item(int(item_id), user=user, action=action, expected_version=normalized_version, note=str(note).strip() if note else None)
        except PermissionError as exc:
            raise WorkbenchServiceError("FORBIDDEN", str(exc), 403) from exc
        except ValueError as exc:
            raise WorkbenchServiceError("WORK_ITEM_TRANSITION_FAILED", str(exc), 409) from exc

    def list_notifications(self, user: dict[str, Any], *, status: str | None = None, include_history: bool = True, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        self.require_permission(user, "work_item.view")
        return self.store.list_notifications(user_id=int(user["id"]), status=status, include_history=include_history, page=max(1, page), page_size=min(100, max(1, page_size)))

    def mark_notification_read(self, user: dict[str, Any], notification_id: int) -> dict[str, Any]:
        self.require_permission(user, "work_item.manage")
        try:
            return self.store.mark_notification_read(int(notification_id), user_id=int(user["id"]))
        except ValueError as exc:
            raise WorkbenchServiceError("NOTIFICATION_UPDATE_FAILED", str(exc), 409) from exc

    def close_notification(self, user: dict[str, Any], notification_id: int, conclusion: str) -> dict[str, Any]:
        self.require_permission(user, "work_item.manage")
        if not conclusion.strip():
            raise WorkbenchServiceError("CLOSE_CONCLUSION_REQUIRED", "关闭消息必须填写处理结论", 400)
        try:
            return self.store.close_notification(int(notification_id), user_id=int(user["id"]), conclusion=conclusion.strip())
        except ValueError as exc:
            raise WorkbenchServiceError("NOTIFICATION_UPDATE_FAILED", str(exc), 409) from exc
