"""Generate a realistic, deliberately messy multi-subsidiary CRM extract.

All companies and people are fictional. Anomalies (duplicates, missing values,
inconsistent formats, invalid emails/SIRET, future dates) are injected on purpose
so that the quality pipeline has something to find and fix.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd

SUBSIDIARIES = ["PLV Paris", "Print Lyon", "Vitrines Milano", "Digital London", "Events Dubai"]
SEGMENTS = ["Haute couture", "Joaillerie", "Parfums & cosmétiques", "Horlogerie", "Maroquinerie", "Vins & spiritueux"]

COMPANY_ROOTS = [
    "Maison Aurèle", "Atelier Solenne", "Bijoux Castellane", "Parfums d'Orsay Lune", "Horlogerie Vasseur",
    "Maroquinerie Belcourt", "Domaine Saint-Alban", "Maison Ophélie", "Cristal Montaigne", "Studio Elara",
    "Maison Valmont Rive", "Atelier Noor", "Joaillerie Iskander", "Parfums Céleste", "Maison Héloïse",
    "Couture Ardent", "Brume de Grasse", "Atelier Lisière", "Maison Corbel", "Lumen Paris",
    "Orfèvrerie Delmas", "Maison Sarrazin", "Atelier Nacré", "Cuirs Fontvieille", "Maison Albane",
    "Esprit Riviera", "Galerie Mirabeau", "Maison Ysolde", "Atelier Saphir", "Parfums Ombrelle",
]
LEGAL_FORMS = ["", " SAS", " SA", " SARL", " Ltd", " S.A.S."]
FIRST = ["Camille", "Léa", "Inès", "Sofia", "Yasmine", "Claire", "Julien", "Hugo", "Karim", "Thomas",
         "Amira", "Chloé", "Nora", "Lucas", "Mehdi", "Sarah", "Emma", "Adam", "Louise", "Rayan"]
LAST = ["Martin", "Bernard", "Haddad", "Rossi", "Dubois", "Benali", "Moreau", "Laurent", "Garcia",
        "Lefèvre", "Mansouri", "Roux", "Fontaine", "Girard", "Chevalier", "Bonnet", "Meyer", "Khelifi"]
CITIES = {"FR": ["Paris", "Lyon", "Grasse", "Bordeaux"], "IT": ["Milano", "Firenze"],
          "GB": ["London"], "AE": ["Dubai"], "CH": ["Genève"]}
COUNTRY_VARIANTS = {"FR": ["FR", "France", "france", "FRA", " France "], "IT": ["IT", "Italie", "Italy"],
                    "GB": ["GB", "UK", "Royaume-Uni", "United Kingdom"], "AE": ["AE", "UAE", "Émirats arabes unis"],
                    "CH": ["CH", "Suisse", "Switzerland"]}
ACCENTS = str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc")
PHONE_PREFIX = {"FR": "33", "IT": "39", "GB": "44", "AE": "971", "CH": "41"}


def _siret(rng: random.Random) -> str:
    """Build a 14-digit SIRET that passes the Luhn check."""
    digits = [rng.randint(0, 9) for _ in range(13)]
    for check in range(10):
        candidate = digits + [check]
        if _luhn_ok("".join(map(str, candidate))):
            return "".join(map(str, candidate))
    raise RuntimeError("unreachable")


def _luhn_ok(number: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _phone(rng: random.Random, country: str) -> str:
    national = "".join(str(rng.randint(0, 9)) for _ in range(8))
    lead = rng.choice("67") if country == "FR" else str(rng.randint(1, 9))
    pref = PHONE_PREFIX[country]
    style = rng.randint(0, 3)
    if style == 0:
        return f"+{pref} {lead} {national[:2]} {national[2:4]} {national[4:6]} {national[6:]}"
    if style == 1 and country == "FR":
        return f"0{lead}.{national[:2]}.{national[2:4]}.{national[4:6]}.{national[6:]}"
    if style == 2:
        return f"00{pref}{lead}{national}"
    return f"+{pref}{lead}{national}"


def _date_str(rng: random.Random, d: date) -> str:
    fmt = rng.choice(["%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"])
    return d.strftime(fmt)


def generate(n_accounts: int = 400, seed: int = 42, today: date = date(2026, 11, 24)) -> pd.DataFrame:
    rng = random.Random(seed)
    companies = []
    for root in COMPANY_ROOTS:
        country = rng.choices(list(CITIES), weights=[60, 12, 10, 10, 8])[0]
        companies.append({
            "root": root, "country": country, "city": rng.choice(CITIES[country]),
            "segment": rng.choice(SEGMENTS), "siret": _siret(rng) if country == "FR" else "",
        })

    rows = []
    for i in range(n_accounts):
        c = rng.choice(companies)
        first, last = rng.choice(FIRST), rng.choice(LAST)
        domain = c["root"].lower().replace("'", "").replace(" ", "")
        domain = domain.translate(ACCENTS) + ".com"
        last_contact = today - timedelta(days=rng.randint(1, 900))
        rows.append({
            "record_id": f"R{i + 1:05d}",
            "subsidiary": rng.choice(SUBSIDIARIES),
            "account_type": rng.choices(["Client", "Prospect"], weights=[40, 60])[0],
            "company_name": c["root"] + rng.choice(LEGAL_FORMS),
            "segment": c["segment"],
            "contact_first_name": first,
            "contact_last_name": last,
            "email": f"{first}.{last}@{domain}".lower().translate(ACCENTS),
            "phone": _phone(rng, c["country"]),
            "country": rng.choice(COUNTRY_VARIANTS[c["country"]]),
            "city": c["city"],
            "siret": c["siret"],
            "annual_revenue_eur": rng.choice([None, rng.randint(2, 900) * 100_000]),
            "last_contact_date": _date_str(rng, last_contact),
        })
    df = pd.DataFrame(rows)

    # --- inject anomalies -------------------------------------------------
    idx = list(df.index)
    rng.shuffle(idx)
    cursor = 0

    def take(k: int) -> list[int]:
        nonlocal cursor
        out = idx[cursor:cursor + k]
        cursor += k
        return out

    # same contact entered by another subsidiary, with typos / case changes
    dup_src = take(45)
    dups = df.loc[dup_src].copy()
    for j, (k, row) in enumerate(dups.iterrows()):
        variant = j % 4
        if variant == 0:
            dups.at[k, "company_name"] = row["company_name"].upper()
        elif variant == 1:
            dups.at[k, "email"] = "  " + row["email"].upper() + " "
        elif variant == 2:
            name = row["company_name"]
            pos = rng.randint(1, max(1, len(name) - 2))
            dups.at[k, "company_name"] = name[:pos] + name[pos + 1:]  # missing letter
        else:
            dups.at[k, "contact_last_name"] = row["contact_last_name"].upper()
            dups.at[k, "phone"] = _phone(rng, "FR") if row["country"] in COUNTRY_VARIANTS["FR"] else row["phone"]
        dups.at[k, "subsidiary"] = rng.choice([s for s in SUBSIDIARIES if s != row["subsidiary"]])
    dups["record_id"] = [f"R{n_accounts + j + 1:05d}" for j in range(len(dups))]
    df = pd.concat([df, dups], ignore_index=True)

    for k in take(30):
        df.at[k, "email"] = None
    for k in take(15):
        e = df.at[k, "email"]
        df.at[k, "email"] = rng.choice([e.replace("@", ""), e.replace(".com", ""), e.replace("@", "@@")])
    for k in take(25):
        df.at[k, "phone"] = None
    for k in take(10):
        df.at[k, "phone"] = "0" + str(rng.randint(100, 9999))
    for k in take(20):
        df.at[k, "segment"] = None
    for k in take(12):
        df.at[k, "country"] = None
    for k in take(10):
        if df.at[k, "siret"]:
            s = df.at[k, "siret"]
            df.at[k, "siret"] = s[:-1] + str((int(s[-1]) + 1) % 10)
    for k in take(6):
        df.at[k, "last_contact_date"] = (today + timedelta(days=rng.randint(30, 400))).strftime("%Y-%m-%d")
    for k in take(8):
        df.at[k, "contact_first_name"] = " " + df.at[k, "contact_first_name"].lower() + "  "

    return df.sample(frac=1, random_state=seed).reset_index(drop=True)
