from datetime import date

import pandas as pd

from crm_quality.dedupe import assign_clusters, build_golden_records, canonical_company_names, find_duplicates
from crm_quality.rules import luhn_ok, run_rules
from crm_quality.standardize import standardize

TODAY = date(2026, 11, 24)


def _raw(**overrides):
    base = {
        "record_id": "R1", "subsidiary": "PLV Paris", "account_type": "Client", "company_name": "Maison Aurèle SAS",
        "segment": "Joaillerie", "contact_first_name": "Léa", "contact_last_name": "Martin",
        "email": "lea.martin@maisonaurele.com", "phone": "06 12 34 56 78", "country": "France", "city": "Paris",
        "siret": "73282932000074", "annual_revenue_eur": "1000000", "last_contact_date": "2026-10-01",
    }
    base.update(overrides)
    return base


def test_luhn():
    assert luhn_ok("73282932000074")
    assert not luhn_ok("73282932000075")


def test_clean_record_has_no_issue():
    df = standardize(pd.DataFrame([_raw()]))
    assert run_rules(df, TODAY).empty


def test_rules_catch_anomalies():
    df = standardize(pd.DataFrame([_raw(email="lea.martin@@maison", siret="73282932000075",
                                        last_contact_date="2027-05-01", phone=None)]))
    found = set(run_rules(df, TODAY)["rule"])
    assert {"INVALID_EMAIL", "INVALID_SIRET", "FUTURE_CONTACT_DATE", "MISSING_PHONE"} <= found


def test_duplicates_across_subsidiaries_become_one_golden_record():
    df = standardize(pd.DataFrame([
        _raw(),
        _raw(record_id="R2", subsidiary="Print Lyon", company_name="MAISON AURELE",
             email="  LEA.MARTIN@MAISONAURELE.COM ", segment=None),
        _raw(record_id="R3", contact_first_name="Hugo", contact_last_name="Roux", email="hugo.roux@x.com"),
    ]))
    pairs = find_duplicates(df)
    assert len(pairs) == 1 and pairs.iloc[0]["reason"] == "email identique"
    clusters = assign_clusters(df, pairs)
    golden = build_golden_records(df, clusters, pd.Series([True] * 3))
    assert len(golden) == 2
    lea = golden[golden["contact_last_name"] == "Martin"].iloc[0]
    assert lea["subsidiaries"] == "PLV Paris, Print Lyon"
    assert lea["segment"] == "Joaillerie"


def test_company_typos_are_harmonised():
    df = standardize(pd.DataFrame([_raw(record_id=f"R{i}") for i in range(3)]
                                  + [_raw(record_id="R9", company_name="Maison Aurle")]))
    assert set(canonical_company_names(df)) == {"Maison Aurèle"}
