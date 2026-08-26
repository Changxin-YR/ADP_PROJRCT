from pathlib import Path

from tools.audit_source import audit_file, find_flask_blueprints, find_vue_routes, scan_tree


def test_audit_flags_static_business_sources(tmp_path: Path) -> None:
    page = tmp_path / "Page.vue"
    page.write_text("import { rows } from '../dataset/dataset'", encoding="utf-8")

    assert audit_file(page) == {"static_business_source"}


def test_audit_flags_inline_business_fallbacks(tmp_path: Path) -> None:
    page = tmp_path / "RegisterPage.vue"
    page.write_text("const FALLBACK_OPTIONS = { roles: [{ id: 1 }] }", encoding="utf-8")

    assert audit_file(page) == {"static_business_source"}


def test_audit_flags_handwritten_files_over_300_lines(tmp_path: Path) -> None:
    page = tmp_path / "Page.vue"
    page.write_text("\n".join(["x"] * 301), encoding="utf-8")

    assert "over_300_lines" in audit_file(page)


def test_scan_records_line_and_matching_text(tmp_path: Path) -> None:
    page = tmp_path / "QueuePage.vue"
    page.write_text("const ok = true\nlocalStorage.setItem('queue', '[]')", encoding="utf-8")

    finding = scan_tree(tmp_path).findings[0]

    assert finding.path == "QueuePage.vue"
    assert finding.line == 2
    assert finding.category == "browser_business_storage"
    assert finding.text == "localStorage.setItem('queue', '[]')"


def test_route_and_blueprint_maps_are_complete(tmp_path: Path) -> None:
    router = tmp_path / "router.ts"
    router.write_text(
        "{ path: '/ponds', component: () => import('./layers/product/ponds/PondListPage.vue') }",
        encoding="utf-8",
    )
    app = tmp_path / "app.py"
    app.write_text(
        "from backend.layers.product.cost.routes import create_cost_blueprint\n"
        "app.register_blueprint(create_cost_blueprint(settings, store))\n",
        encoding="utf-8",
    )

    assert find_vue_routes(router) == {
        "/ponds": "./layers/product/ponds/PondListPage.vue"
    }
    assert find_flask_blueprints(app) == {
        "create_cost_blueprint": "backend.layers.product.cost.routes"
    }


def test_strict_source_rules_only_scan_production_files(tmp_path: Path) -> None:
    source = tmp_path / "frontend/src/Page.vue"
    test_file = tmp_path / "frontend/tests/page.spec.ts"
    tool = tmp_path / "tools/audit.py"
    for path in (source, test_file, tool):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("const marker = 'localStorage'", encoding="utf-8")

    findings = scan_tree(tmp_path).findings

    assert [(item.path, item.category) for item in findings] == [
        ("frontend/src/Page.vue", "browser_business_storage")
    ]
