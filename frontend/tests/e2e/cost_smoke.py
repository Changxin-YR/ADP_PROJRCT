from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    artifact_dir = Path("test-artifacts")
    artifact_dir.mkdir(exist_ok=True)
    browser_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda error: browser_errors.append(str(error)))

        page.goto("http://127.0.0.1:5173/auth/login", wait_until="networkidle")
        page.locator("#identifier").fill("admin")
        page.locator("#password").fill("FarmPass9!")
        page.locator("form").get_by_role("button", name="登录", exact=True).click()
        page.wait_for_url("**/workbench")
        page.on("console", lambda message: browser_errors.append(message.text) if message.type == "error" else None)

        page.goto("http://127.0.0.1:5173/cost/structure", wait_until="networkidle")
        assert "672,000.00" in page.get_by_test_id("cost-total").inner_text()
        assert "待接入产量" in page.get_by_test_id("cost-unit-cost").inner_text()
        page.get_by_test_id("cost-row-feed").click()
        page.get_by_test_id("cost-entry-drawer").get_by_text("LEGACY-INIT-2026").wait_for()
        assert "LEGACY-INIT-2026" in page.get_by_test_id("cost-entry-drawer").inner_text()
        page.get_by_role("button", name="关闭来源明细").click()
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(artifact_dir / "cost-accounting.png"))

        browser.close()

    if browser_errors:
        raise AssertionError("Browser errors: " + " | ".join(browser_errors))


if __name__ == "__main__":
    main()
