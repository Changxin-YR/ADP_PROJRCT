from pathlib import Path


def test_reference_seed_does_not_regrant_account_administration_to_breed_manager() -> None:
    seed = Path("database/seed_reference.sql").read_text(encoding="utf-8")

    assert "r.code = 'breed_manager' AND p.code IN ('auth.review', 'auth.user.manage', 'workbench.enter')" not in seed


def test_reference_seed_explicitly_keeps_account_administration_with_super_admin() -> None:
    seed = Path("database/seed_reference.sql").read_text(encoding="utf-8")

    assert "r.code = 'super_admin' AND p.code IN ('auth.review', 'auth.user.manage', 'auth.session.view', 'auth.role.manage', 'workbench.enter')" in seed
