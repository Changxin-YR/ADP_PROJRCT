from pathlib import Path
import json

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def operation_count() -> int:
    spec = json.loads((ROOT / "api-docs" / "openapi.json").read_text(encoding="utf-8"))
    return sum(len(methods) for methods in spec.get("paths", {}).values())


def main() -> None:
    console_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.goto("http://127.0.0.1:4174", wait_until="networkidle")
        assert page.locator("h1").inner_text() == "ADP 企业业务接口"
        expected_count = str(operation_count())
        assert page.locator("#operation-count").inner_text() == expected_count
        page.locator("#api-search").fill("verify")
        assert page.locator("article.operation").count() > 0
        assert not console_errors
        page.locator("#api-search").fill("")
        page.screenshot(path=str(ROOT / "docs" / "audits" / "api-docs-desktop.png"), full_page=True)
        browser.close()
    print(f"API docs smoke passed: {operation_count()} operations, search and console clean")


if __name__ == "__main__":
    main()
