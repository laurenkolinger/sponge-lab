"""Species richness, taxonomic coverage, and diversity indices of the sightings.

The Diversity panel (``GET /api/diversity``) and the summary tables of an export
package both come from this module. Richness counts distinct species codes and
leaves out UNKN (Unknown sponge); a genus-level taxon such as Cinachyrella counts
as one taxon. The genus is the first word of the scientific name. The family, the
order, and the class come from ``config/taxonomy.csv``, keyed by genus, so a genus
missing from that file counts at genus rank only.

A sample video is a video with at least one row (labeled or Review) or marked
done. Sample videos are the units of every video count and of the accumulation
curve, which is the exact Mao Tau expected richness. Shannon, Simpson, and Chao1
treat each labeled sighting as one individual and leave out UNKN. The screening
targets chosen species, so the indices describe the sightings, not the reef.

Bad input raises ValueError with a message that starts with the field name.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from screener.names import check_config_text, parse_video_name, read_config_table
from screener.species import Species, species_by_code
from screener.store import LABEL_STATUS_COLUMN, LABELED, STATUS_DONE, STATUS_IN_PROGRESS

TAXONOMY_LABEL = "taxonomy"
GENUS_COLUMN = "Genus"
FAMILY_COLUMN = "Family"
ORDER_COLUMN = "Order"
CLASS_COLUMN = "Class"
APHIA_COLUMN = "AphiaID"
TAXONOMY_COLUMNS = (GENUS_COLUMN, FAMILY_COLUMN, ORDER_COLUMN, CLASS_COLUMN, APHIA_COLUMN)
GENUS_PATTERN = re.compile(r"[A-Z][a-z-]+")
APHIA_PATTERN = re.compile(r"[0-9]+")

UNKNOWN_CODE = "UNKN"
UNKNOWN_SITE = "Unknown site"
# The screening phases. Phases 1 and 2 are Parts 1 and 2 of the ID guide; Phase 3
# holds Part 3 and every species added while screening, which has no guide part.
PHASES = ("1", "2", "3")
GUIDE_PHASES = ("1", "2")
LAST_PHASE = "3"
DECIMALS = 3
DATE_DIGITS = 8


@dataclass(frozen=True)
class Taxon:
    """One row of taxonomy.csv: where a genus sits in the tree of life.

    Attributes:
        genus: The genus, such as "Aplysina".
        family: The family, such as "Aplysinidae", or "".
        order: The order, such as "Verongiida", or "".
        class_name: The class, such as "Demospongiae", or "".
        aphia_id: The WoRMS AphiaID of the genus, such as "131975", or "".
    """

    genus: str
    family: str
    order: str
    class_name: str
    aphia_id: str


@dataclass(frozen=True)
class Placement:
    """A species code with its name, its screening phase, and its ranks.

    Attributes:
        code: The species code, such as "ACAU".
        name: The scientific name.
        phase: "1", "2", or "3"; "" for UNKN and for a code outside the species list.
        genus: The first word of the name, or "" for UNKN.
        family: The family from the taxonomy, or "" when the taxonomy lacks the genus.
        order: The order from the taxonomy, or "".
        class_name: The class from the taxonomy, or "".
    """

    code: str
    name: str
    phase: str
    genus: str
    family: str
    order: str
    class_name: str


@dataclass(frozen=True)
class SampleVideo:
    """One sample video: a video with a row or marked done.

    Attributes:
        key: The S3 key.
        name: The file name.
        site: The Site of its rows, or the site from its file name when it has
            none; UNKNOWN_SITE when that is empty.
        transect: The Transect of its rows, or the transect from its file name.
        date: The survey date from the file name as YYYY-MM-DD, or "" when the
            name is outside the TCRMP pattern.
        status: "done" or "in progress".
    """

    key: str
    name: str
    site: str
    transect: str
    date: str
    status: str


def load_taxonomy(path: Path) -> Dict[str, Taxon]:
    """Load the genus table from taxonomy.csv.

    Args:
        path: The CSV file with the columns ``Genus``, ``Family``, ``Order``,
            ``Class``, and ``AphiaID``. Family, Order, Class, and AphiaID may be blank.

    Returns:
        ``{genus: Taxon}`` in file order. A file with only its header gives ``{}``.

    Raises:
        FileNotFoundError: When the file does not exist.
        ValueError: When the file breaks the read_config_table rules, a genus is
            not one capitalized word or appears twice, an AphiaID holds anything
            but digits, or a cell is unsafe for a CSV cell. The message names the
            file and the line.
    """
    taxonomy: Dict[str, Taxon] = {}
    genus_lines: Dict[str, int] = {}
    for line, row in read_config_table(path, TAXONOMY_COLUMNS, TAXONOMY_LABEL):
        where = f"{TAXONOMY_LABEL} file {path} line {line}"
        cells = {column: check_config_text(row[column], f"{where}: {column}") for column in TAXONOMY_COLUMNS}
        genus = cells[GENUS_COLUMN]
        if not GENUS_PATTERN.fullmatch(genus):
            raise ValueError(f"{where}: {GENUS_COLUMN} {genus!r} must be one capitalized word, such as Aplysina")
        if genus in genus_lines:
            raise ValueError(f"{where}: {GENUS_COLUMN} {genus} already appears on line {genus_lines[genus]}")
        aphia_id = cells[APHIA_COLUMN]
        if aphia_id and not APHIA_PATTERN.fullmatch(aphia_id):
            raise ValueError(f"{where}: {APHIA_COLUMN} {aphia_id!r} must be blank or digits")
        genus_lines[genus] = line
        taxonomy[genus] = Taxon(
            genus=genus,
            family=cells[FAMILY_COLUMN],
            order=cells[ORDER_COLUMN],
            class_name=cells[CLASS_COLUMN],
            aphia_id=aphia_id,
        )
    return taxonomy


def _checked_counts(counts: Any, field: str) -> List[int]:
    """Check a list of counts and keep the ones above zero.

    Args:
        counts: The candidate list.
        field: The argument name for the error message.

    Returns:
        The counts above zero, in order.

    Raises:
        ValueError: Starting with ``field`` when counts is not a list or tuple of
            whole numbers of zero or more.
    """
    if not isinstance(counts, (list, tuple)):
        raise ValueError(f"{field}: expected a list of whole numbers, got {type(counts).__name__}")
    for value in counts:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{field}: expected whole numbers of zero or more, got {value!r}")
    return [value for value in counts if value > 0]


def shannon(counts: Sequence[int]) -> Optional[float]:
    """Compute the Shannon index H' with the natural log.

    Args:
        counts: Sightings per species. Zeros are ignored.

    Returns:
        ``-sum(p * ln p)`` over the species, where p is the share of the
        sightings, or None when there are no sightings.

    Raises:
        ValueError: Starting with ``counts`` for anything but a list of whole
            numbers of zero or more.
    """
    positive = _checked_counts(counts, "counts")
    total = sum(positive)
    if not total:
        return None
    return -sum(count / total * math.log(count / total) for count in positive) + 0.0


def simpson(counts: Sequence[int]) -> Optional[float]:
    """Compute the Simpson index 1 - D.

    Args:
        counts: Sightings per species. Zeros are ignored.

    Returns:
        ``1 - sum(p ** 2)`` over the species, where p is the share of the
        sightings, or None when there are no sightings.

    Raises:
        ValueError: Starting with ``counts`` for anything but a list of whole
            numbers of zero or more.
    """
    positive = _checked_counts(counts, "counts")
    total = sum(positive)
    if not total:
        return None
    return 1.0 - sum((count / total) ** 2 for count in positive)


def chao1(counts: Sequence[int]) -> Optional[float]:
    """Estimate the richness with the bias-corrected Chao1.

    Args:
        counts: Sightings per species. Zeros are ignored.

    Returns:
        ``S + F1 * (F1 - 1) / (2 * (F2 + 1))``, where S is the number of species,
        F1 the number seen once, and F2 the number seen twice; None when there
        are no sightings. With F2 = 0 the formula still holds.

    Raises:
        ValueError: Starting with ``counts`` for anything but a list of whole
            numbers of zero or more.
    """
    positive = _checked_counts(counts, "counts")
    if not positive:
        return None
    singletons = sum(1 for count in positive if count == 1)
    doubletons = sum(1 for count in positive if count == 2)
    return len(positive) + singletons * (singletons - 1) / (2 * (doubletons + 1))


def mao_tau(incidences: Sequence[int], samples: int) -> List[float]:
    """Compute the exact Mao Tau expected richness for 1 to ``samples`` sample videos.

    For H samples and a taxon found in h of them, a draw of m samples without
    replacement misses the taxon with probability C(H - h, m) / C(H, m), so
    E[S(m)] is the sum over taxa of 1 - C(H - h, m) / C(H, m). That ratio is the
    product over j = 0 to m - 1 of (H - h - j) / (H - j); it is built one factor
    per m, so no factorial or binomial is ever formed.

    Args:
        incidences: For each taxon, the number of samples that hold it, 0 to samples.
        samples: The number of samples, H, zero or more.

    Returns:
        ``[E[S(1)], ..., E[S(H)]]``, empty when samples is 0. E[S(H)] is the
        observed number of taxa and E[S(1)] the mean number per sample.

    Raises:
        ValueError: Starting with ``samples`` when it is not a whole number of
            zero or more, or ``incidences`` when it is not a list of whole
            numbers from 0 to samples.
    """
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 0:
        raise ValueError(f"samples: expected a whole number of zero or more, got {samples!r}")
    positive = _checked_counts(incidences, "incidences")
    for value in positive:
        if value > samples:
            raise ValueError(f"incidences: {value} is more than the {samples} samples")
    expected = [0.0] * samples
    for found_in in positive:
        missed = 1.0
        for drawn in range(1, samples + 1):
            missed *= max(samples - found_in - (drawn - 1), 0) / (samples - (drawn - 1))
            expected[drawn - 1] += 1.0 - missed
    return expected


def genus_of(name: str) -> str:
    """Return the genus of a scientific name: its first word.

    Args:
        name: A name such as "Aplysina cauliformis" or "Cinachyrella sp.".

    Returns:
        The first word, or "" for a blank name.
    """
    words = name.split()
    return words[0] if words else ""


def phase_of(species: Species) -> str:
    """Return the screening phase of a species.

    Args:
        species: One species of the list.

    Returns:
        "1" or "2" for guide Parts 1 and 2, "3" for every other species
        (Part 3 and the species added while screening), and "" for UNKN.
    """
    if species.code == UNKNOWN_CODE:
        return ""
    return species.part if species.part in GUIDE_PHASES else LAST_PHASE


def _placement(code: str, name: str, phase: str, taxonomy: Mapping[str, Taxon]) -> Placement:
    """Place one code in the tree.

    Args:
        code: The species code.
        name: The scientific name.
        phase: The screening phase, or "".
        taxonomy: ``{genus: Taxon}``.

    Returns:
        The Placement. UNKN gets no ranks, and a genus the taxonomy lacks gets
        no family, order, or class.
    """
    genus = "" if code == UNKNOWN_CODE else genus_of(name)
    taxon = taxonomy.get(genus)
    return Placement(
        code=code,
        name=name,
        phase=phase,
        genus=genus,
        family=taxon.family if taxon else "",
        order=taxon.order if taxon else "",
        class_name=taxon.class_name if taxon else "",
    )


def place_codes(
    rows: Sequence[Mapping[str, str]], species: Sequence[Species], taxonomy: Mapping[str, Taxon]
) -> Dict[str, Placement]:
    """Place every species of the list, and every other code the labeled rows hold.

    Args:
        rows: Observation rows. Only labeled rows add codes.
        species: The species list, custom species included.
        taxonomy: ``{genus: Taxon}``.

    Returns:
        ``{code: Placement}``: the species list in its order, then the codes
        outside it in code order, each named after its first row and with no phase.

    Raises:
        ValueError: Starting with ``species`` when the list fails species_by_code.
    """
    placements = {
        item.code: _placement(item.code, item.name, phase_of(item), taxonomy)
        for item in species_by_code(species).values()
    }
    extra: Dict[str, str] = {}
    for row in rows:
        code = row["SpeciesCode"]
        if row[LABEL_STATUS_COLUMN] == LABELED and code not in placements and code not in extra:
            extra[code] = row["Sponge Type"]
    for code in sorted(extra):
        placements[code] = _placement(code, extra[code], "", taxonomy)
    return placements


def _iso_date(digits: str) -> str:
    """Write an eight digit date as YYYY-MM-DD.

    Args:
        digits: A date such as "20241022", or "".

    Returns:
        "2024-10-22", or "" for anything but eight digits.
    """
    if len(digits) != DATE_DIGITS or not digits.isdigit():
        return ""
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"


def sample_videos(
    rows: Sequence[Mapping[str, str]], screened: Sequence[Mapping[str, str]], site_names: Mapping[str, str]
) -> Dict[str, SampleVideo]:
    """Find the sample videos: every video with a row, labeled or Review, or marked done.

    Args:
        rows: Observation rows, labeled and unlabeled.
        screened: The rows of videos_screened.csv.
        site_names: ``{site code: site name}``, for the site of a video with no rows.

    Returns:
        ``{S3 key: SampleVideo}``. The site and the transect come from the first
        row of a video, and from its file name when it has no rows. A blank site
        reads UNKNOWN_SITE. A video missing from the screening log is in progress.

    Raises:
        ValueError: Starting with ``site_names`` when it is not a mapping.
    """
    if not isinstance(site_names, Mapping):
        raise ValueError(f"site_names: expected a mapping of site code to name, got {type(site_names).__name__}")
    first_rows: Dict[str, Mapping[str, str]] = {}
    for row in rows:
        first_rows.setdefault(row["S3Key"], row)
    statuses = {row["S3Key"]: row["Status"] for row in screened}
    done = [key for key, status in statuses.items() if status == STATUS_DONE and key not in first_rows]
    videos: Dict[str, SampleVideo] = {}
    for key in [*first_rows, *done]:
        parsed = parse_video_name(key, site_names)
        first = first_rows.get(key)
        site = first["Site"] if first else parsed.site_name
        videos[key] = SampleVideo(
            key=key,
            name=parsed.file_name,
            site=site or UNKNOWN_SITE,
            transect=first["Transect"] if first else parsed.transect,
            date=_iso_date(parsed.date),
            status=statuses.get(key, STATUS_IN_PROGRESS),
        )
    return videos


def _rounded(value: Optional[float]) -> Optional[float]:
    """Round a float to DECIMALS places, keeping None.

    Args:
        value: A float or None.

    Returns:
        The rounded float, or None.
    """
    return None if value is None else round(value, DECIMALS) + 0.0


def summarize(
    rows: Sequence[Mapping[str, str]], videos: Sequence[SampleVideo], placements: Mapping[str, Placement]
) -> Dict[str, Any]:
    """Describe the diversity of one group of sample videos.

    Args:
        rows: The observation rows of the group's videos, labeled and unlabeled.
        videos: The group's sample videos.
        placements: ``{code: Placement}`` from place_codes, holding every labeled
            code of rows.

    Returns:
        ``videos`` and ``sites`` (how many of each), ``sightings`` (labeled rows,
        UNKN included), ``review`` (Review rows), ``unknown`` (UNKN rows),
        ``species``, ``genus``, ``family``, and ``order`` (distinct taxa seen,
        UNKN left out), ``phases`` (species seen per phase), ``shannon``,
        ``simpson``, and ``chao1`` (None without a sighting), ``counts`` and
        ``video_counts`` (sightings and videos per code, UNKN included, in code
        order), and ``accumulation`` (``{"videos": m, "species": E[S(m)]}`` for
        m = 1 to the number of videos). Floats have DECIMALS decimals.
    """
    labeled = [row for row in rows if row[LABEL_STATUS_COLUMN] == LABELED]
    counts = Counter(row["SpeciesCode"] for row in labeled)
    video_counts = Counter(code for _key, code in {(row["S3Key"], row["SpeciesCode"]) for row in labeled})
    taxa = sorted(code for code in counts if code != UNKNOWN_CODE)
    per_species = [counts[code] for code in taxa]
    seen = [placements[code] for code in taxa]
    curve = mao_tau([video_counts[code] for code in taxa], len(videos))
    return {
        "videos": len(videos),
        "sites": len({video.site for video in videos}),
        "sightings": len(labeled),
        "review": len(rows) - len(labeled),
        "unknown": counts.get(UNKNOWN_CODE, 0),
        "species": len(taxa),
        "genus": len({item.genus for item in seen if item.genus}),
        "family": len({item.family for item in seen if item.family}),
        "order": len({item.order for item in seen if item.order}),
        "phases": {phase: sum(1 for item in seen if item.phase == phase) for phase in PHASES},
        "shannon": _rounded(shannon(per_species)),
        "simpson": _rounded(simpson(per_species)),
        "chao1": _rounded(chao1(per_species)),
        "counts": {code: counts[code] for code in sorted(counts)},
        "video_counts": {code: video_counts[code] for code in sorted(video_counts)},
        "accumulation": [{"videos": index, "species": _rounded(value)} for index, value in enumerate(curve, start=1)],
    }


def _reference(placements: Sequence[Placement]) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    """Count the reference list at each rank and per phase.

    Args:
        placements: The species list placed, without UNKN.

    Returns:
        ``({"species", "genus", "family", "order"}, [{"part", "total"} per phase])``.
    """
    reference = {
        "species": len(placements),
        "genus": len({item.genus for item in placements if item.genus}),
        "family": len({item.family for item in placements if item.family}),
        "order": len({item.order for item in placements if item.order}),
    }
    phases = [{"part": phase, "total": sum(1 for item in placements if item.phase == phase)} for phase in PHASES]
    return reference, phases


def diversity_payload(
    rows: Sequence[Mapping[str, str]],
    screened: Sequence[Mapping[str, str]],
    species: Sequence[Species],
    taxonomy: Mapping[str, Taxon],
    site_names: Mapping[str, str],
) -> Dict[str, Any]:
    """Build the whole ``GET /api/diversity`` answer.

    Args:
        rows: Every observation row, labeled and unlabeled.
        screened: The rows of videos_screened.csv.
        species: The species list, custom species included.
        taxonomy: ``{genus: Taxon}`` from load_taxonomy.
        site_names: ``{site code: site name}``, for the site of a video with no rows.

    Returns:
        ``reference`` (the species list without UNKN, counted at each rank),
        ``phases`` (``{"part", "total"}`` per phase), ``taxa`` (``{"code", "name",
        "part", "genus", "family", "order", "class"}`` for the species list in
        its order, then any other code the rows hold; ``part`` is the phase),
        ``all`` (the summarize answer of every sample video), ``sites`` (one per
        site, with ``site``, sorted by site), and ``videos`` (one per sample
        video, with ``key``, ``name``, ``site``, ``transect``, ``date``, and
        ``status``, sorted by site, date, transect, and name).

    Raises:
        ValueError: Starting with ``species``, ``taxonomy``, or ``site_names``
            when the argument has the wrong type.
    """
    if not isinstance(taxonomy, Mapping):
        raise ValueError(f"taxonomy: expected a mapping of genus to Taxon, got {type(taxonomy).__name__}")
    listed = species_by_code(species)
    placements = place_codes(rows, species, taxonomy)
    videos = sample_videos(rows, screened, site_names)
    rows_by_key: Dict[str, List[Mapping[str, str]]] = {}
    for row in rows:
        rows_by_key.setdefault(row["S3Key"], []).append(row)
    by_site: Dict[str, List[SampleVideo]] = {}
    for video in videos.values():
        by_site.setdefault(video.site, []).append(video)
    reference, phases = _reference([placements[code] for code in listed if code != UNKNOWN_CODE])
    sites = []
    for site in sorted(by_site):
        group = by_site[site]
        site_rows = [row for video in group for row in rows_by_key.get(video.key, [])]
        sites.append({"site": site, **summarize(site_rows, group, placements)})
    ordered = sorted(videos.values(), key=lambda item: (item.site, item.date, item.transect, item.name))
    return {
        "reference": reference,
        "phases": phases,
        "taxa": [
            {
                "code": item.code,
                "name": item.name,
                "part": item.phase,
                "genus": item.genus,
                "family": item.family,
                "order": item.order,
                "class": item.class_name,
            }
            for item in placements.values()
        ],
        "all": summarize(rows, list(videos.values()), placements),
        "sites": sites,
        "videos": [
            {
                "key": video.key,
                "name": video.name,
                "site": video.site,
                "transect": video.transect,
                "date": video.date,
                "status": video.status,
                **summarize(rows_by_key.get(video.key, []), [video], placements),
            }
            for video in ordered
        ],
    }
