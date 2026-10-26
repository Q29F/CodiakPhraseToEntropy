"""Runtime and authentication checks for the optional notebook container."""

from __future__ import annotations

import csv
import http.client
import importlib
import importlib.metadata as metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def check_dependencies(lock_paths: list[Path]) -> None:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    import pip

    expected = {}
    for path in lock_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line[0].isspace() or line.startswith("#"):
                continue
            requirement = Requirement(line.rstrip("\\").strip())
            if requirement.marker is None or requirement.marker.evaluate():
                pins = list(requirement.specifier)
                assert len(pins) == 1 and pins[0].operator == "==", "Unpinned dependency"
                expected[canonicalize_name(requirement.name)] = pins[0].version
    actual = {}
    for distribution in metadata.distributions():
        name = canonicalize_name(distribution.metadata["Name"])
        assert name not in actual, "Duplicate package metadata"
        actual[name] = distribution.version
    assert actual == expected, "Installed packages differ from the applicable locks"
    assert pip.__version__ == metadata.version("pip") == "26.2.2", "Installer mismatch"
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True, timeout=30)


def check_cli() -> None:
    with tempfile.TemporaryDirectory() as directory:
        destination = Path(directory, "entropy-export.csv")
        result = subprocess.run(
            [sys.executable, "simulationV2.py", "--phrase", "abab", "--export", str(destination)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        with destination.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == ["phase", "expression"], "Unexpected CLI export columns"
            rows = list(reader)
        assert len(rows) == 1, "Unexpected CLI export row count"
        assert math.isclose(float(rows[0]["phase"]), math.pi / 2, abs_tol=1e-12)
        assert rows[0]["expression"] == result.stdout.strip(), "CLI output and export disagree"


def check_runtime() -> None:
    assert sys.version_info[:3] == (3, 12, 16), "Unexpected Python version"
    assert sys.prefix == "/opt/codiak", "Application virtual environment is not active"
    assert os.getuid() == os.getgid() == 1000, "Container must run as its non-root user"
    for name in (
        "ssl", "_hashlib", "sqlite3", "bz2", "lzma", "zlib", "ctypes", "readline", "dbm.gnu",
    ):
        importlib.import_module(name)
    import pyexpat

    assert pyexpat.version_info >= (2, 9, 0), "Unexpected Expat version"
    assert Path("CodiakPhraseToEntropySimulationV2.ipynb").is_file(), "Notebook is missing"
    check_dependencies([Path("/tmp/requirements-notebook.txt"), Path("/tmp/requirements-installer.txt")])
    check_cli()
    print("Container runtime, locked dependencies, and CLI export passed.")


def request(port: int, path: str, token: str | None = None) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = "token " + token
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        body = response.read(1_048_577)
        assert len(body) <= 1_048_576, "Unexpected notebook response size"
        return response.status, body
    finally:
        connection.close()


def check_notebook(port: int = 8888) -> None:
    from jupyter_server.serverapp import list_running_servers

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        servers = [server for server in list_running_servers() if server.get("port") == port]
        if servers:
            assert len(servers) == 1, "Unexpected notebook server count"
            token = servers[0].get("token")
            assert isinstance(token, str) and token, "Default token authentication is missing"
            assert Path(servers[0]["root_dir"]) == Path.cwd(), "Unexpected notebook root"
            try:
                status, _ = request(port, "/api/status")
            except (OSError, http.client.HTTPException):
                time.sleep(0.2)
                continue
            assert status in (401, 403), "Unauthenticated notebook API access was accepted"
            status, body = request(port, "/api/status", token)
            assert status == 200, "Authenticated notebook API access failed"
            assert json.loads(body)["kernels"] == 0, "Unexpected active notebook kernel"
            status, body = request(port, "/lab", token)
            assert status == 200 and b"jupyter-config-data" in body, "JupyterLab did not render"
            print("Default JupyterLab startup and token authentication passed.")
            return
        time.sleep(0.2)
    raise AssertionError("Notebook startup did not complete within 60 seconds")


if __name__ == "__main__":
    if sys.argv[1:] == ["--notebook"]:
        check_notebook()
    elif not sys.argv[1:]:
        check_runtime()
    else:
        raise SystemExit("Usage: python tests/container.py [--notebook]")
