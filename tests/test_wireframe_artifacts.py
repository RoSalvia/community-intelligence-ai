from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIREFRAME_DIR = ROOT / "docs" / "wireframes"
EXPECTED_PREVIEWS = {
    "overview.svg",
    "campaigns.svg",
    "communities.svg",
    "behaviors.svg",
    "response-patterns.svg",
    "metric-lab.svg",
    "evidence.svg",
}


def test_task_5_wireframe_package_is_complete() -> None:
    assert (WIREFRAME_DIR / "README.md").is_file()
    assert (WIREFRAME_DIR / "LOW_FIDELITY_WIREFRAME.md").is_file()
    assert (WIREFRAME_DIR / "community-intelligence-wireframe.html").is_file()

    previews = {path.name for path in WIREFRAME_DIR.glob("*.svg")}
    assert previews == EXPECTED_PREVIEWS


def test_wireframe_documents_preserve_product_boundaries() -> None:
    specification = (WIREFRAME_DIR / "LOW_FIDELITY_WIREFRAME.md").read_text()
    html = (WIREFRAME_DIR / "community-intelligence-wireframe.html").read_text()

    for boundary in (
        "Message count is context, not quality",
        "Not implemented",
        "Human review",
        "association, not causation",
    ):
        assert boundary.casefold() in specification.casefold()

    for page_name in (
        "Overview",
        "Campaigns",
        "Communities",
        "Behaviors",
        "Response Patterns",
        "Metric Lab",
        "Evidence",
    ):
        assert f'data-page="{page_name}"' in html
