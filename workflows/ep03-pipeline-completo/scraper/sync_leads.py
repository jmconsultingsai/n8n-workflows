"""
sync_leads.py — Unify lead sources into one Google Sheet.
===========================================================
From the JM Consulting YouTube channel — EP3: Pipeline Completo de Leads con IA.

Reads from:
  - CVR scraper output (CSV) — active source, ships with this repo
  - LinkedIn scraper (Excel) — commented out; enable if you have that scraper
  - Jobindex scraper (Excel/JSON) — commented out; enable if you have that scraper
  - Google Places / WF4 (Sheet) — commented out; enable if you have WF4 running

Writes to:
  Google Sheet with tabs: RAW_LEADS, CALL_LIST, LINKEDIN_VOLUME

ADAPTING TO YOUR SETUP
------------------------
This script is tightly integrated with the CVR scraper (scrape_cvr.py) and a
specific Google Sheet structure. If your setup differs, paste this file into
Claude (or any LLM) along with your Sheet structure and ask it to adapt:

  "I have a leads scraper that outputs [format] with columns [list].
   Adapt sync_leads.py to read from that format and write to a Google Sheet
   with the same RAW_LEADS / CALL_LIST / LINKEDIN_VOLUME tab structure."

Usage:
    python sync_leads.py              # sync CVR source only
    python sync_leads.py --classify   # re-sort existing leads into tiers

Requirements:
    pip install gspread google-auth openpyxl python-dotenv
"""

from __future__ import annotations

import io
import csv
import sys
import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# Windows cp1252 fix — must be before any print() calls
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv()

import gspread
from google.oauth2.service_account import Credentials

try:
    import openpyxl
except ImportError:
    print("ERROR: pip install openpyxl")
    sys.exit(1)


# ── Config ───────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent

# Google Sheets — set these in .env
SPREADSHEET_ID       = os.getenv("SPREADSHEET_ID", "")
SERVICE_ACCOUNT_FILE = Path(os.getenv("SERVICE_ACCOUNT_FILE", "credentials.json"))

# Source file paths (relative to this script's directory)
CVR_CSV = BASE_DIR / "leads.csv"

# Other sources exist but are disabled by default.
# To enable LinkedIn or Jobindex: uncomment the import block and the
# corresponding entry in SOURCES at the bottom of this file.
#
# LINKEDIN_EXCEL = BASE_DIR / "linkedin_scraper" / "linkedin_leads.xlsx"
# JOBINDEX_DIR   = BASE_DIR / "jobindex"
#
# For Google Maps (WF4 output in a separate Sheet):
# GMAPS_SPREADSHEET_ID = os.getenv("GMAPS_SPREADSHEET_ID", "")

# Sheet tab names
TAB_RAW      = "RAW_LEADS"
TAB_CALL     = "CALL_LIST"
TAB_LINKEDIN = "LINKEDIN_VOLUME"

# Unified column order — do NOT reorder without also updating the Sheet header
COLUMNS = [
    "Empresa",
    "URL",
    "Email",
    "Telefono",
    "LinkedIn",
    "Contacto",
    "Titulo",
    "Industry",
    "Ubicacion",
    "Pais",
    "Empleados",
    "Fuente",
    "Fecha",
    "Score",
    "Tier",
    "Estado",
]

# Leads with Score >= this threshold AND a phone number go to CALL_LIST.
# The scraper does not score leads — scoring happens in leads-audit (separate tool).
CALL_SCORE_THRESHOLD = 3


# ── Google Sheets auth ───────────────────────────────────────────────────────

def get_sheet():
    """Authenticate and return the spreadsheet object."""
    if not SPREADSHEET_ID:
        print("ERROR: SPREADSHEET_ID is not set in .env")
        sys.exit(1)
    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"ERROR: Service account file not found: {SERVICE_ACCOUNT_FILE}")
        print("  Download it from Google Cloud Console -> IAM -> Service Accounts -> Keys.")
        sys.exit(1)

    creds = Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(SPREADSHEET_ID)


def get_or_create_tab(sheet, tab_name: str):
    """Get a worksheet tab, creating it if it does not exist."""
    try:
        return sheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=tab_name, rows=2000, cols=len(COLUMNS))
        ws.update(values=[COLUMNS], range_name="A1")
        ws.format("A1:P1", {"textFormat": {"bold": True}})
        print(f"  Created tab: {tab_name}")
        return ws


# ── Source readers ───────────────────────────────────────────────────────────

def _normalize(row: dict) -> dict:
    """Ensure all unified columns exist with string values."""
    normalized = {}
    for col in COLUMNS:
        val = row.get(col, "")
        normalized[col] = str(val).strip() if val else ""
    return normalized


def read_cvr() -> list[dict]:
    """Read leads from CVR scraper CSV (scrape_cvr.py output)."""
    csv_path = Path(os.getenv("CVR_CSV", str(CVR_CSV)))
    if not csv_path.exists():
        print(f"  SKIP: {csv_path} not found — run scrape_cvr.py first")
        return []

    leads = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            lead = {
                "Empresa":   raw.get("navn", ""),
                "URL":       raw.get("virk_url", ""),
                "Email":     raw.get("email", ""),
                "Telefono":  raw.get("telefon", ""),
                "LinkedIn":  "",
                "Contacto":  "",
                "Titulo":    "",
                "Industry":  raw.get("branche", ""),
                "Ubicacion": raw.get("by", ""),
                "Pais":      "Denmark",
                "Empleados": raw.get("ansatte", ""),
                "Fuente":    "cvr",
                "Fecha":     str(date.today()),
                "Score":     "",
                "Tier":      "pending",
                "Estado":    "nuevo",
            }
            leads.append(_normalize(lead))

    print(f"  CVR: {len(leads)} leads read from {csv_path.name}")
    return leads


# ── Other source readers (disabled — uncomment to enable) ────────────────────
#
# def read_linkedin() -> list[dict]:
#     """Read leads from LinkedIn scraper Excel."""
#     if not LINKEDIN_EXCEL.exists():
#         print(f"  SKIP: {LINKEDIN_EXCEL} not found")
#         return []
#
#     wb = openpyxl.load_workbook(LINKEDIN_EXCEL, read_only=True)
#     ws = wb.active
#     if ws is None:
#         return []
#
#     rows = list(ws.iter_rows(min_row=1, values_only=True))
#     if not rows:
#         return []
#
#     headers = [str(h or "").strip() for h in rows[0]]
#     leads = []
#     for row in rows[1:]:
#         raw = dict(zip(headers, row))
#         lead = {
#             "Empresa":   raw.get("Empresa actual", "") or "",
#             "Email":     raw.get("Email", "") or "",
#             "LinkedIn":  raw.get("LinkedIn URL", "") or "",
#             "Contacto":  raw.get("Nombre completo", "") or "",
#             "Titulo":    raw.get("Titulo actual", "") or "",
#             "Ubicacion": raw.get("Ubicacion", "") or "",
#             "Pais":      _guess_country(raw.get("Ubicacion", "") or ""),
#             "Empleados": raw.get("Tamano empresa", "") or "",
#             "Fuente":    "linkedin",
#             "Fecha":     str(raw.get("Fecha de scraping", date.today())),
#             "Tier":      "LINKEDIN",
#             "Estado":    raw.get("Estado", "nuevo") or "nuevo",
#         }
#         leads.append(_normalize(lead))
#     wb.close()
#     print(f"  LinkedIn: {len(leads)} leads read")
#     return leads
#
#
# def read_jobindex() -> list[dict]:
#     """Read leads from Jobindex scraper (JSON or Excel)."""
#     import json
#     json_files = sorted(JOBINDEX_DIR.glob("jobindex_leads_*.json"), reverse=True)
#     xlsx_files = sorted(JOBINDEX_DIR.glob("jobindex_leads_*.xlsx"), reverse=True)
#
#     if not json_files and not xlsx_files:
#         print(f"  SKIP: No jobindex output found in {JOBINDEX_DIR}")
#         return []
#
#     leads = []
#     if json_files:
#         with open(json_files[0], encoding="utf-8") as f:
#             data = json.load(f)
#         for item in data if isinstance(data, list) else data.get("leads", []):
#             lead = {
#                 "Empresa":  item.get("company", "") or item.get("empresa", ""),
#                 "URL":      item.get("company_url", "") or item.get("url", ""),
#                 "Email":    item.get("contact_email", "") or item.get("email", ""),
#                 "Telefono": item.get("phone", "") or item.get("telefono", ""),
#                 "Industry": "staffing-signal",
#                 "Pais":     "Denmark",
#                 "Fuente":   "jobindex",
#                 "Fecha":    str(date.today()),
#                 "Tier":     "pending",
#                 "Estado":   "nuevo",
#             }
#             leads.append(_normalize(lead))
#         print(f"  Jobindex: {len(leads)} leads read from {json_files[0].name}")
#     return leads
#
#
# def read_gmaps() -> list[dict]:
#     """Read leads from WF4-gmaps Google Sheet (separate spreadsheet)."""
#     gmaps_id = os.getenv("GMAPS_SPREADSHEET_ID", "")
#     if not gmaps_id:
#         print("  SKIP: GMAPS_SPREADSHEET_ID not set in .env")
#         return []
#     try:
#         creds = Credentials.from_service_account_file(
#             str(SERVICE_ACCOUNT_FILE),
#             scopes=[
#                 "https://www.googleapis.com/auth/spreadsheets.readonly",
#                 "https://www.googleapis.com/auth/drive.readonly",
#             ],
#         )
#         gc = gspread.authorize(creds)
#         gmaps_sheet = gc.open_by_key(gmaps_id)
#         ws = gmaps_sheet.sheet1
#     except Exception as e:
#         print(f"  SKIP: Could not read GMaps sheet: {e}")
#         return []
#
#     all_records = ws.get_all_records()
#     leads = []
#     # WF4 columns: Nombre, Web, Correo, Telefono, Direccion, Nicho, Ciudad, Estado, Fecha
#     for raw in all_records:
#         lead = {
#             "Empresa":   raw.get("Nombre", ""),
#             "URL":       raw.get("Web", ""),
#             "Email":     raw.get("Correo", ""),
#             "Telefono":  raw.get("Telefono", ""),
#             "Industry":  raw.get("Nicho", ""),
#             "Ubicacion": raw.get("Ciudad", ""),
#             "Pais":      _guess_country(raw.get("Ciudad", "") or raw.get("Direccion", "")),
#             "Fuente":    "gmaps",
#             "Fecha":     raw.get("Fecha", str(date.today())),
#             "Tier":      "pending",
#             "Estado":    raw.get("Estado", "nuevo"),
#         }
#         leads.append(_normalize(lead))
#     print(f"  GMaps: {len(leads)} leads read from WF4 sheet")
#     return leads

# ─────────────────────────────────────────────────────────────────────────────


def _guess_country(location: str) -> str:
    """Guess country from a location string."""
    loc = location.lower()
    dk_signals = [
        "denmark", "danmark", "copenhagen", "kobenhavn", "aarhus",
        "odense", "aalborg", "esbjerg", "kolding", "hovedstaden",
        "midtjylland", "syddanmark", "nordjylland", "sjaelland",
    ]
    us_signals = [
        "united states", "usa", "florida", "texas", "california",
        "new york", "miami", "houston", "dallas", " fl", " tx", " ca", " ny",
    ]
    if any(s in loc for s in dk_signals):
        return "Denmark"
    if any(s in loc for s in us_signals):
        return "USA"
    return ""


# ── Deduplication ────────────────────────────────────────────────────────────

def _dedup_key(lead: dict) -> str:
    """Generate a dedup key from company name + URL."""
    name = re.sub(r"[^a-z0-9]", "", (lead.get("Empresa") or "").lower())
    url  = re.sub(r"[^a-z0-9]", "", (lead.get("URL") or "").lower())
    return f"{name}|{url}" if name else url


def dedup_against_existing(new_leads: list[dict], existing_rows: list[list]) -> list[dict]:
    """Remove leads that already exist in the sheet (by company name + URL)."""
    existing_keys: set[str] = set()
    for row in existing_rows[1:]:  # skip header
        if len(row) >= 2:
            name = re.sub(r"[^a-z0-9]", "", str(row[0] or "").lower())
            url  = re.sub(r"[^a-z0-9]", "", str(row[1] or "").lower())
            existing_keys.add(f"{name}|{url}")

    unique = []
    for lead in new_leads:
        key = _dedup_key(lead)
        if key and key not in existing_keys:
            unique.append(lead)
            existing_keys.add(key)

    return unique


# ── Classify into tiers ──────────────────────────────────────────────────────

def classify_leads(sheet) -> None:
    """
    Read RAW_LEADS, sort scored leads into CALL_LIST and LINKEDIN_VOLUME tabs.

    CALL_LIST criteria:
      - Score >= CALL_SCORE_THRESHOLD AND has phone number, OR
      - No score yet but has phone from a reliable source (cvr, gmaps)
      - Estado != "descartado"

    LINKEDIN_VOLUME: everything else that has a LinkedIn URL or company name.

    Note: scoring is done externally (leads-audit tool, not included here).
    """
    raw_ws  = get_or_create_tab(sheet, TAB_RAW)
    call_ws = get_or_create_tab(sheet, TAB_CALL)
    link_ws = get_or_create_tab(sheet, TAB_LINKEDIN)

    all_rows = raw_ws.get_all_records()
    if not all_rows:
        print("  No leads in RAW_LEADS to classify.")
        return

    call_leads:     list[dict] = []
    linkedin_leads: list[dict] = []

    for row in all_rows:
        estado = str(row.get("Estado", "")).lower()
        if estado == "descartado":
            continue

        score_raw   = row.get("Score", "")
        has_phone   = bool(row.get("Telefono", ""))
        has_linkedin = bool(row.get("LinkedIn", ""))

        try:
            score = int(score_raw) if score_raw else -1
        except (ValueError, TypeError):
            score = -1

        if has_phone and (score >= CALL_SCORE_THRESHOLD or (score == -1 and row.get("Fuente") in ("cvr", "gmaps"))):
            row["Tier"] = "CALL"
            call_leads.append(row)
        elif has_linkedin or row.get("Empresa"):
            row["Tier"] = "LINKEDIN"
            linkedin_leads.append(row)

    # Write CALL_LIST
    call_ws.clear()
    call_ws.update(values=[COLUMNS], range_name="A1")
    if call_leads:
        rows = [[lead.get(col, "") for col in COLUMNS] for lead in call_leads]
        call_ws.update(values=rows, range_name="A2")
    call_ws.format("A1:P1", {"textFormat": {"bold": True}})

    # Write LINKEDIN_VOLUME
    link_ws.clear()
    link_ws.update(values=[COLUMNS], range_name="A1")
    if linkedin_leads:
        rows = [[lead.get(col, "") for col in COLUMNS] for lead in linkedin_leads]
        link_ws.update(values=rows, range_name="A2")
    link_ws.format("A1:P1", {"textFormat": {"bold": True}})

    print(f"\n  CALL_LIST:       {len(call_leads)} leads (score >= {CALL_SCORE_THRESHOLD} + phone)")
    print(f"  LINKEDIN_VOLUME: {len(linkedin_leads)} leads")


# ── Active sources ───────────────────────────────────────────────────────────
# Add read_linkedin, read_jobindex, read_gmaps here when you enable them above.

SOURCES: dict[str, callable] = {
    "cvr": read_cvr,
}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    selected_sources: list[str] = []
    do_classify = "--classify" in sys.argv

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--source" and i < len(sys.argv) - 1:
            key = sys.argv[i + 1]
            if key not in SOURCES:
                print(f"ERROR: Unknown source '{key}'. Valid: {', '.join(SOURCES)}")
                sys.exit(1)
            selected_sources.append(key)

    if not selected_sources and not do_classify:
        selected_sources = list(SOURCES.keys())

    print(f"Lead Sync — {date.today()}")
    print(f"Sheet: {SPREADSHEET_ID or '(not set — check .env)'}\n")

    sheet = get_sheet()
    print(f"Connected: {sheet.title}\n")

    if selected_sources:
        raw_ws = get_or_create_tab(sheet, TAB_RAW)

        existing = raw_ws.get_all_values()
        if not existing:
            raw_ws.update(values=[COLUMNS], range_name="A1")
            raw_ws.format("A1:P1", {"textFormat": {"bold": True}})
            existing = [COLUMNS]

        all_new: list[dict] = []
        for source_key in selected_sources:
            reader = SOURCES[source_key]
            leads  = reader()
            all_new.extend(leads)

        if not all_new:
            print("\nNo new leads from any source.")
        else:
            unique = dedup_against_existing(all_new, existing)
            print(f"\n  Total new:   {len(all_new)}")
            print(f"  After dedup: {len(unique)}")

            if unique:
                rows     = [[lead.get(col, "") for col in COLUMNS] for lead in unique]
                next_row = len(existing) + 1
                needed   = next_row + len(rows) - 1
                if needed > raw_ws.row_count:
                    raw_ws.resize(rows=needed)
                    print(f"  Resized sheet to {needed} rows")
                raw_ws.update(values=rows, range_name=f"A{next_row}")
                print(f"  Appended {len(rows)} leads to {TAB_RAW} (row {next_row}+)")

    if do_classify or selected_sources:
        print(f"\nClassifying leads into tiers...")
        classify_leads(sheet)

    print(f"\nDone. Sheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")


if __name__ == "__main__":
    main()
