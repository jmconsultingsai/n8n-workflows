"""
CVR Lead Scraper — Denmark Multi-Sector
========================================
From the JM Consulting YouTube channel — EP3: Pipeline Completo de Leads con IA.

This scraper queries Denmark's official business registry (Datafordeler CVR GraphQL v2)
using a multi-phase approach:

  Phase 1 — CVR_Branche: get CVREnhedsIds by branchekode
  Phase 2 — batch enrich (name, address, email, phone, employees, CVR number) per 100 IDs
  Phase 3 — join in Python, filter by employee count, export CSV

ADAPTING TO YOUR COUNTRY
--------------------------
This script is designed for Denmark's Datafordeler API. If you are in a different country,
you can paste both this script and sync_leads.py into Claude (or any LLM) and ask it to
adapt them for your country's business registry API. Example prompt:

  "I want to scrape business leads from [country]'s public registry.
   The API is at [URL] and uses [REST/GraphQL/SOAP].
   Adapt this scrape_cvr.py script to query that API instead of Datafordeler.
   Keep the same CSV output format (cvr, navn, branche, ansatte, adresse, postnr, by,
   telefon, email, virk_url) and the same Phase 1 / Phase 2 / Phase 3 structure."

Architecture note: the Datafordeler API is a relational flat model (not nested).
Each entity type is queried separately and joined by CVREnhedsId.

Schema notes (v2 live — verified 2026-07-17):
  - Filtering uses `where:` (not `filter:`).
  - Results come as connection pattern: { nodes: [...] } or { edges: [{ node }] }.
  - Each query requires at least one @filterRequirement field.
  - CVR_Telefonnummer.vaerdi is the phone number field (no "kontaktoplysning" field exists).
  - CVR_Beskaeftigelse has no virkningTil — use datoTil for recency; active filter not applicable.
  - CVR_Virksomhed.id == CVREnhedsId from other tables; CVRNummer is the public 8-digit number.
  - DafStringOperationFilterInput.in has MaxListSize: 100 — keep PAGE_SIZE at 100.
  - virkningTil is NOT in CVR_BrancheFilterInput — active-record filtering is done client-side.

Requirements:
    pip install requests python-dotenv pyyaml

Setup:
    1. Copy .env.example to .env and fill in your credentials.
    2. Get your Datafordeler account at: https://datafordeler.dk/
       Then: My IT-systems → Create new IT-system → Subscribe to CVR service
       Choose OAuth2 (recommended) or API Key.
    3. The sectors to scrape are defined in sectors.yaml — edit that file to
       add or remove industry codes for your use case.

Output:
    leads.csv (or whatever OUTPUT_FILE is set to in .env)

Schema inspection:
    python scrape_cvr.py --schema

Sector selection:
    python scrape_cvr.py                              # all sectors
    python scrape_cvr.py --sector byggeri             # construction only
    python scrape_cvr.py --sector fast_ejendom --sector forsikring
"""

import io
import os
import csv
import sys
import time
import yaml
import requests
from pathlib import Path
from dotenv import load_dotenv

# Windows cp1252 fix — must be before any print() calls
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

# Authentication — OAuth2 is recommended (token auto-refreshes every 60 min).
# API Key is the simpler fallback if OAuth2 is not set up.
OAUTH_CLIENT_ID     = os.getenv("DATAFORDELER_OAUTH_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.getenv("DATAFORDELER_OAUTH_CLIENT_SECRET", "")
API_KEY             = os.getenv("DATAFORDELER_API_KEY", "")

GRAPHQL_URL = os.getenv("CVR_GRAPHQL_URL", "https://graphql.datafordeler.dk/CVR/v2")
SCHEMA_URL  = os.getenv("CVR_GRAPHQL_SCHEMA_URL", "https://graphql.datafordeler.dk/CVR/v2/schema")
OAUTH_TOKEN_URL = "https://auth.datafordeler.dk/realms/distribution/protocol/openid-connect/token"

# Scraper config — override via .env
MIN_EMPLOYEES = int(os.getenv("MIN_EMPLOYEES", "5"))
MAX_EMPLOYEES = int(os.getenv("MAX_EMPLOYEES", "200"))
OUTPUT_FILE   = os.getenv("OUTPUT_FILE", "leads.csv")

PAGE_SIZE = 100   # max for `in` filter per DafStringOperationFilterInput.MaxListSize

# OAuth token state (module-level, refreshed automatically)
_oauth_token: str = ""
_oauth_expires: float = 0

# ── Load sectors from YAML ────────────────────────────────────────────────────

_SECTORS_FILE = Path(__file__).parent / "sectors.yaml"

def _load_sectors() -> dict:
    """Load sectors dict from sectors.yaml."""
    if not _SECTORS_FILE.exists():
        print(f"ERROR: sectors.yaml not found at {_SECTORS_FILE}")
        print("  Create it or copy sectors.yaml.example from the repo.")
        sys.exit(1)
    with open(_SECTORS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # Normalize: codes must be strings (YAML may parse them as ints)
    for key, sector in data.items():
        sector["codes"] = [str(c) for c in sector.get("codes", [])]
    return data

SECTORS: dict = _load_sectors()

# ── Runtime flags ─────────────────────────────────────────────────────────────

DEBUG     = "--debug" in sys.argv
USE_OAUTH = bool(OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET)

# ── GraphQL queries ───────────────────────────────────────────────────────────
# All queries use `where:` (v2 schema). Results come as `{ nodes: [...] }`.
# @filterRequirement is satisfied per entity:
#   CVR_Branche       -> vaerdi (or CVREnhedsId or datafordelerRowId)
#   CVR_Navn          -> CVREnhedsId (or datafordelerRowId or vaerdi)
#   CVR_Adressering   -> CVREnhedsId (or Adresse or datafordelerRowId)
#   CVR_e_mailadresse -> CVREnhedsId (or datafordelerRowId)
#   CVR_Telefonnummer -> CVREnhedsId (or datafordelerRowId)
#   CVR_Beskaeftigelse -> CVREnhedsId (or datafordelerRowId)
#   CVR_Virksomhed    -> id (= CVREnhedsId) (or CVRNummer or datafordelerRowId or virksomhedStartdato)

# Phase 1: get CVREnhedsIds by branchekode (paginated)
# virkningTil is NOT in CVR_BrancheFilterInput — active filtering is client-side.
Q_BRANCHE = """
query Branche($kode: String!, $first: Int!, $after: String) {
  CVR_Branche(first: $first after: $after where: { vaerdi: { eq: $kode } }) {
    pageInfo { hasNextPage endCursor }
    nodes { CVREnhedsId vaerdi vaerdiTekst virkningTil }
  }
}
"""

# Phase 2a: company names
# virkningTil in CVR_NavnFilterInput — but we filter active records client-side
# to keep consistent fallback logic across all entity types.
Q_NAVN = """
query Navne($ids: [String!]!) {
  CVR_Navn(first: 500 where: { CVREnhedsId: { in: $ids } }) {
    nodes { CVREnhedsId vaerdi virkningTil }
  }
}
"""

# Phase 2b: addresses
# AdresseringAnvendelse distinguishes "Postadresse" from "Besoegsadresse".
# virkningTil is in CVR_AdresseringFilterInput but we filter client-side for
# consistent active/fallback logic.
Q_ADRESSE = """
query Adresser($ids: [String!]!) {
  CVR_Adressering(first: 500 where: { CVREnhedsId: { in: $ids } }) {
    nodes {
      CVREnhedsId
      AdresseringAnvendelse
      CVRAdresse_vejnavn
      CVRAdresse_husnummerFra
      CVRAdresse_postnummer
      CVRAdresse_postdistrikt
      virkningTil
    }
  }
}
"""

# Phase 2c: emails
Q_EMAIL = """
query Emails($ids: [String!]!) {
  CVR_e_mailadresse(first: 500 where: { CVREnhedsId: { in: $ids } }) {
    nodes { CVREnhedsId vaerdi virkningTil }
  }
}
"""

# Phase 2d: phone numbers
# CVR_Telefonnummer field name is `vaerdi` (confirmed from live schema).
# There is no `kontaktoplysning` field on this type.
Q_TELEFON = """
query Telefoner($ids: [String!]!) {
  CVR_Telefonnummer(first: 500 where: { CVREnhedsId: { in: $ids } }) {
    nodes { CVREnhedsId vaerdi virkningTil }
  }
}
"""

# Phase 2e: employee counts
# CVR_Beskaeftigelse has NO virkningTil field in the live schema.
# It uses datoTil (LocalDate, non-nullable) — we pick the record with the
# latest datoTil, which represents the most current employment snapshot.
Q_BESK = """
query Beskaeftigelse($ids: [String!]!) {
  CVR_Beskaeftigelse(first: 500 where: { CVREnhedsId: { in: $ids } }) {
    nodes {
      CVREnhedsId
      antal
      intervalFra
      intervalTil
      beskaeftigelsestalstype
      datoTil
    }
  }
}
"""

# Phase 2f: public CVR number (CVRNummer)
# CVR_Virksomhed.id == CVREnhedsId from other tables.
# CVR_Virksomhed has no CVREnhedsId field — filter by `id` instead.
# @filterRequirement: requiresOneOfFields ["CVRNummer","datafordelerRowId","id","virksomhedStartdato"]
Q_VIRKSOMHED = """
query Virksomheder($ids: [String!]!) {
  CVR_Virksomhed(first: 500 where: { id: { in: $ids } }) {
    nodes { id CVRNummer virkningTil }
  }
}
"""

# ── HTTP helper ───────────────────────────────────────────────────────────────

def _get_oauth_token() -> str:
    """Get or refresh OAuth Bearer token (valid 60 min)."""
    global _oauth_token, _oauth_expires
    if _oauth_token and time.time() < _oauth_expires - 60:
        return _oauth_token
    resp = requests.post(OAUTH_TOKEN_URL, data={
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }, timeout=30)
    if resp.status_code != 200:
        raise SystemExit(f"[OAUTH ERROR] Token request failed ({resp.status_code}): {resp.text[:200]}")
    body = resp.json()
    _oauth_token = body["access_token"]
    _oauth_expires = time.time() + body.get("expires_in", 3600)
    return _oauth_token


def gql(session: requests.Session, query: str, variables: dict, retries: int = 3) -> dict:
    """Execute a GraphQL query against the Datafordeler CVR API."""
    if USE_OAUTH:
        url = GRAPHQL_URL
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {_get_oauth_token()}"}
    else:
        url = f"{GRAPHQL_URL}?apiKey={API_KEY}"
        headers = {"Content-Type": "application/json"}

    for attempt in range(1, retries + 1):
        try:
            resp = session.post(
                url,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=120,  # Datafordeler can be slow on large queries
            )
        except requests.exceptions.ReadTimeout:
            if attempt < retries:
                wait = attempt * 10
                print(f"  [TIMEOUT] attempt {attempt}/{retries}, retrying in {wait}s ...")
                time.sleep(wait)
                continue
            raise

        if resp.status_code == 401:
            if USE_OAUTH:
                # Token might have expired mid-run, force refresh and retry
                global _oauth_token
                _oauth_token = ""
                headers["Authorization"] = f"Bearer {_get_oauth_token()}"
                if attempt < retries:
                    continue
            raise SystemExit("[AUTH ERROR] Credentials rejected — check .env")
        if resp.status_code == 403:
            raise SystemExit("[ACCESS ERROR] CVR service not enabled for these credentials")
        if resp.status_code == 500:
            print(f"  [500 SERVER ERROR] vars={variables} — skipping")
            if DEBUG:
                print(f"  Response body: {resp.text[:500]}")
            return {"data": {}}
        resp.raise_for_status()

        data = resp.json()
        if DEBUG:
            import json
            print(f"  [DEBUG] vars={variables}")
            print(f"  [DEBUG] response={json.dumps(data)[:600]}")
        if "errors" in data:
            for err in data["errors"]:
                print(f"  [GQL ERROR] {err.get('message', err)}")
            raise SystemExit("GraphQL errors — run --schema to inspect field names")
        return data

    raise RuntimeError("Max retries exceeded")


def nodes_of(data: dict, key: str) -> list:
    """Extract nodes list from a connection response, defensive against missing keys."""
    return data.get("data", {}).get(key, {}).get("nodes", []) or []


# ── Phase 1: collect CVREnhedsIds by branchekode ─────────────────────────────

def fetch_ids_for_code(code: str, session: requests.Session) -> tuple[set[str], dict[str, str]]:
    """Return (set of active CVREnhedsIds, {id: branche_text}) for a given branchekode."""
    ids: set[str] = set()
    branche_map: dict[str, str] = {}
    after = None

    while True:
        data  = gql(session, Q_BRANCHE, {"kode": code, "first": PAGE_SIZE, "after": after})
        conn  = data.get("data", {}).get("CVR_Branche", {}) or {}
        nodes = conn.get("nodes", []) or []
        pi    = conn.get("pageInfo", {}) or {}

        for n in nodes:
            # virkningTil == null means the branchekode record is still active.
            # The filter is not available in the API so we do it client-side.
            if n.get("virkningTil") is None:
                eid = n.get("CVREnhedsId", "")
                if eid:
                    ids.add(eid)
                    branche_map[eid] = n.get("vaerdiTekst", "") or ""

        if not pi.get("hasNextPage"):
            break
        after = pi.get("endCursor")
        time.sleep(0.2)

    return ids, branche_map


# ── Phase 2: batch enrich by CVREnhedsId ─────────────────────────────────────

def _active(nodes: list, id_key: str, val_key: str) -> dict[str, str]:
    """
    From a list of nodes, return a mapping {id -> value}
    preferring active records (virkningTil == null).
    Falls back to the first encountered record if none are active.
    """
    active: dict[str, str]   = {}
    fallback: dict[str, str] = {}

    for n in nodes:
        eid = n.get(id_key, "") or ""
        val = n.get(val_key, "") or ""
        if not eid or not val:
            continue
        if n.get("virkningTil") is None:
            active[eid] = val
        elif eid not in fallback:
            fallback[eid] = val

    return {**fallback, **active}  # active wins over fallback


def _active_address(nodes: list) -> dict[str, dict]:
    """Return {CVREnhedsId -> address dict} for currently active addresses."""
    active:   dict[str, dict] = {}
    fallback: dict[str, dict] = {}

    for n in nodes:
        eid = n.get("CVREnhedsId", "") or ""
        if not eid:
            continue
        rec = {
            "vejnavn":   n.get("CVRAdresse_vejnavn", "") or "",
            "husnummer": n.get("CVRAdresse_husnummerFra", "") or "",
            "postnr":    n.get("CVRAdresse_postnummer", "") or "",
            "by":        n.get("CVRAdresse_postdistrikt", "") or "",
        }
        if n.get("virkningTil") is None:
            active[eid] = rec
        elif eid not in fallback:
            fallback[eid] = rec

    return {**fallback, **active}


def _latest_employees(nodes: list) -> dict[str, int]:
    """
    Return {CVREnhedsId -> employee_count} using the most recent record.
    CVR_Beskaeftigelse has no virkningTil — we use datoTil (non-nullable) for recency.
    Prefers `antal` (exact count); falls back to `intervalFra` (range lower bound).

    beskaeftigelsestalstype values seen in the wild:
      "ANTAL"    — exact headcount (antal is populated)
      "INTERVAL" — range only (intervalFra/intervalTil; antal is null)
      "UOPLYST"  — unknown (both antal and intervalFra are null — skip these)
    We skip records where no numeric value can be extracted.
    """
    best: dict[str, tuple] = {}  # eid -> (datoTil_str, count)

    for n in nodes:
        eid  = n.get("CVREnhedsId", "") or ""
        if not eid:
            continue
        dato = n.get("datoTil", "") or ""

        antal = n.get("antal")
        if antal is None:
            # INTERVAL type: use lower bound of the range
            antal = n.get("intervalFra")
        if antal is None:
            # UOPLYST or unknown type — no usable count, skip
            continue

        try:
            count = int(antal)
        except (TypeError, ValueError):
            continue

        prev_dato, _ = best.get(eid, ("", 0))
        if dato >= prev_dato:
            best[eid] = (dato, count)

    return {eid: count for eid, (_, count) in best.items()}


def _cvr_numbers(nodes: list) -> dict[str, str]:
    """
    Return {CVREnhedsId -> CVRNummer_string} from CVR_Virksomhed nodes.
    CVR_Virksomhed.id == CVREnhedsId; CVRNummer is a Long (public 8-digit number).
    Prefer active records (virkningTil == null); fall back to first encountered.
    """
    active: dict[str, str]   = {}
    fallback: dict[str, str] = {}

    for n in nodes:
        eid    = n.get("id", "") or ""
        cvrnr  = n.get("CVRNummer")
        if not eid or cvrnr is None:
            continue
        val = str(cvrnr)
        if n.get("virkningTil") is None:
            active[eid] = val
        elif eid not in fallback:
            fallback[eid] = val

    return {**fallback, **active}


def enrich_batch(ids: list[str], session: requests.Session) -> dict[str, dict]:
    """Fetch all attributes for a batch of CVREnhedsIds and return joined records."""
    v = {"ids": ids}

    navne     = _active(nodes_of(gql(session, Q_NAVN,       v), "CVR_Navn"),           "CVREnhedsId", "vaerdi")
    adresser  = _active_address(nodes_of(gql(session, Q_ADRESSE,  v), "CVR_Adressering"))
    emails    = _active(nodes_of(gql(session, Q_EMAIL,      v), "CVR_e_mailadresse"),  "CVREnhedsId", "vaerdi")
    telefoner = _active(nodes_of(gql(session, Q_TELEFON,    v), "CVR_Telefonnummer"),  "CVREnhedsId", "vaerdi")
    ansatte   = _latest_employees(nodes_of(gql(session, Q_BESK,       v), "CVR_Beskaeftigelse"))
    cvrnumre  = _cvr_numbers(nodes_of(gql(session, Q_VIRKSOMHED, v), "CVR_Virksomhed"))

    result = {}
    for eid in ids:
        navn = navne.get(eid, "")
        if not navn:
            continue  # skip if no name (likely a produktionsenhed, not a virksomhed)

        emp   = ansatte.get(eid)   # None means not found; 0 is a valid count
        addr  = adresser.get(eid, {})
        cvrnr = cvrnumre.get(eid, "")

        result[eid] = {
            "cvr":     cvrnr or eid,   # public CVR number; fall back to internal id
            "navn":    navn,
            "ansatte": "" if emp is None else emp,
            "adresse": f"{addr.get('vejnavn', '')} {addr.get('husnummer', '')}".strip(),
            "postnr":  addr.get("postnr", ""),
            "by":      addr.get("by", ""),
            "telefon": telefoner.get(eid, ""),
            "email":   emails.get(eid, ""),
            # Store internal ID separately for the virk.dk URL (uses CVRNummer)
            "_eid":    eid,
            "_cvrnr":  cvrnr,
        }
    return result


# ── Schema helper ─────────────────────────────────────────────────────────────

def print_schema():
    """Download and save the live GraphQL schema for inspection."""
    if USE_OAUTH:
        url = SCHEMA_URL
        headers = {"Authorization": f"Bearer {_get_oauth_token()}"}
    else:
        url = f"{SCHEMA_URL}?apiKey={API_KEY}"
        headers = {}
    print(f"Fetching schema from {SCHEMA_URL} ...")
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 401:
            print("[AUTH ERROR] Invalid credentials")
            return
        resp.raise_for_status()
        with open("schema.graphql", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print(f"Schema saved to schema.graphql ({len(resp.text)} chars)")
    except requests.RequestException as e:
        print(f"[ERROR] {e}")


# ── CLI helpers ───────────────────────────────────────────────────────────────

def _parse_sectors() -> tuple[list[str], list[str]]:
    """Parse --sector flags from CLI. Returns (sector_names, all_codes)."""
    selected = []
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--sector" and i + 1 < len(args):
            key = args[i + 1]
            if key not in SECTORS:
                valid = ", ".join(SECTORS.keys())
                print(f"ERROR: Unknown sector '{key}'. Valid: {valid}")
                sys.exit(1)
            selected.append(key)
            i += 2
        else:
            i += 1

    if not selected:
        selected = list(SECTORS.keys())

    names = [SECTORS[k]["name"] for k in selected]
    codes = []
    for k in selected:
        codes.extend(SECTORS[k]["codes"])

    return names, codes


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if "--schema" in sys.argv:
        print_schema()
        return

    if not API_KEY and not USE_OAUTH:
        print("ERROR: No credentials set in .env")
        print("  Option A (recommended): set DATAFORDELER_OAUTH_CLIENT_ID + DATAFORDELER_OAUTH_CLIENT_SECRET")
        print("  Option B: set DATAFORDELER_API_KEY")
        return

    auth_mode = "OAuth" if USE_OAUTH else "API Key"
    print(f"Auth: {auth_mode}")

    sector_names, codes = _parse_sectors()
    print(f"CVR Lead Scraper — Denmark")
    print(f"Sectors: {', '.join(sector_names)}")
    print(f"Filter: {MIN_EMPLOYEES}-{MAX_EMPLOYEES} employees | {len(codes)} branchekoder\n")

    session = requests.Session()

    # Phase 1: collect all active CVREnhedsIds
    all_ids: set[str] = set()
    all_branche: dict[str, str] = {}
    for code in codes:
        ids, branche_map = fetch_ids_for_code(code, session)
        new = ids - all_ids
        all_ids |= new
        all_branche.update(branche_map)
        print(f"  [{code}] {len(new)} new IDs (total: {len(all_ids)})")

    print(f"\nTotal unique companies to enrich: {len(all_ids)}")

    # Phase 2: enrich in batches of PAGE_SIZE
    id_list   = list(all_ids)
    enriched: dict[str, dict] = {}

    for i in range(0, len(id_list), PAGE_SIZE):
        batch = id_list[i : i + PAGE_SIZE]
        print(f"  Enriching {i + 1}-{min(i + PAGE_SIZE, len(id_list))} / {len(id_list)} ...")
        try:
            records = enrich_batch(batch, session)
            enriched.update(records)
        except requests.RequestException as e:
            print(f"  [NETWORK ERROR] batch {i}: {e}")
        time.sleep(0.3)

    # Phase 3: filter by employee count and export
    leads = []
    for eid, rec in enriched.items():
        emp = rec.get("ansatte")
        if emp != "" and emp is not None:
            if not (MIN_EMPLOYEES <= int(emp) <= MAX_EMPLOYEES):
                continue
        rec["branche"] = all_branche.get(eid, "")
        # Use public CVRNummer for the virk.dk URL when available
        cvrnr = rec.get("_cvrnr", "")
        if cvrnr:
            rec["virk_url"] = f"https://datacvr.virk.dk/enhed/virksomhed/{cvrnr}"
        else:
            # Fall back to internal id — URL may not resolve but is better than nothing
            rec["virk_url"] = f"https://datacvr.virk.dk/enhed/virksomhed/{eid}"
        leads.append(rec)

    if not leads:
        print("\nNo leads found after filtering.")
        print("Run  python scrape_cvr.py --schema  to verify field names.")
        return

    fieldnames = ["cvr", "navn", "branche", "ansatte", "adresse", "postnr", "by", "telefon", "email", "virk_url"]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(leads)

    with_email = sum(1 for l in leads if l["email"])
    with_phone = sum(1 for l in leads if l["telefon"])
    print(f"\nDone. {len(leads)} leads -> {OUTPUT_FILE}")
    print(f"  With email:  {with_email} ({with_email * 100 // len(leads)}%)")
    print(f"  With phone:  {with_phone} ({with_phone * 100 // len(leads)}%)")


if __name__ == "__main__":
    main()
