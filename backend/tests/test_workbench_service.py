from __future__ import annotations

from typing import Any

import pytest

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.workbench.workbench_service import WorkbenchService, WorkbenchServiceError


class FakeWorkbenchStore:
    def __init__(self) -> None:
        self.items = [{"id": 1, "assignee_user_id": 7, "module_code": "workbench", "object_type": "workbench:manual", "status": "in_progress", "row_version": 2}]
        self.notifications = [{"id": 9, "recipient_user_id": 7, "status": "unread"}]

    def list_work_items(self, **kwargs: Any) -> dict[str, Any]:
        return {"items": self.items, "page": kwargs["page"], "page_size": kwargs["page_size"], "total": len(self.items), "has_next": False}

    def transition_work_item(self, item_id: int, **kwargs: Any) -> dict[str, Any]:
        assert item_id == 1
        if kwargs["expected_version"] != self.items[0]["row_version"]:
            raise ValueError("待办已被其他人更新，请刷新后重试")
        self.items[0]["status"] = "completed"
        self.items[0]["row_version"] += 1
        self.items[0]["completed_by"] = kwargs["user"]["id"]
        return dict(self.items[0])

    def list_notifications(self, **kwargs: Any) -> dict[str, Any]:
        return {"items": self.notifications, "page": kwargs["page"], "page_size": kwargs["page_size"], "total": len(self.notifications), "has_next": False}

    def mark_notification_read(self, notification_id: int, *, user_id: int) -> dict[str, Any]:
        assert notification_id == 9 and user_id == 7
        self.notifications[0]["status"] = "read"
        return dict(self.notifications[0])

    def close_notification(self, notification_id: int, *, user_id: int, conclusion: str) -> dict[str, Any]:
        assert notification_id == 9 and user_id == 7
        self.notifications[0]["status"] = "closed"
        self.notifications[0]["close_conclusion"] = conclusion
        return dict(self.notifications[0])


def _user(*permissions: str) -> dict[str, Any]:
    return {"id": 7, "permissions": list(permissions)}


def test_completed_work_item_is_a_state_transition_not_a_delete() -> None:
    store = FakeWorkbenchStore()
    service = WorkbenchService(store)

    result = service.transition_work_item(_user("work_item.manage"), 1, action="complete", expected_version=2, note="已复核")

    assert result["status"] == "completed"
    assert result["completed_by"] == 7
    assert store.items[0]["row_version"] == 3


def test_cancel_requires_reason_and_permissions_are_separate() -> None:
    store = FakeWorkbenchStore()
    service = WorkbenchService(store)

    with pytest.raises(WorkbenchServiceError, match="权限"):
        service.list_work_items(_user(), page=1)
    with pytest.raises(WorkbenchServiceError) as error:
        service.transition_work_item(_user("work_item.manage"), 1, action="cancel", note="")
    assert error.value.code == "CANCEL_REASON_REQUIRED"


def test_notification_read_and_close_keep_history() -> None:
    store = FakeWorkbenchStore()
    service = WorkbenchService(store)
    assert service.mark_notification_read(_user("work_item.manage"), 9)["status"] == "read"
    closed = service.close_notification(_user("work_item.manage"), 9, "已通知责任人")
    assert closed["status"] == "closed"
    assert closed["close_conclusion"] == "已通知责任人"
    assert store.notifications


def test_transition_passes_complete_user_context_to_store() -> None:
    class ContextStore(FakeWorkbenchStore):
        def transition_work_item(self, item_id: int, **kwargs: Any) -> dict[str, Any]:
            assert kwargs["user"]["data_scopes"] == [{"scope_type": "area", "area_id": 8}]
            assert "user_id" not in kwargs
            return {"id": item_id, "status": "claimed", "row_version": 2}

    current = _user("work_item.manage")
    current["data_scopes"] = [{"scope_type": "area", "area_id": 8}]

    result = WorkbenchService(ContextStore()).transition_work_item(current, 1, action="claim", expected_version=1)

    assert result["status"] == "claimed"


@pytest.mark.parametrize("invalid_version", [True, 1.5, "1.5", 0, -1])
def test_transition_rejects_non_positive_or_fractional_versions(invalid_version: object) -> None:
    with pytest.raises(DomainError) as caught:
        WorkbenchService(FakeWorkbenchStore()).transition_work_item(
            _user("work_item.manage"), 1, action="complete", expected_version=invalid_version  # type: ignore[arg-type]
        )

    assert caught.value.code == "EXPECTED_VERSION_REQUIRED"
