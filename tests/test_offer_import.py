import csv
import json

import pytest
import yaml
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import cli
from src.core.config import settings
from src.db.base import Base
from src.db.models import BankOffer
from src.offers.importer import (
    OfferImportValidationError,
    export_offers,
    import_offers,
    load_and_validate_offers,
)


@pytest.fixture()
def offer_session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def valid_offer(**overrides):
    row = {
        "bank_id": "demo-import-bank",
        "product_name": "Imported Cash Offer",
        "product_type": "cash",
        "is_active": True,
        "priority": 55,
        "min_amount": 50_000,
        "max_amount": 500_000,
        "min_term_months": 6,
        "max_term_months": 60,
        "allowed_age_bands": ["22_30", "31_45", "46_60"],
        "allowed_regions": [],
        "allowed_employment_types": ["employee", "self_employed"],
        "allowed_credit_history_bands": ["good", "average", "no_history"],
        "max_pti_band": "high",
        "risk_band_policy": ["low", "medium", "unknown"],
        "advertiser_name": "Demo Import Advertiser",
        "ad_label_text": "Advertising. Imported demo offer.",
        "erid": None,
        "legal_disclaimer": "Preliminary conditions. Final decision is made by the bank.",
        "partner_id": "demo",
        "affiliate_url_template_key": None,
        "commission_type": "none",
        "commission_amount": None,
        "expires_at": None,
    }
    row.update(overrides)
    return row


def write_yaml(path, rows):
    path.write_text(yaml.safe_dump({"offers": rows}, allow_unicode=True), encoding="utf-8")


def write_csv(path, rows):
    prepared = []
    for source in rows:
        row = dict(source)
        for field, value in row.items():
            if isinstance(value, list):
                row[field] = json.dumps(value)
            elif value is None:
                row[field] = ""
        prepared.append(row)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(prepared[0]))
        writer.writeheader()
        writer.writerows(prepared)


@pytest.mark.parametrize("extension,writer", [("yaml", write_yaml), ("csv", write_csv)])
def test_valid_yaml_and_csv_dry_run_write_nothing(
    tmp_path, offer_session_factory, extension, writer
):
    path = tmp_path / f"offers.{extension}"
    writer(path, [valid_offer()])
    with offer_session_factory() as session:
        report = import_offers(session, path, apply=False)
        assert report.mode == "dry_run"
        assert report.rows == 1
        assert session.scalar(select(func.count()).select_from(BankOffer)) == 0


def test_apply_upserts_deterministically_and_stores_no_template_value(
    tmp_path, offer_session_factory
):
    path = tmp_path / "offers.yaml"
    write_yaml(path, [valid_offer()])
    with offer_session_factory() as session:
        first = import_offers(session, path, apply=True)
        second = import_offers(session, path, apply=True)
        offer = session.scalar(select(BankOffer))
        assert first.created == 1
        assert second.unchanged == 1
        assert offer.affiliate_url_template_key is None
        assert offer.affiliate_url_template.startswith("https://example.invalid/")


@pytest.mark.parametrize(
    "overrides",
    [
        {"advertiser_name": ""},
        {"ad_label_text": ""},
        {"min_amount": 500_000, "max_amount": 100_000},
        {"min_term_months": 60, "max_term_months": 12},
        {"partner_id": "future_partner", "affiliate_url_template_key": None},
    ],
)
def test_invalid_offer_is_rejected_without_echoing_values(tmp_path, overrides):
    path = tmp_path / "invalid.yaml"
    write_yaml(path, [valid_offer(**overrides)])
    with pytest.raises(OfferImportValidationError) as exc_info:
        load_and_validate_offers(path)
    assert "Demo Import Advertiser" not in str(exc_info.value)
    assert "Preliminary conditions" not in str(exc_info.value)


def test_duplicate_rows_are_rejected_and_raw_urls_are_forbidden(tmp_path):
    duplicate = tmp_path / "duplicate.yaml"
    write_yaml(duplicate, [valid_offer(), valid_offer()])
    with pytest.raises(OfferImportValidationError, match="Duplicate"):
        load_and_validate_offers(duplicate)
    unsafe = tmp_path / "unsafe.yaml"
    write_yaml(
        unsafe,
        [valid_offer(affiliate_url_template="https://partner.example/?token=private")],
    )
    with pytest.raises(OfferImportValidationError, match="forbidden"):
        load_and_validate_offers(unsafe)


def test_enabled_real_partner_requires_secret_and_template_environment(tmp_path, monkeypatch):
    partners = tmp_path / "partners.yaml"
    partners.write_text(
        yaml.safe_dump(
            {
                "partners": {
                    "real-test": {
                        "adapter": "env_template",
                        "enabled": True,
                        "secret_env": "REAL_TEST_SECRET",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    offers = tmp_path / "real.yaml"
    write_yaml(
        offers,
        [
            valid_offer(
                partner_id="real-test",
                affiliate_url_template_key="REAL_TEST_AFFILIATE_TEMPLATE",
            )
        ],
    )
    monkeypatch.setattr(settings, "partner_config_path", str(partners))
    with pytest.raises(OfferImportValidationError, match="requires configured secret"):
        load_and_validate_offers(offers)
    monkeypatch.setenv("REAL_TEST_SECRET", "runtime-only-secret")
    monkeypatch.setenv(
        "REAL_TEST_AFFILIATE_TEMPLATE",
        "https://partner.example/apply?click_id={click_id}&token=runtime-only",
    )
    rows, _ = load_and_validate_offers(offers)
    assert rows[0].affiliate_url_template_key == "REAL_TEST_AFFILIATE_TEMPLATE"


def test_export_excludes_private_template_values(tmp_path, offer_session_factory):
    source = tmp_path / "offers.yaml"
    destination = tmp_path / "offers_export.csv"
    write_yaml(source, [valid_offer()])
    with offer_session_factory() as session:
        import_offers(session, source, apply=True)
        assert export_offers(session, destination) == 1
    exported = destination.read_text(encoding="utf-8")
    assert "affiliate_url_template," not in exported.splitlines()[0]
    assert "affiliate_url_template_key" in exported.splitlines()[0]
    assert "example.invalid" not in exported


def test_cli_dry_run_never_prints_resolved_template(
    tmp_path, offer_session_factory, monkeypatch, capsys
):
    secret_template = "https://private.example/apply?click_id={click_id}&token=do-not-print"
    monkeypatch.setenv("DEMO_IMPORT_TEMPLATE", secret_template)
    path = tmp_path / "offers.yaml"
    write_yaml(path, [valid_offer(affiliate_url_template_key="DEMO_IMPORT_TEMPLATE")])
    monkeypatch.setattr(cli, "SessionLocal", offer_session_factory)
    cli.main(["import-offers", "--path", str(path), "--dry-run"])
    output = capsys.readouterr().out
    assert "Rows validated: 1" in output
    assert secret_template not in output
    assert "do-not-print" not in output
