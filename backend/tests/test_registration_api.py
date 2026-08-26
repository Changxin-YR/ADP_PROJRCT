from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

import pytest


@dataclass(frozen=True)
class UserRecord:
    id: int
    phone: str
    name: str
    status: str


@dataclass(frozen=True)
class ApplicationRecord:
    id: int
    user_id: int
    version_no: int
    status: str


@dataclass(frozen=True)
class SessionRecord:
    id: int
    user_id: int
    status: str


class RegistrationDatabaseAdapter(Protocol):
    integrity_error: type[Exception]
    state_error: type[Exception]

    def create_pending_user(self, *, phone: str, name: str, password_hash: str) -> UserRecord: ...

    def create_role(self, *, code: str, name: str) -> int: ...

    def create_area(self, *, code: str, name: str) -> int: ...

    def create_data_scope(self, *, area_id: int, scope_code: str, scope_name: str) -> int: ...

    def submit_application(
        self,
        *,
        user_id: int,
        version_no: int,
        name: str,
        desired_role_id: int,
        area_id: int,
        application_note: str,
    ) -> ApplicationRecord: ...

    def approve_application(
        self,
        *,
        application_id: int,
        reviewed_by_user_id: int,
        final_role_id: int,
        data_scope_id: int,
    ) -> None: ...

    def set_user_status(self, *, user_id: int, status: str) -> None: ...

    def create_session(self, *, user_id: int, session_hash: str, expires_at: str) -> SessionRecord: ...

    def get_user_status(self, *, user_id: int) -> str: ...

    def get_user_role_ids(self, *, user_id: int) -> list[int]: ...

    def get_user_data_scope_ids(self, *, user_id: int) -> list[int]: ...

    def get_application(self, *, application_id: int) -> ApplicationRecord: ...


@pytest.fixture(scope="session", autouse=True)
def _require_non_production_database_target() -> None:
    candidate_names = [
        os.getenv("ADP_TEST_MYSQL_DATABASE"),
        os.getenv("MYSQL_DATABASE"),
        os.getenv("DB_NAME"),
    ]
    for candidate in candidate_names:
        if candidate and "prod" in candidate.lower():
            pytest.fail(
                "Refusing to run auth database contract tests against a production-like database name. "
                "Configure a dedicated local test database for backend fixtures."
            )


@pytest.fixture
def registration_db_adapter(request: pytest.FixtureRequest) -> RegistrationDatabaseAdapter:
    # Task 3 is expected to provide the real adapter fixture. We bridge to it when
    # present, and skip cleanly when the fixture has not been introduced yet.
    try:
        return request.getfixturevalue("real_registration_db_adapter")
    except pytest.FixtureLookupError:
        pytest.skip(
            "Task 3 has not provided a 'real_registration_db_adapter' fixture yet. "
            "This contract test will run once the real adapter bridge exists."
        )


def test_phone_must_be_unique(registration_db_adapter: RegistrationDatabaseAdapter) -> None:
    registration_db_adapter.create_pending_user(
        phone="13800000000",
        name="测试用户甲",
        password_hash="hash-a",
    )

    with pytest.raises(registration_db_adapter.integrity_error):
        registration_db_adapter.create_pending_user(
            phone="13800000000",
            name="测试用户乙",
            password_hash="hash-b",
        )


def test_application_versions_only_increase(registration_db_adapter: RegistrationDatabaseAdapter) -> None:
    user = registration_db_adapter.create_pending_user(
        phone="13800000001",
        name="版本测试",
        password_hash="hash-version",
    )
    role_id = registration_db_adapter.create_role(code="farmer", name="养殖员")
    area_id = registration_db_adapter.create_area(code="area-a", name="A 区")

    first_application = registration_db_adapter.submit_application(
        user_id=user.id,
        version_no=1,
        name=user.name,
        desired_role_id=role_id,
        area_id=area_id,
        application_note="首次申请",
    )

    assert first_application.version_no == 1

    second_application = registration_db_adapter.submit_application(
        user_id=user.id,
        version_no=2,
        name=user.name,
        desired_role_id=role_id,
        area_id=area_id,
        application_note="第二次申请",
    )

    assert second_application.version_no == 2

    with pytest.raises(registration_db_adapter.integrity_error):
        registration_db_adapter.submit_application(
            user_id=user.id,
            version_no=1,
            name=user.name,
            desired_role_id=role_id,
            area_id=area_id,
            application_note="重复版本号必须失败",
        )

    with pytest.raises((registration_db_adapter.state_error, registration_db_adapter.integrity_error)):
        registration_db_adapter.submit_application(
            user_id=user.id,
            version_no=0,
            name=user.name,
            desired_role_id=role_id,
            area_id=area_id,
            application_note="版本号必须递增",
        )


def test_pending_users_have_no_business_data_scope(
    registration_db_adapter: RegistrationDatabaseAdapter,
) -> None:
    user = registration_db_adapter.create_pending_user(
        phone="13800000002",
        name="待审核用户",
        password_hash="hash-pending",
    )

    assert registration_db_adapter.get_user_status(user_id=user.id) == "pending"
    assert registration_db_adapter.get_user_role_ids(user_id=user.id) == []
    assert registration_db_adapter.get_user_data_scope_ids(user_id=user.id) == []


def test_approval_writes_active_status_role_and_scope_together(
    registration_db_adapter: RegistrationDatabaseAdapter,
) -> None:
    reviewer = registration_db_adapter.create_pending_user(
        phone="13800000003",
        name="审核管理员",
        password_hash="hash-reviewer",
    )
    registration_db_adapter.set_user_status(user_id=reviewer.id, status="active")

    applicant = registration_db_adapter.create_pending_user(
        phone="13800000004",
        name="申请人",
        password_hash="hash-applicant",
    )
    role_id = registration_db_adapter.create_role(code="manager", name="区域管理员")
    area_id = registration_db_adapter.create_area(code="area-b", name="B 区")
    scope_id = registration_db_adapter.create_data_scope(
        area_id=area_id,
        scope_code="area-b-all",
        scope_name="B 区全部数据",
    )
    application = registration_db_adapter.submit_application(
        user_id=applicant.id,
        version_no=1,
        name=applicant.name,
        desired_role_id=role_id,
        area_id=area_id,
        application_note="等待审批",
    )

    registration_db_adapter.approve_application(
        application_id=application.id,
        reviewed_by_user_id=reviewer.id,
        final_role_id=role_id,
        data_scope_id=scope_id,
    )

    approved_application = registration_db_adapter.get_application(application_id=application.id)
    assert registration_db_adapter.get_user_status(user_id=applicant.id) == "active"
    assert registration_db_adapter.get_user_role_ids(user_id=applicant.id) == [role_id]
    assert registration_db_adapter.get_user_data_scope_ids(user_id=applicant.id) == [scope_id]
    assert approved_application.status == "approved"


def test_disabled_users_cannot_establish_sessions(
    registration_db_adapter: RegistrationDatabaseAdapter,
) -> None:
    user = registration_db_adapter.create_pending_user(
        phone="13800000005",
        name="停用用户",
        password_hash="hash-disabled",
    )
    registration_db_adapter.set_user_status(user_id=user.id, status="disabled")

    with pytest.raises(registration_db_adapter.state_error):
        registration_db_adapter.create_session(
            user_id=user.id,
            session_hash="dev-session-hash",
            expires_at="2099-01-01 00:00:00",
        )
