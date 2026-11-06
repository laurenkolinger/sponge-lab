#!/usr/bin/env python3
"""Rebuild config/taxonomy.csv from the World Register of Marine Species (WoRMS).

The genera are the first words of the scientific names in config/species.csv
(UNKN left out), plus any genus named on the command line. For each one the
script asks the WoRMS REST service for the records of that exact name and keeps
the accepted Animalia record of rank Genus. It writes Genus, Family, Order,
Class, and AphiaID, one row per genus in alphabetical order, and replaces the
file only after every genus was found, so a failure leaves the old file whole.

Usage: python3 tools/fetch_taxonomy.py [EXTRA_GENUS ...]
"""

import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from screener.diversity import GENUS_PATTERN, TAXONOMY_COLUMNS, UNKNOWN_CODE, genus_of  # noqa: E402
from screener.species import load_species  # noqa: E402

SPECIES_FILE = ROOT / "config" / "species.csv"
TAXONOMY_FILE = ROOT / "config" / "taxonomy.csv"
RECORDS_URL = "https://www.marinespecies.org/rest/AphiaRecordsByName/{name}?like=false&marine_only=true"
USER_AGENT = "SpongeLab fetch_taxonomy"
TIMEOUT_SECONDS = 30
# WoRMS answers 204 No Content when it knows no record of the name.
NO_CONTENT = 204
ACCEPTED = "accepted"
KINGDOM = "Animalia"
RANK = "Genus"
PART_SUFFIX = ".part"


def accepted_genus(records: Any, genus: str) -> Dict[str, str]:
    """Pick the accepted Animalia genus out of the WoRMS records of a name.

    Args:
        records: The parsed JSON answer of AphiaRecordsByName: a list of
            AphiaRecord objects, or None when WoRMS knows no record.
        genus: The genus asked for, such as "Aplysina".

    Returns:
        ``{"Genus", "Family", "Order", "Class", "AphiaID"}`` as text. A rank
        WoRMS leaves blank reads "".

    Raises:
        ValueError: Starting with the genus when the answer is not a list of
            objects, or when it holds no accepted Animalia record of rank Genus
            with that exact name, or more than one.
    """
    if records is None:
        records = []
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise ValueError(f"{genus}: expected a list of WoRMS records, got {type(records).__name__}")
    matches = [
        record
        for record in records
        if record.get("scientificname") == genus
        and record.get("status") == ACCEPTED
        and record.get("kingdom") == KINGDOM
        and record.get("rank") == RANK
    ]
    if len(matches) != 1:
        raise ValueError(f"{genus}: expected one accepted {KINGDOM} record of rank {RANK}, found {len(matches)}")
    record = matches[0]
    return {
        "Genus": genus,
        "Family": record.get("family") or "",
        "Order": record.get("order") or "",
        "Class": record.get("class") or "",
        "AphiaID": str(record.get("AphiaID") or ""),
    }


def fetch_records(genus: str) -> Any:
    """Ask WoRMS for the records of one name.

    Args:
        genus: The genus.

    Returns:
        The parsed JSON answer, or None when WoRMS knows no record of the name.

    Raises:
        OSError: When the service cannot be reached or answers with an error.
        ValueError: When the answer is not JSON.
    """
    url = RECORDS_URL.format(name=urllib.parse.quote(genus))
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        if response.status == NO_CONTENT:
            return None
        return json.loads(response.read().decode("utf-8"))


def genera_to_fetch(species_file: Path, extra: Iterable[str]) -> List[str]:
    """List the genera of the species list and the extra genera, without repeats.

    Args:
        species_file: config/species.csv.
        extra: Genera named on the command line.

    Returns:
        The genera in alphabetical order.

    Raises:
        ValueError: When the species file breaks its rules, or starting with
            ``genus`` when an extra genus is not one capitalized word.
    """
    genera = {genus_of(item.name) for item in load_species(species_file) if item.code != UNKNOWN_CODE}
    for genus in extra:
        if not GENUS_PATTERN.fullmatch(genus):
            raise ValueError(f"genus: {genus!r} must be one capitalized word, such as Aplysina")
        genera.add(genus)
    return sorted(genera)


def build_rows(genera: Iterable[str], fetch: Callable[[str], Any]) -> List[Dict[str, str]]:
    """Look up every genus.

    Args:
        genera: The genera, in the order of the rows.
        fetch: Takes a genus and returns the parsed WoRMS answer.

    Returns:
        One accepted_genus row per genus.

    Raises:
        ValueError: From accepted_genus, for the first genus WoRMS cannot place.
        OSError: When fetch cannot reach the service.
    """
    rows = []
    for genus in genera:
        rows.append(accepted_genus(fetch(genus), genus))
        sys.stderr.write(f"{genus}: {rows[-1]['Family']}, {rows[-1]['Order']}, {rows[-1]['Class']}\n")
    return rows


def write_rows(path: Path, rows: List[Dict[str, str]]) -> None:
    """Write the taxonomy table through a temporary file beside it.

    Args:
        path: The taxonomy.csv to replace.
        rows: The rows, with every column of TAXONOMY_COLUMNS.

    Raises:
        OSError: When the file cannot be written.
    """
    partial = path.with_name(path.name + PART_SUFFIX)
    with open(partial, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(TAXONOMY_COLUMNS)
        writer.writerows([row[column] for column in TAXONOMY_COLUMNS] for row in rows)
    os.replace(partial, path)


def main(arguments: List[str]) -> int:
    """Rebuild config/taxonomy.csv.

    Args:
        arguments: Extra genera to include.

    Returns:
        0 on success, 1 when a genus cannot be placed or WoRMS cannot be reached.
    """
    try:
        rows = build_rows(genera_to_fetch(SPECIES_FILE, arguments), fetch_records)
        write_rows(TAXONOMY_FILE, rows)
    except (OSError, ValueError) as error:
        sys.stderr.write(f"fetch_taxonomy: {error}. {TAXONOMY_FILE} is unchanged.\n")
        return 1
    sys.stderr.write(f"fetch_taxonomy: wrote {len(rows)} genera to {TAXONOMY_FILE}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
