from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

import pymysql
from pymysql.connections import Connection


class RegistrationStateError(RuntimeError):
    pass


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


class MySqlRegistrationTestAdapter:
    integrity_error = pymysql.IntegrityError
    state_error = RegistrationStateError

    def __init__(self, *, host: str, port: int, database: str, user: str, password: str) -> None:
        self.connection_options = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": False,
        }

    @contextmanager
    def _transaction(self) -> Iterator[Connection]:
        connection = pymysql.connect(**self.connection_options)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_pending_user(self, *, phone: str, name: str, password_hash: str) -> UserRecord:
        with self._transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (phone,name,password_hash,status) VALUES (%s,%s,%s,'pending')",
                (phone, name, password_hash),
            )
            return UserRecord(cursor.lastrowid, phone, name, "pending")

    def create_role(self, *, code: str, name: str) -> int:
        with self._transaction() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO roles (code,name) VALUES (%s,%s)", (code, name))
            return int(cursor.lastrowid)

    def create_area(self, *, code: str, name: str) -> int:
        with self._transaction() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO areas (code,name) VALUES (%s,%s)", (code, name))
            return int(cursor.lastrowid)

    def create_data_scope(self, *, area_id: int, scope_code: str, scope_name: str) -> int:
        with self._transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO data_scopes (code,name,scope_type,area_id) VALUES (%s,%s,'area',%s)",
                (scope_code, scope_name, area_id),
            )
            return int(cursor.lastrowid)

    def submit_application(
        self,
        *,
        user_id: int,
        version_no: int,
        name: str,
        desired_role_id: int,
        area_id: int,
        application_note: str,
    ) -> ApplicationRecord:
        with self._transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(version_no),0) AS version_no FROM registration_applications WHERE user_id=%s FOR UPDATE",
                (user_id,),
            )
            latest = int(cursor.fetchone()["version_no"])
            if version_no <= 0 or version_no > latest + 1:
                raise RegistrationStateError("application version must increase by one")
            cursor.execute(
                "INSERT INTO registration_applications (user_id,version_no,name,desired_role_id,area_id,application_note) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (user_id, version_no, name, desired_role_id, area_id, application_note),
            )
            return ApplicationRecord(cursor.lastrowid, user_id, version_no, "pending")

    def approve_application(
        self,
        *,
        application_id: int,
        reviewed_by_user_id: int,
        final_role_id: int,
        data_scope_id: int,
    ) -> None:
        with self._transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT user_id,status FROM registration_applications WHERE id=%s FOR UPDATE",
                (application_id,),
            )
            application = cursor.fetchone()
            if application is None or application["status"] != "pending":
                raise RegistrationStateError("application is not pending")
            user_id = int(application["user_id"])
            cursor.execute("UPDATE users SET status='active' WHERE id=%s", (user_id,))
            cursor.execute(
                "INSERT INTO user_roles (user_id,role_id,granted_by) VALUES (%s,%s,%s)",
                (user_id, final_role_id, reviewed_by_user_id),
            )
            cursor.execute(
                "INSERT INTO user_data_scopes (user_id,data_scope_id,granted_by) VALUES (%s,%s,%s)",
                (user_id, data_scope_id, reviewed_by_user_id),
            )
            cursor.execute(
                "UPDATE registration_applications SET status='approved',reviewed_by=%s,reviewed_at=CURRENT_TIMESTAMP WHERE id=%s",
                (reviewed_by_user_id, application_id),
            )

    def set_user_status(self, *, user_id: int, status: str) -> None:
        with self._transaction() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE users SET status=%s WHERE id=%s", (status, user_id))

    def create_session(self, *, user_id: int, session_hash: str, expires_at: str) -> SessionRecord:
        with self._transaction() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status FROM users WHERE id=%s FOR UPDATE", (user_id,))
            user = cursor.fetchone()
            if user is None or user["status"] not in {"active", "must_change_password"}:
                raise RegistrationStateError("user status cannot establish a session")
            cursor.execute(
                "INSERT INTO sessions (user_id,session_token_hash,status,expires_at) VALUES (%s,%s,'active',%s)",
                (user_id, session_hash, expires_at),
            )
            return SessionRecord(cursor.lastrowid, user_id, "active")

    def get_user_status(self, *, user_id: int) -> str:
        return str(self._one("SELECT status FROM users WHERE id=%s", (user_id,))["status"])

    def get_user_role_ids(self, *, user_id: int) -> list[int]:
        return self._ids("SELECT role_id AS id FROM user_roles WHERE user_id=%s ORDER BY role_id", user_id)

    def get_user_data_scope_ids(self, *, user_id: int) -> list[int]:
        return self._ids("SELECT data_scope_id AS id FROM user_data_scopes WHERE user_id=%s ORDER BY data_scope_id", user_id)

    def get_application(self, *, application_id: int) -> ApplicationRecord:
        row = self._one(
            "SELECT id,user_id,version_no,status FROM registration_applications WHERE id=%s",
            (application_id,),
        )
        return ApplicationRecord(int(row["id"]), int(row["user_id"]), int(row["version_no"]), str(row["status"]))

    def _one(self, sql: str, params: tuple[int]) -> dict[str, object]:
        with self._transaction() as connection, connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if row is None:
                raise RegistrationStateError("record not found")
            return row

    def _ids(self, sql: str, user_id: int) -> list[int]:
        with self._transaction() as connection, connection.cursor() as cursor:
            cursor.execute(sql, (user_id,))
            return [int(row["id"]) for row in cursor.fetchall()]
