from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    artifact_dir = Path('test-artifacts')
    artifact_dir.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
        page.on('response', lambda response: errors.append(f'{response.status} {response.url}') if response.status >= 400 else None)

        page.goto('http://127.0.0.1:5173/workbench', wait_until='domcontentloaded')
        page.wait_for_selector('[data-testid="kpi-ponds"]', timeout=10000)
        assert page.get_by_test_id('kpi-ponds').inner_text().startswith('塘口总数')
        page.screenshot(path=str(artifact_dir / 'workbench.png'), full_page=True)

        page.goto('http://127.0.0.1:5173/ponds', wait_until='domcontentloaded')
        page.get_by_text('东港一号塘').wait_for(timeout=10000)
        page.get_by_test_id('pond-search').fill('南湾')
        assert page.get_by_text('南湾育苗塘').is_visible()
        assert not page.get_by_text('东港一号塘').is_visible()
        page.screenshot(path=str(artifact_dir / 'ponds.png'), full_page=True)

        page.goto('http://127.0.0.1:5173/batches', wait_until='domcontentloaded')
        page.get_by_text('ADP-2026-001').wait_for(timeout=10000)
        page.get_by_test_id('batch-status').select_option(label='待结算')
        assert page.get_by_text('ADP-2026-003').is_visible()
        assert not page.get_by_text('ADP-2026-001').is_visible()
        page.locator('a').filter(has_text='ADP-2026-003').click(timeout=10000)
        page.wait_for_url('**/batches/203', timeout=10000)
        page.get_by_text('存量口径').wait_for(timeout=10000)
        assert page.get_by_text('编辑批次').is_visible()
        page.goto('http://127.0.0.1:5173/batches/204', wait_until='domcontentloaded')
        page.get_by_text('存量口径').wait_for(timeout=10000)
        assert page.get_by_text('只读模式').is_visible()
        page.screenshot(path=str(artifact_dir / 'batch-detail.png'), full_page=True)

        browser.close()
    if errors:
        raise AssertionError('Browser errors: ' + ' | '.join(errors))


if __name__ == '__main__':
    main()
