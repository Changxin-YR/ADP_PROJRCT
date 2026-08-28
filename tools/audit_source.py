from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


RULES = {
    "static_business_source": ("dataset/dataset", "workbench.mock", "FALLBACK_OPTIONS", "const FALLBACK:"),
    "browser_business_storage": ("localStorage", "sessionStorage"),
    "dangerous_delete_copy": ("删除", "delete"),
}
HANDWRITTEN_SUFFIXES = {".py", ".ts", ".vue", ".sql"}
IGNORED_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "playwright-report",
    "test-results",
}
STRICT_CATEGORIES = {
    "static_business_source",
    "browser_business_storage",
    "over_300_lines",
}
PRODUCTION_ONLY_RULES = {"static_business_source", "browser_business_storage"}
APPROVED_BROWSER_STORAGE = {"frontend/src/layers/common/ui/offlineDraft.ts"}


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    category: str
    text: str


@dataclass(frozen=True)
class AuditReport:
    findings: tuple[Finding, ...]
    vue_routes: dict[str, str]
    flask_blueprints: dict[str, str]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def audit_file(path: Path) -> set[str]:
    text = _read(path)
    categories = {
        category
        for category, needles in RULES.items()
        if any(needle.lower() in text.lower() for needle in needles)
    }
    if path.suffix.lower() in HANDWRITTEN_SUFFIXES and len(text.splitlines()) > 300:
        categories.add("over_300_lines")
    return categories


def find_vue_routes(path: Path) -> dict[str, str]:
    pattern = re.compile(
        r"path\s*:\s*['\"]([^'\"]+)['\"][^\n]*?import\(\s*['\"]([^'\"]+\.vue)['\"]\s*\)"
    )
    return dict(pattern.findall(_read(path)))


def find_flask_blueprints(path: Path) -> dict[str, str]:
    text = _read(path)
    imports = dict(
        (factory, module)
        for module, factory in re.findall(
            r"^from\s+([\w.]+)\s+import\s+(create_\w+_blueprint)\s*$",
            text,
            re.MULTILINE,
        )
    )
    registered = set(re.findall(r"register_blueprint\(\s*(create_\w+_blueprint)\(", text))
    return {factory: imports[factory] for factory in sorted(registered) if factory in imports}


def _source_files(root: Path, paths: Iterable[str] | None) -> list[Path]:
    candidates: list[Path] = []
    for requested in paths or ["."]:
        target = (root / requested).resolve()
        if target.is_file():
            candidates.append(target)
        elif target.is_dir():
            candidates.extend(target.rglob("*"))
    return sorted(
        path
        for path in set(candidates)
        if path.is_file()
        and path.suffix.lower() in HANDWRITTEN_SUFFIXES
        and not any(part in IGNORED_DIRS for part in path.parts)
    )


def scan_tree(root: Path, paths: Iterable[str] | None = None) -> AuditReport:
    root = root.resolve()
    findings: list[Finding] = []
    for path in _source_files(root, paths):
        text = _read(path)
        relative = path.relative_to(root).as_posix()
        production = not relative.startswith(("backend/tests/", "frontend/tests/", "tools/"))
        lines = text.splitlines()
        if len(lines) > 300 and production:
            findings.append(Finding(relative, 301, "over_300_lines", f"{len(lines)} lines"))
        for line_no, line in enumerate(lines, 1):
            lowered = line.lower()
            for category, needles in RULES.items():
                if category in PRODUCTION_ONLY_RULES and not production:
                    continue
                if category == "browser_business_storage" and relative in APPROVED_BROWSER_STORAGE:
                    continue
                if any(needle.lower() in lowered for needle in needles):
                    findings.append(Finding(relative, line_no, category, line.strip()))
    router = root / "frontend" / "src" / "router.ts"
    app = root / "backend" / "app.py"
    return AuditReport(
        findings=tuple(sorted(findings)),
        vue_routes=find_vue_routes(router) if router.exists() else {},
        flask_blueprints=find_flask_blueprints(app) if app.exists() else {},
    )


def _escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_markdown(report: AuditReport, destination: Path) -> None:
    counts = Counter(item.category for item in report.findings)
    lines = [
        "# Enterprise Source Audit",
        "",
        "## Summary",
        "",
        "| Category | Count |",
        "| --- | ---: |",
        *[f"| {name} | {count} |" for name, count in sorted(counts.items())],
        "",
        "## Findings",
        "",
        "| File | Line | Category | Match |",
        "| --- | ---: | --- | --- |",
        *[
            f"| {_escape(item.path)} | {item.line} | {item.category} | {_escape(item.text)} |"
            for item in report.findings
        ],
        "",
        "## Vue Routes",
        "",
        "| Path | Page |",
        "| --- | --- |",
        *[f"| {_escape(route)} | {_escape(page)} |" for route, page in report.vue_routes.items()],
        "",
        "## Flask Blueprints",
        "",
        "| Factory | Module |",
        "| --- | --- |",
        *[
            f"| {_escape(factory)} | {_escape(module)} |"
            for factory, module in report.flask_blueprints.items()
        ],
        "",
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ADP production source contracts")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--paths", nargs="*")
    parser.add_argument("--fail-category", action="append", default=[])
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = scan_tree(args.root, args.paths)
    if args.markdown:
        destination = args.markdown
        if not destination.is_absolute():
            destination = args.root / destination
        write_markdown(report, destination)
    counts = Counter(item.category for item in report.findings)
    print(
        f"files_findings={len(report.findings)} vue_routes={len(report.vue_routes)} "
        f"flask_blueprints={len(report.flask_blueprints)} categories={dict(sorted(counts.items()))}"
    )
    failed = set(args.fail_category)
    if args.strict:
        failed.update(STRICT_CATEGORIES)
    return int(any(item.category in failed for item in report.findings))


if __name__ == "__main__":
    raise SystemExit(main())
