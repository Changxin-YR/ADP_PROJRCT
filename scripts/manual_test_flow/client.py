"""HTTP 传输层：会话、CSRF、幂等友好的写请求与附件上传（标准库实现）。"""
from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.request
import uuid
from datetime import datetime

PREFIX = "MT2609"
ORGANIZATION_ID = 1
FARM_ID = 1


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, payload: dict | None = None) -> None:
        super().__init__(f"[{status} {code}] {message}")
        self.status = status
        self.code = code
        self.message = message
        self.payload = payload or {}


class Client:
    """一个账号一个实例：自带 cookie 与 CSRF 令牌。"""

    def __init__(self, base_url: str, identifier: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.identifier = identifier
        self.password = password
        self.cookies: dict[str, str] = {}
        self.csrf = ""
        self.user: dict = {}

    # ---------- 内部 ----------
    def _url(self, path: str) -> str:
        return path if path.startswith("http") else f"{self.base_url}{path if path.startswith('/') else '/' + path}"

    def _cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())

    def _store_cookies(self, response) -> None:
        for header, value in response.getheaders():
            if header.lower() != "set-cookie":
                continue
            pair = value.split(";", 1)[0]
            if "=" in pair:
                name, cookie_value = pair.split("=", 1)
                if cookie_value == "":
                    self.cookies.pop(name.strip(), None)
                else:
                    self.cookies[name.strip()] = cookie_value.strip()

    def _headers(self, method: str, path: str, *, json_body: bool) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if json_body:
            headers["Content-Type"] = "application/json"
        if method in {"POST", "PUT", "PATCH", "DELETE"} and self.csrf and path != "/api/v1/auth/csrf":
            headers["X-CSRF-Token"] = self.csrf
        if self.cookies:
            headers["Cookie"] = self._cookie_header()
        return headers

    # ---------- 通用请求 ----------
    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self._url(path), data=data, method=method, headers=self._headers(method, path, json_body=body is not None)
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                self._store_cookies(response)
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            self._store_cookies(error)
            raw = error.read()
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except Exception:  # noqa: BLE001
                parsed = {"code": "HTTP_ERROR", "message": raw.decode("utf-8", "replace")[:200]}
            raise ApiError(error.code, str(parsed.get("code")), str(parsed.get("message")), parsed) from None

    def get(self, path: str) -> tuple[int, dict]:
        return self.request("GET", path)

    def post(self, path: str, body: dict | None = None) -> tuple[int, dict]:
        return self.request("POST", path, body if body is not None else {})

    def patch(self, path: str, body: dict) -> tuple[int, dict]:
        return self.request("PATCH", path, body)

    def delete(self, path: str) -> tuple[int, dict]:
        return self.request("DELETE", path)

    # ---------- 鉴权 ----------
    def login(self) -> dict:
        _, payload = self.get("/api/v1/auth/csrf")
        self.csrf = payload["data"]["csrf_token"]
        _, payload = self.post("/api/v1/auth/login", {"identifier": self.identifier, "password": self.password})
        self.user = payload["data"]["user"]
        return self.user

    # ---------- 附件 ----------
    def upload_attachment(self, entity_type: str, entity_id: int, file_name: str = "mt2609-evidence.txt") -> int:
        boundary = f"----mt2609{uuid.uuid4().hex}"
        content = f"{PREFIX} 验收凭据 {datetime.now().isoformat(timespec='seconds')}\n".encode("utf-8")
        parts: list[bytes] = []
        for name, value in (
            ("organization_id", str(ORGANIZATION_ID)),
            ("entity_type", entity_type),
            ("entity_id", str(entity_id)),
        ):
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8"))
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file_name}\"\r\n"
            f"Content-Type: {mimetypes.guess_type(file_name)[0] or 'text/plain'}\r\n\r\n".encode("utf-8")
            + content
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-CSRF-Token": self.csrf,
            "Cookie": self._cookie_header(),
        }
        request = urllib.request.Request(
            self._url("/api/v1/data-exchange/attachments"), data=b"".join(parts), method="POST", headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                self._store_cookies(response)
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            parsed = json.loads(error.read().decode("utf-8") or "{}")
            raise ApiError(error.code, str(parsed.get("code")), str(parsed.get("message"))) from None
        return int(payload["data"]["attachment"]["id"])
