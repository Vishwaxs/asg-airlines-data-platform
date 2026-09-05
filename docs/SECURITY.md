# PII handling and access control

## Inventory

| Field | Source | Classification | Treatment | Survives to gold |
|---|---|---|---|---|
| `aadhaar_id` | passengers | National identifier | Zero-pad to 12, HMAC-SHA-256 with pepper, truncate to 16 hex, prefix `PSG_` | As `passenger_sk` only |
| `first_name` | passengers | Direct identifier | Masked to first name plus surname initial | As `masked_name` |
| `last_name` | passengers | Direct identifier | Dropped; initial only | No |
| `email` | passengers | Direct identifier | Masked to `f***l@domain` | As `masked_email` |
| `phone` | passengers | Direct identifier | Masked to `+91-XXXXXX` plus last 4 | As `masked_phone` |
| `date_of_birth` | passengers | Quasi-identifier | Dropped at the silver boundary | No |
| `age` | passengers | Attribute | Retained, plus `age_band` | Yes |
| `passport_number` | bookings | Direct identifier | Dropped at the silver boundary | No |
| `emergency_contact_name` | bookings | Third-party identifier | Dropped at the silver boundary | No |
| `emergency_contact_phone` | bookings | Third-party identifier | Dropped at the silver boundary | No |
| `seat_number` | bookings | Attribute | Retained | Yes |

Age is retained and date of birth is not, because age alone does not identify anyone while date
of birth combined with a name is one of the standard re-identification keys. The emergency
contact fields belong to people who are not even the data subject and no KPI needs them, so
they are dropped rather than masked: the cheapest control for data you do not need is not to
carry it.

## Why HMAC rather than SHA-256

An Aadhaar number is 12 digits. That is a keyspace of 10^12, which a laptop enumerates in
minutes: hash every candidate, build a lookup table, and a plain SHA-256 "anonymised" column
becomes reversible. HMAC-SHA-256 keyed with a pepper held outside the repository makes the
token useless to anyone without the key, while staying deterministic so joins still work across
runs and across tables.

The pepper is read from `ASG_PII_PEPPER`. `.env` is gitignored and `.env.example` carries a
placeholder, never a real value. In Azure the pepper belongs in Key Vault, read at runtime by
managed identity.

Tokens are truncated to 16 hex characters (64 bits). At 1,000 passengers the collision
probability is negligible; the truncation is verified in practice by asserting
`passenger_sk` is unique after the dimension is built.

## Zero-padding before hashing

`aadhaar_id` arrives as `int64` with leading zeros already stripped: 925 values are 12 digits,
109 are 11, 5 are 10. Hashing the raw value would give the same person two different tokens
depending on how many zeros were lost, silently splitting one passenger into two dimension
members. Every value is cast to string and `zfill(12)` before the HMAC. `tests/test_pii.py`
asserts that 10-, 11- and 12-digit forms of the same identity produce one token, and that
without the padding they do not.

## Layer boundaries

| Layer | Contents | Committed | Raw PII |
|---|---|---|---|
| `data/raw/` | Source workbook | No | Yes |
| `data/bronze/` | Parquet, values preserved | No | Yes |
| `data/silver/` | Typed, tokenised, masked | No | No |
| `data/gold/` | Star schema and KPI extracts | Yes | No |
| `data/quarantine/` | Rejected rows and reasons | Yes | No |
| `warehouse/` | DuckDB database | No | No |

No raw identifier crosses the silver boundary. `tests/test_no_pii_leak.py` enforces this by
scanning every gold and quarantine CSV for forbidden column names, raw phone and passport
patterns, unmasked `@`, Aadhaar-shaped digit strings, and date-of-birth-shaped columns. The
scan was verified against a deliberately poisoned file to confirm it fails when it should.

The quarantine files are the case most likely to leak by accident, because the instinct when
rejecting a row is to dump the whole row for debugging. Only flights are quarantined here and
flights carry no PII, but the writer selects columns explicitly rather than dumping, so this
holds if a PII-bearing table is quarantined later.

## Role matrix

| Role | raw | bronze | silver | gold | Power BI |
|---|---|---|---|---|---|
| Data engineer | Read/write | Read/write | Read/write | Read/write | Publish |
| Analyst | None | None | None | Read | Read |
| BI consumer | None | None | None | None | Read (dataset only) |
| Auditor | On request, logged | Read | Read | Read | Read |

The analyst boundary sits at gold deliberately: everything an analyst needs for the required
KPIs exists there, and nothing there is re-identifiable.

## Azure mapping

- One ADLS Gen2 container per layer (`raw`, `bronze`, `silver`, `gold`), RBAC granted at
  container scope so the role matrix above is enforced by the platform rather than by
  convention.
- The pepper in Key Vault, read at runtime through a managed identity. No secret in app
  settings, no secret in the repository.
- ADF pipelines run under a managed identity with write access to bronze and silver only.
- POSIX ACLs on the raw container restricted to the ingestion identity; analysts have no path
  to it.
- Diagnostic logging on the raw container so access is auditable.

## Known gaps

- **Pepper rotation is not implemented.** Rotating it changes every `passenger_sk`, which
  requires a rebuild of the dimension and the facts that reference it. A production build would
  either version the key and store the version alongside the token, or carry a stable internal
  id and treat the token as a display value.
- **No audit log on raw access** in the local build. This exists only once the data is in
  Azure with diagnostic settings enabled.
- **No column-level encryption at rest** beyond whatever the platform provides by default.
- **Masking is not differential privacy.** `masked_name` plus `age_band` plus a route is not a
  strong anonymisation set; it is a reasonable control for an internal analytics audience, not
  a safe public release.
- **The 16-character truncation is a deliberate trade** of collision headroom for readability.
  It is verified at this volume, not proven at arbitrary scale.
