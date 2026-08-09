from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_project_documentation_has_no_interview_or_portfolio_positioning():
    forbidden = (
        "portfolio",
        "interview",
        "pet project",
        "for interview",
        "interview positioning",
        "portfolio project",
        "интервью",
    )
    documents = [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
    violations: list[str] = []
    for document in documents:
        content = document.read_text(encoding="utf-8").lower()
        for phrase in forbidden:
            if phrase in content:
                violations.append(f"{document.relative_to(ROOT)}: {phrase}")
    assert violations == []


def test_public_frontend_has_no_direct_partner_links():
    workspace = (ROOT / "frontend/app/components/OfferWorkspace.tsx").read_text(
        encoding="utf-8"
    )
    assert "v1/offers/${offer.offer_id}/click" in workspace
    assert 'href={offer.' not in workspace
    assert "affiliate_url_template" not in workspace
    assert "commission_amount" not in workspace
