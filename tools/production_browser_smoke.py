"""Public UI smoke; credentials are read from stdin and never saved."""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    credentials = json.load(sys.stdin)
    output = Path('test-results')
    output.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(type(error).__name__))
            page.goto('https://23331.cloud/adp/')
            page.wait_for_load_state('networkidle')
            page.locator('input').first.fill(credentials['identifier'])
            page.locator('input[type="password"]').fill(credentials['password'])
            credentials.clear()
            page.get_by_role('button', name='登录', exact=True).last.click()
            page.wait_for_url('**/workbench', timeout=30000)
            page.wait_for_load_state('networkidle')
            print(json.dumps({'stage': 'browser_login', 'status': 'PASS', 'path': '/workbench'}))
            page.locator('button').filter(has_text='塘小助').click()
            page.get_by_placeholder('例如：查询我有权限查看的鱼塘').fill('查询我当前账号有哪些权限')
            with page.expect_response(lambda response: '/agent/turn/stream' in response.url, timeout=150000) as received:
                page.locator('button').filter(has_text='发送').click()
            response = received.value
            chunks = [json.loads(line) for line in response.text().splitlines() if line.strip()]
            assert response.status == 200
            assert not any(chunk.get('type') == 'error' for chunk in chunks)
            assert any(chunk.get('type') == 'result' and chunk.get('data', {}).get('message') for chunk in chunks)
            assert any(chunk.get('tool') == 'adp_query' for chunk in chunks)
            print(json.dumps({'stage': 'browser_agent_read', 'status': 'PASS', 'tool': 'adp_query'}))
            page.screenshot(path=str(output / 'production-agent-read.png'), full_page=True)
            assert not errors, errors
        finally:
            browser.close()


if __name__ == '__main__':
    main()
