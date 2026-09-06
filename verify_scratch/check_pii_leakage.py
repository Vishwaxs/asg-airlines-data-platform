import sys
import os
import re
from pathlib import Path
import json

print("=== PII LEAKAGE AUDIT ===")

phone_regex = re.compile(r"\+91-\d{10}")
passport_regex = re.compile(r"[A-Z]\d{7}")
email_regex = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
aadhaar_regex = re.compile(r"\b\d{10,12}\b")
dob_regex = re.compile(r"date_of_birth", re.IGNORECASE)

dirs_to_check = ["data/gold", "data/quarantine", "reports", "notebooks"]

findings = []

for d in dirs_to_check:
    dp = Path(d)
    if not dp.exists():
        continue
    for p in dp.rglob("*"):
        if p.is_file():
            # Check text or csv or md or ipynb
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                continue
            
            # Check if notebook
            if p.suffix == ".ipynb":
                # examine both code and output
                nb = json.loads(content)
                text_blobs = []
                for cell in nb.get("cells", []):
                    text_blobs.extend(cell.get("source", []))
                    for out in cell.get("outputs", []):
                        if "text" in out:
                            text_blobs.extend(out["text"])
                        if "data" in out:
                            for mime, data in out["data"].items():
                                if isinstance(data, list):
                                    text_blobs.extend(data)
                                elif isinstance(data, str):
                                    text_blobs.append(data)
                content = "\n".join(text_blobs)

            # Check phone
            phones = phone_regex.findall(content)
            if phones:
                findings.append((str(p), "Raw Phone", phones[:3]))

            # Check passport
            passports = passport_regex.findall(content)
            # filter out normal words or column names like CANCELLED or PSG_
            real_passports = [x for x in passports if not x.startswith("PSG_") and x not in ["CANCEL1", "PENDIN1"]]
            if real_passports:
                # verify if they match raw passport format
                findings.append((str(p), "Passport", real_passports[:3]))

            # Check emails
            emails = email_regex.findall(content)
            unmasked_emails = [e for e in emails if "***" not in e and not e.endswith("example.com")]
            if unmasked_emails:
                findings.append((str(p), "Unmasked Email", unmasked_emails[:3]))

            # Check dob
            if dob_regex.search(content):
                findings.append((str(p), "date_of_birth literal found", []))

            # Check aadhaar numbers (10-12 continuous digits)
            # Exclude timestamps like 20260417, date_keys, etc.
            aadhaars = aadhaar_regex.findall(content)
            # filter out 2025xxxx, 2026xxxx date keys
            suspicious_aadhaar = [a for a in aadhaars if not (a.startswith("2025") or a.startswith("2026") or a.startswith("1899"))]
            if suspicious_aadhaar and p.suffix != ".md": # in md could be row counts or hashes
                findings.append((str(p), "Potential Aadhaar (10-12 digits)", suspicious_aadhaar[:5]))

print(f"Total findings: {len(findings)}")
for f in findings:
    print(f)
