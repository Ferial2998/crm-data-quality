from datetime import date

from crm_quality.standardize import (company_key, display_company, normalize_country, normalize_email,
                                     normalize_phone, parse_date, title_name)


def test_company_key_ignores_case_accents_and_legal_form():
    assert company_key("MAISON AURÈLE SAS") == company_key("Maison Aurele") == "maison aurele"
    assert company_key("Atelier Noor S.A.S.") == "atelier noor"


def test_display_company_is_readable():
    assert display_company("MAISON AURÈLE SAS") == "Maison Aurèle"
    assert display_company("  Atelier Noor   Ltd ") == "Atelier Noor"


def test_names_and_email():
    assert title_name("  camille  ") == "Camille"
    assert title_name("LEFÈVRE") == "Lefèvre"
    assert normalize_email("  Lea.Martin@Maison.COM ") == "lea.martin@maison.com"


def test_country_variants():
    for value in ["FR", "france", " France ", "FRA"]:
        assert normalize_country(value) == "FR"
    assert normalize_country("Royaume-Uni") == "GB"
    assert normalize_country("Émirats arabes unis") == "AE"
    assert normalize_country("Atlantis") is None


def test_phone_to_e164():
    assert normalize_phone("06.12.34.56.78", "FR") == "+33612345678"
    assert normalize_phone("+33 6 12 34 56 78", "FR") == "+33612345678"
    assert normalize_phone("0033612345678", None) == "+33612345678"
    assert normalize_phone("01234", "FR") is None


def test_dates_in_several_formats():
    assert parse_date("2026-03-01") == parse_date("01/03/2026") == parse_date("01-03-2026") == date(2026, 3, 1)
    assert parse_date("hier") is None
