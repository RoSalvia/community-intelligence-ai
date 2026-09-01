from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wheel_configuration_includes_the_built_web_product() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["version"] == "0.1.0a0"
    package_data = project["tool"]["setuptools"]["package-data"]
    assert package_data["community_intelligence.web"] == [
        "static/index.html",
        "static/assets/*",
    ]

    static_dir = ROOT / "src" / "community_intelligence" / "web" / "static"
    assert (static_dir / "index.html").is_file()
    assert list((static_dir / "assets").glob("*.js"))
    assert list((static_dir / "assets").glob("*.css"))


def test_github_release_documentation_has_stranger_entrypoints() -> None:
    expected = [
        ROOT / "README.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        ROOT / "THIRD_PARTY_NOTICES.md",
        ROOT / "docs" / "ARCHITECTURE.md",
        ROOT / "docs" / "EVALUATION.md",
        ROOT / "docs" / "METRICS.md",
        ROOT / "docs" / "PRIVACY.md",
        ROOT / "docs" / "PRODUCT_STORY.md",
        ROOT / "docs" / "product" / "PRODUCT_SPEC_CN.md",
        ROOT / "docs" / "release-notes-v0.1.0-alpha.md",
        ROOT / ".github" / "workflows" / "ci.yml",
        ROOT / "scripts" / "verify_release.sh",
    ]
    assert all(path.is_file() for path in expected)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "community-intelligence serve" in readme
    assert "Telegram Desktop" in readme
    assert "Not implemented" in readme
    assert "v0.1.0-alpha" in readme

    for name in ("overview.png", "campaign-intelligence.png", "metric-lab.png"):
        screenshot = ROOT / "docs" / "assets" / name
        content = screenshot.read_bytes()
        assert content.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(content) > 100_000


def test_release_verification_covers_real_import_and_browser_flows() -> None:
    script = (ROOT / "scripts" / "verify_release.sh").read_text(encoding="utf-8")

    assert '"${wheel_command}" import telegram' in script
    assert '"${wheel_command}" analyze' in script
    assert "playwright install chromium" in script
    assert "run test:e2e" in script
