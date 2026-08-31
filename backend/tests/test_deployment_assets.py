from __future__ import annotations

from io import BytesIO
from pathlib import Path
import subprocess
from tarfile import open as open_tar


def test_release_archive_keeps_deployment_script_lf_only() -> None:
    root = Path(__file__).resolve().parents[2]
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", "deploy/deploy-blue-green.sh"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout

    with open_tar(fileobj=BytesIO(archive)) as tar:
        script = tar.extractfile("deploy/deploy-blue-green.sh")
        assert script is not None
        assert b"\r\n" not in script.read()
