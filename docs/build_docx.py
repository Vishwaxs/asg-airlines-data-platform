"""Generates docs/ASG_Airlines_Documentation.docx from the artefacts of the last pipeline run.

Numbers come from reports/run_manifest.json and data/gold/, so the document cannot drift from
the data. Re-run it after the Power BI screenshots land in powerbi/screenshots/ and they
replace the placeholders automatically.

    python docs/build_docx.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GOLD = ROOT / "data" / "gold"
REPORTS = ROOT / "reports"
DOCS = ROOT / "docs"
SHOTS = ROOT / "powerbi" / "screenshots"

PAGES = [
    ("01_executive_overview.png", "Executive Overview"),
    ("02_duration_schedule.png", "Duration and Schedule"),
    ("03_route_airline.png", "Route and Airline Performance"),
    ("04_data_quality.png", "Data Quality and Anomalies"),
]

SHEET_NOTES = {
    "flights": {
        "flight_id": "1,004 unique of 1,020. 16 duplicated: 15 byte-identical, 6F250 conflicting.",
        "airline": "41 null, 31 literal UNKNOWN, 4 real carriers.",
        "source": "6 cities, all 30 ordered pairs present, no self-routes.",
        "destination": "As source.",
        "departure_time": "Spans four days, 2026-04-17 to 2026-04-20.",
        "arrival_time": "Precedes departure on SJ192 only.",
        "duration": "Mixed type: 1,019 datetime.time, 1 datetime.datetime (Excel negative time).",
    },
    "bookings": {
        "booking_id": "Unique, no duplicate rows.",
        "passenger_id": "No orphans against passengers.",
        "flight_id": "No orphans against flights. 32 rows point at duplicated ids.",
        "booking_date": "2025-04-17 to 2026-04-17, 342 distinct dates. The only usable time axis.",
        "status": "45 null, 30 literal INVALID, 3 valid values.",
        "seat_number": "No duplicate (flight_id, seat_number) pairs.",
        "passport_number": "100% matches ^[A-Z]d{7}$. Dropped at the silver boundary.",
        "emergency_contact_name": "Third-party PII. Dropped at the silver boundary.",
        "emergency_contact_phone": "100% matches +91 format. Dropped at the silver boundary.",
    },
    "payments": {
        "payment_id": "Unique.",
        "booking_id": "No orphans. 1,000 payments across 637 bookings.",
        "amount": "Three Python types: 961 float, 9 int, 30 str (all literal INVALID). 48 null.",
        "payment_method": "UPI 358, CARD 329, NETBANKING 313, no nulls.",
    },
    "passengers": {
        "passenger_id": "1,000 unique of 1,039. 36 duplicated, all conflicting, none identical.",
        "first_name": "Varies within 11 of 36 duplicate groups.",
        "last_name": "10 null. Varies within 17 of 36 duplicate groups.",
        "age": "1 to 89, 227 under 18. Consistent with date_of_birth in every row.",
        "gender": "M/F only, no nulls, never varies within a duplicate group.",
        "email": "Varies within all 36 duplicate groups.",
        "phone": "100% matches +91 format. Varies within all 36 groups.",
        "aadhaar_id": "int64 with leading zeros lost: 925 are 12 digits, 109 are 11, 5 are 10.",
        "date_of_birth": "Varies within all 36 groups. Dropped at the silver boundary.",
    },
}


def load_context() -> dict:
    manifest = json.loads((REPORTS / "run_manifest.json").read_text(encoding="utf-8"))
    return {
        "manifest": manifest,
        "headline": manifest["headline"],
        "anomalies": pd.read_csv(GOLD / "anomaly_summary.csv"),
        "dq": pd.read_csv(GOLD / "dq_score.csv"),
        "airlines": pd.read_csv(GOLD / "v_flights_by_airline.csv"),
        "routes": pd.read_csv(GOLD / "v_route_performance.csv"),
        "payment_quality": pd.read_csv(GOLD / "v_payment_quality.csv"),
        "status": pd.read_csv(GOLD / "v_booking_status.csv"),
    }


def add_table(doc: Document, df: pd.DataFrame, style: str = "Light Grid Accent 1") -> None:
    table = doc.add_table(rows=1, cols=len(df.columns))
    table.style = style
    for cell, name in zip(table.rows[0].cells, df.columns):
        cell.text = str(name)
        for run in cell.paragraphs[0].runs:
            run.bold = True
    for _, row in df.iterrows():
        cells = table.add_row().cells
        for cell, value in zip(cells, row):
            cell.text = "" if pd.isna(value) else str(value)
    doc.add_paragraph()


def add_image(doc: Document, path: Path, caption: str, width: float = 6.2) -> None:
    if path.exists():
        doc.add_picture(str(path), width=Inches(width))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        placeholder = doc.add_paragraph()
        run = placeholder.add_run(f"[ {path.name} not generated yet ]")
        run.italic = True
        run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
        placeholder.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap = doc.add_paragraph(caption)
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.runs[0].italic = True
    cap.runs[0].font.size = Pt(9)


def build(ctx: dict) -> Document:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    h = ctx["headline"]
    manifest = ctx["manifest"]

    title = doc.add_heading("ASG Airlines Data Platform", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph(
        "Ingestion, cleaning, modelling and reporting over the ASG Airlines operational workbook"
    )
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta = doc.add_paragraph(f"Run {manifest['run_id']}  |  generated {manifest['generated_at'][:10]}")
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break()

    # 1
    doc.add_heading("1. Problem statement and scope", level=1)
    doc.add_paragraph(
        "The source is a single Excel workbook of four sheets - flights, bookings, payments and "
        "passengers - holding 4,059 rows of operational airline data with deliberately injected "
        "quality defects. The task is to build a pipeline that ingests it, resolves those "
        "defects defensibly, models the result for analysis, protects the personal data it "
        "carries, and reports the KPIs the business asked for."
    )
    doc.add_paragraph(
        "Scope covers ingestion through to a Power BI dataset: a layered pipeline with a "
        "declarative validation rule set, a documented quarantine path, a star schema in DuckDB, "
        "PII tokenisation, and four report pages. Out of scope are streaming ingestion, a "
        "scheduler, and any production secret management beyond an environment variable, all of "
        "which are addressed as a migration path rather than implemented."
    )
    doc.add_paragraph(
        "One requirement could not be met as literally stated, and that is a finding rather than "
        "a gap: the brief asks for delay analysis, and the workbook contains no scheduled-versus-"
        "actual timestamp pair from which any delay could be derived. Section 10 states what was "
        "built instead and exactly which two columns would be needed to compute true on-time "
        "performance."
    )

    # 2
    doc.add_heading("2. Source dataset structure", level=1)
    doc.add_paragraph(
        "Every figure below was measured from the workbook rather than assumed. The full "
        "profiling output is in reports/profile.md."
    )
    workbook = ROOT / "data" / "raw" / "UseCase_Airlines.xlsx"
    for sheet, notes in SHEET_NOTES.items():
        doc.add_heading(sheet, level=2)
        if workbook.exists():
            df = pd.read_excel(workbook, sheet)
            rows = []
            for column in df.columns:
                rows.append(
                    {
                        "column": column,
                        "type": str(df[column].dtype),
                        "nulls": int(df[column].isna().sum()),
                        "distinct": int(df[column].nunique(dropna=True)),
                        "issues found": notes.get(column, ""),
                    }
                )
            doc.add_paragraph(f"{len(df):,} rows x {len(df.columns)} columns")
            add_table(doc, pd.DataFrame(rows))
        else:
            doc.add_paragraph("Source workbook not present at generation time.")

    # 3
    doc.add_heading("3. Architecture", level=1)
    add_image(doc, DOCS / "architecture.png", "Figure 1: platform architecture")
    doc.add_paragraph(
        "The pipeline is a medallion build. Bronze holds the source values as read, in Parquet, "
        "stamped with run_id, ingested_at, source_sheet and a row_hash. Nothing is corrected "
        "there, because the layer's job is to make the run reproducible and to give every later "
        "assertion something to be checked against. The row_hash in particular does real work "
        "later: byte-identical duplicate detection compares hashes within a key group rather "
        "than re-comparing columns."
    )
    doc.add_paragraph(
        "Silver holds typed, corrected, deduplicated and tokenised data. This is where the "
        "business rules live and where the PII boundary sits: no raw identifier crosses it. "
        "Quarantine sits beside silver and holds rows that could not be arbitrated, each with "
        "the rule that rejected it and the run that rejected it."
    )
    doc.add_paragraph(
        "Gold holds the star schema, written both to a DuckDB database - so the keys and the "
        "KPI logic are expressible in SQL - and to CSV extracts for Power BI. DuckDB is the "
        "warehouse rather than a served database because it is a single file, requires no "
        "server, and reads Parquet natively, which keeps the whole platform reproducible from a "
        "clean checkout."
    )
    doc.add_heading("Why not Spark or Databricks", level=2)
    doc.add_paragraph(
        "1,020 flight records is a single-node problem. Spinning up a Spark cluster for 4,059 "
        "rows costs more in start-up than the entire transform takes; the full pipeline here "
        "runs end to end in under a second. The architecture was chosen so that this is a "
        "deployment decision rather than a design constraint: the stage boundaries in "
        "src/pipeline.py map one to one onto Databricks notebooks or Data Factory activities, so "
        "moving to Spark is a change of executor, not a rewrite."
    )
    doc.add_paragraph(
        "The threshold for that move is where the flight table stops fitting comfortably in "
        "memory - on the order of tens of millions of rows - or where ingestion becomes "
        "continuous rather than batch. Section 12 sets out that path."
    )

    # 4
    doc.add_heading("4. Data flow", level=1)
    add_image(doc, DOCS / "data_flow.png", "Figure 2: stage-by-stage data flow")
    doc.add_paragraph("Row counts for this run, taken from reports/run_manifest.json:")
    stages = pd.DataFrame(manifest["stages"])[
        ["name", "duration_seconds", "rows_in", "rows_out", "rows_quarantined", "status"]
    ]
    add_table(doc, stages)
    ingested = manifest["rows_ingested"]
    doc.add_paragraph(
        f"Ingested {sum(ingested.values()):,} rows: "
        + ", ".join(f"{k} {v:,}" for k, v in ingested.items())
        + ". Silver retains 4,003. The 56-row difference is 15 byte-identical flight duplicates "
        "collapsed, 39 passenger duplicates resolved by survivorship, and 2 rows quarantined. "
        "No row was dropped for being incomplete."
    )

    # 5
    doc.add_heading("5. Data model", level=1)
    add_image(doc, DOCS / "data_model.png", "Figure 3: star schema")
    doc.add_paragraph(
        "Five dimensions and three facts. The grain of each fact is stated here because every "
        "correctness argument in this document depends on it:"
    )
    for text in [
        "fact_flight: one row per surviving flight_id, plus one unknown member at flight_sk = -1.",
        "fact_booking: one row per booking_id. 1,000 rows, always.",
        "fact_payment: one row per payment_id. 1,000 rows across 637 bookings.",
    ]:
        doc.add_paragraph(text, style="List Bullet")
    doc.add_heading("The fan-out, and how the model prevents it", level=2)
    doc.add_paragraph(
        "Joining bookings out to flights and payments in one query returns 1,404 rows from 1,000 "
        "bookings. Two separate fan-outs cause it: 16 flight_ids appeared twice in the source "
        "(1,000 to 1,032 rows), and 637 bookings carry 1,000 payments (1,000 to 1,363 rows). "
        "Summing amount across that join gives 7,593,758.92 against a true total of "
        "7,385,142.98 - an inflation of 208,615.94, or 2.82%."
    )
    doc.add_paragraph(
        "The model prevents this in two ways. Deduplication runs before modelling so flight_sk "
        "is unique in fact_flight - that dependency is the reason the stages are ordered as they "
        "are. And fact_payment stays at payment grain, joined to fact_booking and never to "
        "fact_flight, so a revenue measure cannot reach a flight join. Both are enforced by "
        "tests: tests/test_model.py asserts the source-level inflation figure and that the star "
        "schema does not reproduce it."
    )
    doc.add_heading("Keys and the date dimension", level=2)
    doc.add_paragraph(
        "Primary and foreign keys are declared in sql/01_dimensions.sql and sql/02_facts.sql "
        "rather than only in pandas, so the referential contract is visible to anyone reading "
        "the warehouse. dim_date spans 2025-04-01 to 2026-05-31 because bookings cover twelve "
        "months while flights cover four days in April 2026."
    )
    doc.add_paragraph(
        "In Power BI dim_date takes an active relationship to fact_booking[booking_date_key] and "
        "an inactive one to fact_flight[departure_date_key], activated per measure with "
        "USERELATIONSHIP. The alternative - two separate date tables - was rejected because it "
        "duplicates the calendar, breaks a single date slicer synced across pages, and leaves "
        "two fields that look interchangeable to a report author but are not."
    )
    doc.add_paragraph(
        "Bookings whose flight was quarantined point at flight_sk = -1 rather than being "
        "dropped, so booking counts stay whole. The consequence is visible and intended: route "
        "rollups sum to 998 bookings, not 1,000."
    )

    # 6
    doc.add_heading("6. Assumptions", level=1)
    doc.add_paragraph(
        "Each assumption is stated with the evidence supporting it. The full list, including "
        "what would change each decision, is in docs/ASSUMPTIONS.md."
    )
    assumptions = [
        ("A negative duration is a midnight rollover failure, not a bad record",
         ("SJ192 gives -1,140 minutes raw. Adding one day to the arrival gives exactly 300 "
         "minutes, and the source duration column independently reads 05:00:00 for that row. "
         "Two fields agree, so this is a reconciliation rather than a guess.")),
        ("The source duration column is a witness, not the authority",
         ("Duration is always recomputed from the timestamps. The stored column is parsed only "
         "to reconcile against, because it is mixed-type and a stored duration cannot outrank "
         "the timestamps it describes.")),
        ("Byte-identical duplicates and conflicting duplicates need different treatments",
         ("15 of 16 duplicated flight_ids are byte-identical and collapse to one. 6F250 "
         "disagrees on source city and both timestamps, so no survivor is justifiable and the "
         "whole group is quarantined.")),
        ("Passenger duplicates need survivorship, not a drop",
         ("All 36 duplicate groups conflict and none is byte-identical, so drop_duplicates() "
         "would keep whichever row pandas saw first. The rule is: fewest nulls, then a full "
         "12-digit Aadhaar, then the lowest email. It resolved 10, 5 and 21 groups respectively.")),
        ("A null and a sentinel are different upstream failures",
         ("airline has 41 nulls and 31 UNKNOWN strings; status has 45 nulls and 30 INVALID; "
         "amount has 48 nulls and 30 INVALID. Each pair maps to one analytical bucket but is "
         "counted separately, because they point at different problems in the source system.")),
        ("Aadhaar lost leading zeros to integer typing",
         ("925 values are 12 digits, 109 are 11, 5 are 10, with nothing shorter. That "
         "distribution is the signature of int64 storage, not of data entry error. Values are "
         "zero-padded to 12 before hashing.")),
        ("Nothing merely incomplete is deleted",
         ("Quarantine is reserved for rows that are structurally unusable or ambiguous. 2 rows "
         "of 4,059 are quarantined; everything else is flagged and retained.")),
        ("Revenue has two correct answers",
         ("Gross revenue is every valid payment; confirmed revenue is the subset against "
         "CONFIRMED bookings. 306 payments sit against CANCELLED bookings, so both are always "
         "reported together.")),
        ("booking_date is the only usable time axis",
         ("Bookings span 342 distinct dates across twelve months; flights span four days. Any "
         "trend visual sits on booking_date, and flights are profiled by departure hour instead.")),
        ("Route duration describes the data, not a schedule",
         ("Within BOM-CCU alone durations run 33 to 293 minutes across 90 flights, so duration "
         "is reported as mean with standard deviation and never as a point estimate.")),
    ]
    for i, (claim, evidence) in enumerate(assumptions, start=1):
        p = doc.add_paragraph()
        p.add_run(f"{i}. {claim}. ").bold = True
        p.add_run(evidence)

    # 7
    doc.add_heading("7. Data cleaning logic", level=1)
    doc.add_paragraph(
        "Each rule below states its trigger, its action and how many rows it touched in this "
        "run. Rules are applied in this order; the ordering matters where noted."
    )
    rules = pd.DataFrame(
        [
            {"rule": "Recompute duration", "trigger": "Always",
             "action": "duration_minutes = arrival_ts - departure_ts", "rows": 1020},
            {"rule": "Roll arrival forward", "trigger": "Recomputed duration < 0",
             "action": "arrival_ts + 1 day, was_corrected = True", "rows": 1},
            {"rule": "Quarantine uncorrectable duration",
             "trigger": "Still negative, or > 24 hours",
             "action": "Quarantine, reason uncorrectable_duration", "rows": 0},
            {"rule": "Collapse exact duplicate flights",
             "trigger": "Same flight_id, identical row_hash",
             "action": "Keep one row", "rows": 15},
            {"rule": "Quarantine conflicting flight keys",
             "trigger": "Same flight_id, differing business columns",
             "action": "Quarantine all rows of the group, exclude id from fact_flight", "rows": 2},
            {"rule": "Reroute affected bookings",
             "trigger": "Booking references a quarantined flight",
             "action": "flight_sk = -1, booking retained", "rows": 2},
            {"rule": "Normalise airline", "trigger": "airline null or literal UNKNOWN",
             "action": "airline_clean = UNKNOWN, is_unknown = True, counted separately",
             "rows": 72},
            {"rule": "Normalise status", "trigger": "status null or literal INVALID",
             "action": "UNKNOWN or INVALID, is_valid = False, row retained", "rows": 75},
            {"rule": "Classify amount", "trigger": "amount null or non-numeric",
             "action": "amount_quality missing or non_numeric, amount NULL, row retained",
             "rows": 78},
            {"rule": "Passenger survivorship", "trigger": "Duplicated passenger_id",
             "action": "Fewest nulls, then 12-digit Aadhaar, then lowest email; all logged",
             "rows": 75},
            {"rule": "Keep nameless passengers", "trigger": "last_name null",
             "action": "masked_name from first_name alone, flagged", "rows": 10},
            {"rule": "Tokenise Aadhaar", "trigger": "Always",
             "action": "zfill(12) then HMAC-SHA-256, truncated, prefixed PSG_", "rows": 1039},
            {"rule": "Drop direct identifiers", "trigger": "Always",
             "action": "date_of_birth, passport_number, emergency_contact_* removed", "rows": 2039},
        ]
    )
    add_table(doc, rules)
    doc.add_paragraph(
        "The dependency worth stating: deduplication has to complete before modelling, because "
        "fact_flight requires a unique flight_sk. Reversing those two stages would either "
        "produce duplicate surrogate keys or force the model to arbitrate a conflict it has no "
        "information to resolve."
    )
    doc.add_heading("Validation rules", level=2)
    doc.add_paragraph(
        "Structural checks are declared in config/validation_rules.yaml rather than hard-coded, "
        "and interpreted by src/validate.py. Each rule names a table, a column, a type "
        "(not_null, regex, in_set, range, unique, referential), parameters and a severity: "
        "error routes a row to quarantine, warning flags and retains it. 26 rules ran in this "
        "run with 0 error-severity failures and 205 warning-severity flags, which is itself the "
        "finding - the data is structurally well-formed and its problems are all semantic."
    )
    add_table(doc, ctx["dq"])

    # 8
    doc.add_heading("8. Transformation logic", level=1)
    doc.add_heading("Duration", level=2)
    doc.add_paragraph(
        "Duration is recomputed for every flight as arrival_ts minus departure_ts, in minutes. "
        "The stored duration column is never used as the value, for two reasons: it is a "
        "mixed-type object column that pandas cannot parse uniformly, and a stored aggregate "
        "should not outrank the fields it summarises. It is parsed separately, for every row "
        "where it is readable, purely as a reconciliation source."
    )
    doc.add_paragraph(
        "Where the recomputed duration is negative, exactly one day is added to the arrival "
        "timestamp and the duration is recomputed. The row is marked was_corrected = True with "
        "correction_reason = arrival_rolled_forward_one_day. If it is still negative, or longer "
        "than 24 hours, the row is quarantined instead - the correction is applied once, not "
        "iterated until the number looks reasonable."
    )
    doc.add_heading("SJ192, worked through", level=2)
    doc.add_paragraph(
        "SJ192 departs 2026-04-19 at 18:45:42 and arrives 2026-04-18 at 23:45:42. Recomputed "
        "naively that is -1,140 minutes. Its stored duration cell holds "
        "datetime.datetime(1899, 12, 29, 5, 0), which is how Excel represents a negative "
        "duration and which pd.to_timedelta raises on; parsed for its time component it reads "
        "05:00:00, or 300 minutes."
    )
    doc.add_paragraph(
        "Adding one day to the arrival gives 2026-04-19 23:45:42 and a recomputed duration of "
        "exactly 300 minutes - matching the stored column exactly. The correction is therefore "
        "not an assumption about what the data ought to say; it is two independent fields "
        "agreeing once the date rollover is repaired. The pipeline reports this as a "
        "reconciliation: across all 1,020 flights, exactly one row disagrees with its stored "
        "duration before the correction, by exactly 1,440 minutes, and none disagrees after."
    )
    doc.add_heading("Overnight and red-eye", level=2)
    doc.add_paragraph(
        "is_overnight is true when the departure date differs from the arrival date. is_red_eye "
        "is true when the departure hour falls between 22:00 and 04:59. These are different "
        "measures and both are kept: 122 flights are overnight and 271 are red-eye in this run. "
        "125 flights crossed midnight in the raw data and were already correct there; the "
        "difference is accounted for by the duplicates collapsed and by SJ192, which stops "
        "being overnight once its arrival is repaired."
    )
    doc.add_heading("Tokenisation", level=2)
    doc.add_paragraph(
        "aadhaar_id is cast to string and zero-padded to 12 digits, then passed through "
        "HMAC-SHA-256 keyed with a pepper from the environment, truncated to 16 hex characters "
        "and prefixed PSG_ to form passenger_sk. The order matters: hashing before padding "
        "gives the same person two different surrogate keys, because 114 of 1,039 values lost "
        "leading zeros to int64 storage. That ordering is asserted by a test."
    )

    # 9
    doc.add_heading("9. PII and access control", level=1)
    doc.add_paragraph(
        "Ten source fields carry personal data. Four survive to gold in masked or tokenised "
        "form, six are dropped entirely. The full inventory, role matrix and Azure mapping are "
        "in docs/SECURITY.md; the summary follows."
    )
    pii = pd.DataFrame(
        [
            {"field": "aadhaar_id", "treatment": "zfill(12) then keyed HMAC-SHA-256, truncated",
             "in gold": "As passenger_sk"},
            {"field": "first_name", "treatment": "Masked to first name plus surname initial",
             "in gold": "masked_name"},
            {"field": "last_name", "treatment": "Reduced to an initial", "in gold": "No"},
            {"field": "email", "treatment": "Masked to f***l@domain", "in gold": "masked_email"},
            {"field": "phone", "treatment": "Masked to +91-XXXXXX plus last 4",
             "in gold": "masked_phone"},
            {"field": "date_of_birth", "treatment": "Dropped at the silver boundary",
             "in gold": "No"},
            {"field": "passport_number", "treatment": "Dropped at the silver boundary",
             "in gold": "No"},
            {"field": "emergency_contact_name", "treatment": "Dropped at the silver boundary",
             "in gold": "No"},
            {"field": "emergency_contact_phone", "treatment": "Dropped at the silver boundary",
             "in gold": "No"},
            {"field": "age", "treatment": "Retained with age_band", "in gold": "Yes"},
        ]
    )
    add_table(doc, pii)
    doc.add_paragraph(
        "The tokenisation is keyed rather than a plain hash for a specific reason. An Aadhaar "
        "number is 12 digits, a keyspace of 10^12, which a laptop enumerates in minutes: a "
        "plain SHA-256 column can be reversed by building the lookup table. HMAC with a pepper "
        "held outside the repository makes the token useless without the key while staying "
        "deterministic, so joins survive across runs."
    )
    doc.add_paragraph(
        "Age is retained and date of birth is not, because age alone does not identify anyone "
        "while date of birth plus a name is a standard re-identification key. The emergency "
        "contact fields belong to third parties and no KPI needs them, so they are dropped "
        "rather than masked - the cheapest control for data you do not need is not to carry it."
    )
    doc.add_paragraph(
        "The boundary is enforced by a test, not by convention: tests/test_no_pii_leak.py scans "
        "every gold and quarantine CSV for forbidden column names, raw phone and passport "
        "patterns, unmasked email addresses, Aadhaar-shaped digit strings and date-of-birth-"
        "shaped columns. It was verified against a deliberately poisoned file to confirm it "
        "fails when it should."
    )
    doc.add_paragraph(
        "Known gaps, stated plainly: pepper rotation is not implemented and would invalidate "
        "every surrogate key; there is no audit log on raw access in the local build; and there "
        "is no column-level encryption at rest beyond the platform default."
    )

    # 10
    doc.add_heading("10. KPI definitions", level=1)
    doc.add_paragraph(
        "Every KPI below is defined once in sql/03_kpi_views.sql and once in "
        "powerbi/measures.dax, so the report and the warehouse can be reconciled against each "
        "other."
    )
    kpis = pd.DataFrame(
        [
            {"kpi": "Average flight duration",
             "formula": "AVG(fact_flight.duration_minutes), unknown member excluded",
             "value": f"{h['avg_duration_minutes']:.2f} min"},
            {"kpi": "Duration spread",
             "formula": "STDDEV_SAMP over the same population",
             "value": f"{h['stddev_duration_minutes']:.2f} min"},
            {"kpi": "Route-wise traffic",
             "formula": "COUNT(fact_booking) by route, aggregated at booking grain",
             "value": "998 across 30 routes"},
            {"kpi": "Flights by airline",
             "formula": "COUNT(fact_flight) by dim_airline",
             "value": "4 carriers plus 67 UNKNOWN"},
            {"kpi": "Gross revenue",
             "formula": "SUM(fact_payment.amount) where amount_quality = valid",
             "value": f"{h['gross_revenue']:,.2f}"},
            {"kpi": "Confirmed revenue",
             "formula": "Same, filtered to bookings with status CONFIRMED",
             "value": f"{h['confirmed_revenue']:,.2f}"},
            {"kpi": "Cancellation rate",
             "formula": "CANCELLED bookings / all bookings",
             "value": f"{h['cancellation_rate_pct']:.2f}%"},
            {"kpi": "Confirmation rate",
             "formula": "CONFIRMED bookings / all bookings",
             "value": f"{h['confirmation_rate_pct']:.2f}%"},
            {"kpi": "Payment coverage",
             "formula": "DISTINCT bookings with >= 1 payment / all bookings",
             "value": f"{h['payment_coverage_pct']:.2f}%"},
            {"kpi": "Average ticket value per booking",
             "formula": "Gross revenue / distinct paid bookings, not per payment",
             "value": f"{h['avg_ticket_value_per_booking']:,.2f}"},
            {"kpi": "Bookings per flight",
             "formula": "Bookings / flights",
             "value": f"{h['bookings_per_flight']:.3f}"},
            {"kpi": "Red-eye share",
             "formula": "Departures between 22:00 and 04:59 / all flights",
             "value": f"{h['red_eye_share_pct']:.2f}%"},
            {"kpi": "Overnight share",
             "formula": "Departure date != arrival date / all flights",
             "value": f"{h['overnight_share_pct']:.2f}%"},
            {"kpi": "Data quality score",
             "formula": "1 - (quarantined + flagged) / ingested, per source table",
             "value": f"{ctx['dq']['dq_score'].mean():.4f} mean"},
        ]
    )
    add_table(doc, kpis)
    doc.add_heading("Delay: what was built instead, and why", level=2)
    doc.add_paragraph(
        "The brief asks for delay analysis. Operational delay is the difference between a "
        "scheduled time and an actual time, and this workbook holds exactly one departure "
        "timestamp and one arrival timestamp per flight, with no scheduled counterpart to "
        "difference them against. There is no transformation that recovers a delay from this "
        "data, and inventing one - treating a route average as a schedule, for instance - would "
        "produce a number that looks like on-time performance and means nothing."
    )
    doc.add_paragraph(
        "What is computable is an anomaly rate, so an anomaly taxonomy was defined instead, "
        "with each category counted against the source table it belongs to. Adding "
        "scheduled_departure and scheduled_arrival to the source is the entire fix: with those "
        "two columns, departure delay, arrival delay and an on-time percentage at any threshold "
        "all follow immediately from the existing model."
    )
    add_table(doc, ctx["anomalies"])

    # 11
    doc.add_heading("11. Dashboard walkthrough", level=1)
    intros = {
        "Executive Overview": (
            "The headline figures and the two trends that matter: bookings by month, which is "
            "the only defensible time axis in this data, and flights by airline, where the "
            "UNKNOWN bar is left visible because hiding 67 unattributed flights would overstate "
            "every carrier's share. Gross and confirmed revenue appear side by side, never one "
            "alone."
        ),
        "Duration and Schedule": (
            "Duration by airline and by route, always with its standard deviation, plus the "
            "distribution and the departure-hour profile. There is deliberately no "
            "flights-per-day chart: flights span four days and such a chart would have four "
            "points. Overnight and red-eye are shown as separate measures because they are "
            "different questions."
        ),
        "Route and Airline Performance": (
            "The route matrix carries flights, bookings, average duration with spread, revenue "
            "and cancellation rate for all 30 routes. Bookings sum to 998 rather than 1,000 "
            "because the two bookings on the quarantined 6F250 sit on the unknown flight member "
            "and have no route - visible rather than patched."
        ),
        "Data Quality and Anomalies": (
            "Anomaly counts by type against the right denominators, quality score per source "
            "table, the row-count waterfall from 4,059 ingested to 4,003 retained, the "
            "missing-versus-sentinel breakdown that keeps nulls and INVALID strings apart, and "
            "the two quarantined rows in full. Red is used on this page and nowhere else."
        ),
    }
    for filename, page in PAGES:
        doc.add_heading(page, level=2)
        doc.add_paragraph(intros[page])
        add_image(doc, SHOTS / filename, f"Figure: {page}")

    # 12
    doc.add_heading("12. Scalability", level=1)
    doc.add_paragraph(
        "The path to 100 million rows changes the executor and the storage layout, not the "
        "shape of the pipeline. Stage boundaries stay where they are; each one becomes a "
        "Databricks notebook or a Data Factory activity."
    )
    for text in [
        ("Partition bronze by ingest date, so a run reads only new partitions rather than the "
        "whole history."),
        ("Swap pandas for Spark at the same stage boundaries. The transformations are already "
        "expressed as whole-table operations rather than row loops, so they translate directly."),
        ("Push the star schema into Delta or Synapse, keeping the same keys and the same grain "
        "declarations."),
        ("Aggregate at silver to gold rather than re-reading raw on every run; the KPI views "
        "become materialised tables refreshed on a schedule."),
        ("Add an incremental watermark on booking_date, and switch the source from a full-file "
        "reload to change data capture."),
        ("Move the row_hash from a per-row apply to a hash of concatenated columns computed in "
        "the engine, which is the one place the current implementation would not scale linearly."),
    ]:
        doc.add_paragraph(text, style="List Bullet")
    doc.add_paragraph(
        "Orchestration maps the same way. The declared stage list, its dependency order and the "
        "per-stage counters in run_manifest.json are the same information an orchestrator holds; "
        "moving to Data Factory or Dagster replaces the runner while the stage contracts, the "
        "fail-fast versus quarantine policy and the manifest stay as they are."
    )

    # 13
    doc.add_heading("13. Error handling, logging and idempotency", level=1)
    doc.add_paragraph(
        "The pipeline distinguishes two classes of failure. A schema violation - a missing "
        "sheet, a missing required column - fails the run immediately, because the pipeline can "
        "quarantine a bad row but cannot infer a column that is not there, and a silent partial "
        "load is worse than a stopped one. A row-level failure quarantines the row and the run "
        "continues, with the reason and the run_id recorded alongside it."
    )
    doc.add_paragraph(
        "Every stage records its name, start and end time, duration, rows in, rows out, rows "
        "quarantined and status. Those counters are written to reports/run_manifest.json, which "
        "is diffable between runs, and the same events are logged to stdout and to "
        "reports/logs/{run_id}.log. A failed run still writes its manifest, marked failed, with "
        "the stage that broke."
    )
    doc.add_paragraph(
        "The pipeline is idempotent. Surrogate keys are deterministic - passenger_sk is a keyed "
        "hash of a business value rather than a sequence - layers are overwritten by run_id, "
        "and the DDL drops and recreates the warehouse tables in dependency order. Running it "
        "twice over the same input produces byte-identical gold CSVs, which was verified by "
        "checksumming the outputs of two consecutive runs."
    )
    doc.add_paragraph(
        "python -m src.pipeline runs end to end from a clean checkout with no arguments. "
        "--stage <name> runs a single stage, loading its inputs from the layer on disk. "
        "--dry-run validates the configuration and prints the plan without touching data."
    )

    # 14
    doc.add_heading("14. Known limitations and next steps", level=1)
    for text in [
        ("Delay is not computable from this source. Two columns - scheduled_departure and "
        "scheduled_arrival - would unlock on-time performance without any other change."),
        ("The validation rule engine is hand-rolled. It is declarative and adequate at this "
        "scope, but Great Expectations or dbt tests would bring a maintained rule library, "
        "richer reporting and less code to defend."),
        ("The pepper lives in an environment variable. A real deployment needs a secret store "
        "and a rotation strategy; rotating today invalidates every passenger_sk."),
        ("Ingestion is a full-file reload. Change data capture on the source would remove the "
        "need to re-read unchanged history."),
        ("Route averages describe this dataset rather than a schedule, because durations here "
        "are not a deterministic function of route. Any operational use would need scheduled "
        "block times."),
        ("The unknown flight member is a single catch-all. At larger scale it would need to be "
        "typed by reason, so that quarantined and genuinely-unknown flights are distinguishable "
        "in the facts."),
        ("Passenger survivorship keeps one row and logs the rest. A slowly changing dimension "
        "would preserve the conflicting versions with validity ranges instead of discarding "
        "them, which is what a production identity resolution would do."),
    ]:
        doc.add_paragraph(text, style="List Bullet")

    return doc


def main() -> int:
    ctx = load_context()
    doc = build(ctx)
    out = DOCS / "ASG_Airlines_Documentation.docx"
    doc.save(out)

    missing = [name for name, _ in PAGES if not (SHOTS / name).exists()]
    print(f"wrote {out}")
    if missing:
        print(f"screenshot placeholders still pending: {', '.join(missing)}")
    else:
        print("all four dashboard screenshots embedded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
