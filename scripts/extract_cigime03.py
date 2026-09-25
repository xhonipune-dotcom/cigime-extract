#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import io
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

SOURCE_URL = "https://raw.githubusercontent.com/d-sanoj/EpigCorpus/main/data/edcs_inscriptions.tsv.gz"
OUT_DIR = Path("output")
RE_CIGIME = re.compile(r"(?:^|\|\s*)CIGIME-03,\s*(\*?\d+)")


def download() -> bytes:
    req = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "cigime-extract/1.0 (+https://github.com/xhonipune-dotcom/cigime-extract)"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    raw = download()

    records: list[dict[str, str]] = []
    by_num: dict[int, list[dict[str, str]]] = defaultdict(list)

    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        reader = csv.DictReader(text, delimiter="\t")
        fieldnames = reader.fieldnames or []

        for row in reader:
            publication = row.get("publication", "") or ""
            belege = row.get("belege", "") or ""
            haystack = publication if "CIGIME-03" in publication else belege
            if "CIGIME-03" not in haystack:
                continue

            matches = RE_CIGIME.findall(haystack)
            if not matches:
                # Keep unexpected CIGIME-03 formatting for manual audit.
                row["cigime03_number"] = ""
                row["cigime03_forgery_marker"] = ""
                records.append(row)
                continue

            for token in matches:
                forged = token.startswith("*")
                num = int(token.lstrip("*"))
                clone = dict(row)
                clone["cigime03_number"] = str(num)
                clone["cigime03_forgery_marker"] = "*" if forged else ""
                records.append(clone)
                by_num[num].append(clone)

    extra = ["cigime03_number", "cigime03_forgery_marker"]
    out_fields = extra + [f for f in fieldnames if f not in extra]

    records.sort(key=lambda r: (
        int(r["cigime03_number"]) if r.get("cigime03_number", "").isdigit() else 10**9,
        r.get("edcs_id", ""),
        r.get("inscription_index", ""),
    ))

    with (OUT_DIR / "cigime03_records.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

    with (OUT_DIR / "cigime03_coverage.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["cigime03_number", "present_in_edcs", "edcs_record_count", "edcs_ids", "places"])
        for n in range(1, 486):
            rows = by_num.get(n, [])
            writer.writerow([
                n,
                "yes" if rows else "no",
                len(rows),
                " | ".join(sorted({r.get("edcs_id", "") for r in rows if r.get("edcs_id")})),
                " | ".join(sorted({r.get("place", "") for r in rows if r.get("place")})),
            ])

    present = sorted(n for n in by_num if 1 <= n <= 485)
    missing = [n for n in range(1, 486) if n not in by_num]
    duplicate_nums = sorted(n for n, rows in by_num.items() if len(rows) > 1 and 1 <= n <= 485)
    outside = sorted(n for n in by_num if n < 1 or n > 485)
    unexpected = sum(1 for r in records if not r.get("cigime03_number"))

    summary = [
        "# CIGIME 3 → EDCS coverage",
        "",
        f"- Burimi: `{SOURCE_URL}`",
        f"- Rekorde EDCS që citojnë `CIGIME-03`: **{len(records)}**",
        f"- Numra CIGIME 3 të pranishëm brenda 1–485: **{len(present)} / 485**",
        f"- Numra që mungojnë: **{len(missing)}**",
        f"- Numra me më shumë se një rekord EDCS: **{len(duplicate_nums)}**",
        f"- Referenca jashtë intervalit 1–485: **{len(outside)}**",
        f"- Rekorde me format `CIGIME-03` të paparsuar automatikisht: **{unexpected}**",
        "",
        "## Numrat që mungojnë",
        "",
        ", ".join(map(str, missing)) if missing else "Asnjë.",
        "",
        "## Numrat me më shumë se një rekord EDCS",
        "",
        ", ".join(map(str, duplicate_nums)) if duplicate_nums else "Asnjë.",
        "",
        "## Shënim metodologjik",
        "",
        "Ky ekstrakt pasqyron vetëm ato rekorde që EDCS i lidh bibliografikisht me `CIGIME-03`. "
        "Mungesa e një numri këtu nuk provon se mbishkrimi mungon nga EDCS; mund të jetë regjistruar vetëm me një botim paralel ose me një referencë tjetër.",
    ]
    (OUT_DIR / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"records={len(records)} present={len(present)} missing={len(missing)} duplicates={len(duplicate_nums)}")


if __name__ == "__main__":
    main()
