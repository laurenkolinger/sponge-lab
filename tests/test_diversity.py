"""Tests for screener.diversity: the indices, the accumulation curve, the taxonomy, and the Diversity answer."""

import csv
import importlib.util
import math
from pathlib import Path

import pytest

from screener import diversity
from screener.diversity import (
    Taxon,
    chao1,
    diversity_payload,
    load_taxonomy,
    mao_tau,
    phase_of,
    shannon,
    simpson,
)
from screener.species import Species, load_species
from tests.store_helpers import SPECIES as STORE_SPECIES
from tests.store_helpers import add_sighting, make_store

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

# The diversity tests bring their own species, sites, and taxonomy, so edits to
# the shipped config files cannot change what these tests expect.
SPECIES = [
    Species(code="ACAU", name="Aplysina cauliformis", part="1", default_pin="1"),
    Species(code="AFUL", name="Aplysina fulva", part="2", default_pin="2"),
    Species(code="CDEL", name="Cliona delitrix", part="1", default_pin="3"),
    Species(code="XMUT", name="Xestospongia muta", part="3", default_pin=""),
    Species(code="CINA", name="Cinachyrella", part="", default_pin=""),
    Species(code="UNKN", name="Unknown sponge", part="", default_pin=""),
]
TAXONOMY = {
    "Aplysina": Taxon("Aplysina", "Aplysinidae", "Verongiida", "Demospongiae", "131975"),
    "Cliona": Taxon("Cliona", "Clionaidae", "Clionaida", "Demospongiae", "132026"),
    "Xestospongia": Taxon("Xestospongia", "Petrosiidae", "Haplosclerida", "Demospongiae", "131849"),
}
SITES = {"FLC": "Flat Cay", "BIT": "Buck Island"}

KEY_FLC_T1 = "TCRMP_video_ondeck/2024Annual/TCRMP20241022_video_FLC_T1.MP4"
KEY_FLC_T2 = "TCRMP_video_ondeck/2024Annual/TCRMP20241022_video_FLC_T2.MP4"
KEY_BIT_T1 = "TCRMP_video_ondeck/2023Annual/TCRMP20230801_video_BIT_T1.MP4"
KEY_BIT_DONE = "TCRMP_video_ondeck/2023Annual/TCRMP20230801_video_BIT_T3.MP4"
KEY_ODD = "TCRMP_video_ondeck/misc/MVI_0203.MOV"

SITE_OF = {KEY_FLC_T1: "Flat Cay", KEY_FLC_T2: "Flat Cay", KEY_BIT_T1: "Buck Island", KEY_BIT_DONE: "Buck Island", KEY_ODD: ""}
TRANSECT_OF = {KEY_FLC_T1: "T1", KEY_FLC_T2: "T2", KEY_BIT_T1: "T1", KEY_BIT_DONE: "T3", KEY_ODD: ""}
NAMES = {item.code: item.name for item in SPECIES}


def row(key, code=None, name=None):
    """Build one observation row the way the store reads it: labeled with a code, or a Review point without."""
    return {
        "S3Key": key,
        "FileName": key.rsplit("/", 1)[-1],
        "Site": SITE_OF[key],
        "Transect": TRANSECT_OF[key],
        "SpeciesCode": code or "",
        "Sponge Type": "" if code is None else name or NAMES[code],
        "LabelStatus": "unlabeled" if code is None else "labeled",
    }


def screened(key, status):
    """Build one videos_screened.csv row."""
    return {"S3Key": key, "FileName": key.rsplit("/", 1)[-1], "Status": status}


def payload(rows, screened_rows=(), species=SPECIES, taxonomy=TAXONOMY, sites=SITES):
    """Run diversity_payload with the test species, taxonomy, and sites."""
    return diversity_payload(list(rows), list(screened_rows), species, taxonomy, sites)


# ----- the indices -----


def test_shannon_matches_a_hand_worked_example():
    # Counts 2, 1, 1: N = 4, shares 0.5, 0.25, 0.25.
    # H' = -(0.5 ln 0.5 + 2 * 0.25 ln 0.25) = 0.5 ln 2 + 0.5 ln 4 = 0.346574 + 0.693147 = 1.039721.
    assert shannon([2, 1, 1]) == pytest.approx(1.0397207708)
    assert shannon([2, 1, 1]) == pytest.approx(1.5 * math.log(2))


def test_shannon_of_one_species_is_zero_and_of_nothing_is_none():
    assert shannon([7]) == 0.0 and math.copysign(1.0, shannon([7])) == 1.0
    assert shannon([]) is None
    assert shannon([0, 0]) is None
    assert shannon([0, 2, 1, 1, 0]) == pytest.approx(shannon([2, 1, 1]))


def test_simpson_matches_a_hand_worked_example():
    # Counts 2, 1, 1: D = 0.5^2 + 0.25^2 + 0.25^2 = 0.25 + 0.0625 + 0.0625 = 0.375, so 1 - D = 0.625.
    assert simpson([2, 1, 1]) == pytest.approx(0.625)
    # Counts 3, 1: D = 0.75^2 + 0.25^2 = 0.5625 + 0.0625 = 0.625, so 1 - D = 0.375.
    assert simpson((3, 1)) == pytest.approx(0.375)
    assert simpson([4]) == 0.0
    assert simpson([]) is None


def test_chao1_matches_a_hand_worked_example():
    # Counts 2, 1, 1: S = 3, F1 = 2, F2 = 1. Chao1 = 3 + 2 * 1 / (2 * (1 + 1)) = 3 + 0.5 = 3.5.
    assert chao1([2, 1, 1]) == pytest.approx(3.5)


def test_chao1_with_no_doubletons_uses_the_bias_corrected_form():
    # Counts 1, 1, 1, 3: S = 4, F1 = 3, F2 = 0. Chao1 = 4 + 3 * 2 / (2 * (0 + 1)) = 4 + 3 = 7.
    assert chao1([1, 1, 1, 3]) == pytest.approx(7.0)
    # Singletons only, counts 1, 1: S = 2, F1 = 2, F2 = 0. Chao1 = 2 + 2 * 1 / 2 = 3.
    assert chao1([1, 1]) == pytest.approx(3.0)
    # One singleton: S = 1, F1 = 1, F2 = 0. Chao1 = 1 + 1 * 0 / 2 = 1.
    assert chao1([1]) == pytest.approx(1.0)


def test_chao1_without_singletons_is_the_observed_richness_and_none_without_sightings():
    assert chao1([5, 2]) == 2.0
    assert chao1([]) is None
    assert chao1([0]) is None


@pytest.mark.parametrize("function", [shannon, simpson, chao1])
@pytest.mark.parametrize("counts", [None, "12", {"ACAU": 1}, [1, -1], [1, 1.5], [True], ["2"]])
def test_indices_refuse_counts_that_are_not_whole_numbers(function, counts):
    with pytest.raises(ValueError) as caught:
        function(counts)
    assert str(caught.value).startswith("counts:")


# ----- the accumulation curve -----


def test_mao_tau_matches_a_hand_worked_example():
    # H = 3 samples; taxon A is in 3 of them, taxon B in 1.
    # m = 1: A gives 1 - C(0,1)/C(3,1) = 1; B gives 1 - C(2,1)/C(3,1) = 1 - 2/3 = 1/3. E = 4/3.
    # m = 2: A gives 1; B gives 1 - C(2,2)/C(3,2) = 1 - 1/3 = 2/3, the product (2/3)(1/2) = 1/3. E = 5/3.
    # m = 3: A gives 1; B gives 1 - C(2,3)/C(3,3) = 1 - 0 = 1. E = 2.
    assert mao_tau([3, 1], 3) == pytest.approx([4 / 3, 5 / 3, 2.0])


def test_mao_tau_ends_at_the_observed_richness_and_starts_at_the_mean_per_sample():
    incidences = [5, 1, 2, 2, 7, 3]
    samples = 9
    curve = mao_tau(incidences, samples)
    assert len(curve) == samples
    assert curve[-1] == pytest.approx(len(incidences))
    assert curve[0] == pytest.approx(sum(incidences) / samples)
    assert all(later >= earlier for earlier, later in zip(curve, curve[1:]))


def test_mao_tau_handles_thousands_of_samples_without_big_numbers():
    curve = mao_tau([1, 2500, 5000], 5000)
    assert len(curve) == 5000
    assert curve[-1] == pytest.approx(3.0)
    assert curve[0] == pytest.approx(7501 / 5000)
    assert all(math.isfinite(value) for value in curve)


def test_mao_tau_of_no_samples_is_empty_and_an_unseen_taxon_adds_nothing():
    assert mao_tau([], 0) == []
    assert mao_tau([0, 0], 2) == [0.0, 0.0]
    assert mao_tau([0, 2], 2) == pytest.approx([1.0, 1.0])


@pytest.mark.parametrize(
    "incidences, samples, starts_with",
    [
        ([1], -1, "samples:"),
        ([1], 2.0, "samples:"),
        ([1], True, "samples:"),
        ([3], 2, "incidences:"),
        ([-1], 2, "incidences:"),
        ("1", 2, "incidences:"),
    ],
)
def test_mao_tau_refuses_bad_input(incidences, samples, starts_with):
    with pytest.raises(ValueError) as caught:
        mao_tau(incidences, samples)
    assert str(caught.value).startswith(starts_with)


# ----- the taxonomy -----


def write_taxonomy(tmp_path, text):
    """Write a taxonomy.csv and return its path."""
    path = tmp_path / "taxonomy.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_shipped_taxonomy_loads_and_covers_every_genus_of_the_species_list():
    taxonomy = load_taxonomy(CONFIG_DIR / "taxonomy.csv")
    assert len(taxonomy) == 29
    assert taxonomy["Aplysina"] == Taxon("Aplysina", "Aplysinidae", "Verongiida", "Demospongiae", "131975")
    assert taxonomy["Plakortis"].class_name == "Homoscleromorpha"
    genera = {item.name.split()[0] for item in load_species(CONFIG_DIR / "species.csv") if item.code != "UNKN"}
    assert genera <= set(taxonomy)


def test_taxonomy_allows_blank_ranks_and_a_header_only_file(tmp_path):
    path = write_taxonomy(tmp_path, "Genus,Family,Order,Class,AphiaID\nOddgenus,,,,\n")
    assert load_taxonomy(path) == {"Oddgenus": Taxon("Oddgenus", "", "", "", "")}
    assert load_taxonomy(write_taxonomy(tmp_path, "Genus,Family,Order,Class,AphiaID\n")) == {}


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("Genus,Family,Order,Class\nAgelas,Agelasidae,Agelasida,Demospongiae\n", "AphiaID"),
        ("Genus,Family,Order,Class,AphiaID\nAgelas,Agelasidae,Agelasida,Demospongiae,1\nAgelas,X,Y,Z,2\n", "line 3"),
        ("Genus,Family,Order,Class,AphiaID\nagelas,Agelasidae,Agelasida,Demospongiae,1\n", "capitalized"),
        ("Genus,Family,Order,Class,AphiaID\nAgelas clathrodes,Agelasidae,Agelasida,Demospongiae,1\n", "capitalized"),
        ("Genus,Family,Order,Class,AphiaID\n,Agelasidae,Agelasida,Demospongiae,1\n", "Genus"),
        ("Genus,Family,Order,Class,AphiaID\nAgelas,Agelasidae,Agelasida,Demospongiae,A131771\n", "AphiaID"),
        ("Genus,Family,Order,Class,AphiaID\nAgelas,=cmd(),Agelasida,Demospongiae,1\n", "formula"),
        ("Genus,Family,Order,Class,AphiaID\nAgelas,Agelasidae,Agelasida,Demospongiae,1,extra\n", "cells"),
        ("", "empty"),
    ],
)
def test_malformed_taxonomy_raises_with_the_path(tmp_path, text, fragment):
    path = write_taxonomy(tmp_path, text)
    with pytest.raises(ValueError) as caught:
        load_taxonomy(path)
    assert str(path) in str(caught.value)
    assert fragment in str(caught.value)


def test_taxonomy_that_is_not_utf8_raises_with_the_path(tmp_path):
    path = tmp_path / "taxonomy.csv"
    path.write_bytes(b"Genus,Family,Order,Class,AphiaID\nAg\xe9las,A,B,C,1\n")
    with pytest.raises(ValueError, match="taxonomy.csv"):
        load_taxonomy(path)


def test_missing_taxonomy_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError, match="taxonomy"):
        load_taxonomy(tmp_path / "taxonomy.csv")


# ----- phases -----


def test_phase_follows_the_guide_part_and_puts_added_species_in_phase_3():
    assert [phase_of(item) for item in SPECIES] == ["1", "2", "1", "3", "3", ""]


# ----- the Diversity answer -----


def test_empty_store_gives_zeros_and_no_indices():
    answer = payload([])
    assert answer["reference"] == {"species": 5, "genus": 4, "family": 3, "order": 3}
    assert answer["phases"] == [{"part": "1", "total": 2}, {"part": "2", "total": 1}, {"part": "3", "total": 2}]
    assert answer["all"] == {
        "videos": 0,
        "sites": 0,
        "sightings": 0,
        "review": 0,
        "unknown": 0,
        "species": 0,
        "genus": 0,
        "family": 0,
        "order": 0,
        "phases": {"1": 0, "2": 0, "3": 0},
        "shannon": None,
        "simpson": None,
        "chao1": None,
        "counts": {},
        "video_counts": {},
        "accumulation": [],
    }
    assert answer["sites"] == [] and answer["videos"] == []


def test_taxa_list_every_species_with_phase_and_ranks():
    taxa = payload([])["taxa"]
    assert [item["code"] for item in taxa] == ["ACAU", "AFUL", "CDEL", "XMUT", "CINA", "UNKN"]
    assert taxa[0] == {
        "code": "ACAU",
        "name": "Aplysina cauliformis",
        "part": "1",
        "genus": "Aplysina",
        "family": "Aplysinidae",
        "order": "Verongiida",
        "class": "Demospongiae",
    }
    cina = taxa[4]
    assert (cina["part"], cina["genus"], cina["family"], cina["order"], cina["class"]) == ("3", "Cinachyrella", "", "", "")
    unknown = taxa[5]
    assert (unknown["part"], unknown["genus"], unknown["family"]) == ("", "", "")


def test_unknown_only_rows_count_as_sightings_but_not_as_species():
    answer = payload([row(KEY_FLC_T1, "UNKN"), row(KEY_FLC_T1, "UNKN"), row(KEY_FLC_T1)])
    summary = answer["all"]
    assert (summary["videos"], summary["sites"], summary["sightings"], summary["review"], summary["unknown"]) == (1, 1, 2, 1, 2)
    assert (summary["species"], summary["genus"], summary["family"], summary["order"]) == (0, 0, 0, 0)
    assert (summary["shannon"], summary["simpson"], summary["chao1"]) == (None, None, None)
    assert summary["counts"] == {"UNKN": 2} and summary["video_counts"] == {"UNKN": 1}
    assert summary["accumulation"] == [{"videos": 1, "species": 0.0}]


def test_one_video_gives_the_same_summary_at_every_scope():
    rows = [row(KEY_FLC_T1, "ACAU"), row(KEY_FLC_T1, "ACAU"), row(KEY_FLC_T1, "CDEL"), row(KEY_FLC_T1, "AFUL")]
    answer = payload(rows, [screened(KEY_FLC_T1, "done")])
    everything = answer["all"]
    site = dict(answer["sites"][0])
    video = dict(answer["videos"][0])
    assert site.pop("site") == "Flat Cay"
    for field in ("key", "name", "site", "transect", "date", "status"):
        video.pop(field)
    assert everything == site == video
    # Counts 2, 1, 1: H' = 1.039721 rounds to 1.04, 1 - D = 0.625, Chao1 = 3 + 2 * 1 / (2 * 2) = 3.5.
    assert (everything["shannon"], everything["simpson"], everything["chao1"]) == (1.04, 0.625, 3.5)
    assert everything["accumulation"] == [{"videos": 1, "species": 3.0}]
    assert everything["phases"] == {"1": 2, "2": 1, "3": 0}
    assert (everything["species"], everything["genus"], everything["family"], everything["order"]) == (3, 2, 2, 2)


def test_whole_answer_matches_a_hand_worked_survey():
    rows = [
        row(KEY_FLC_T1, "ACAU"),
        row(KEY_FLC_T1, "ACAU"),
        row(KEY_FLC_T1, "CDEL"),
        row(KEY_FLC_T1),
        row(KEY_FLC_T2, "ACAU"),
        row(KEY_FLC_T2, "XMUT"),
        row(KEY_FLC_T2, "UNKN"),
        row(KEY_BIT_T1, "CINA"),
        row(KEY_BIT_T1),
    ]
    log = [screened(KEY_FLC_T1, "done"), screened(KEY_BIT_DONE, "done"), screened(KEY_ODD, "in progress")]
    answer = payload(rows, log)
    everything = answer["all"]
    # Sample videos: FLC T1, FLC T2, BIT T1 (rows) and BIT T3 (done, no rows). KEY_ODD is in progress with no rows.
    assert (everything["videos"], everything["sites"]) == (4, 2)
    assert (everything["sightings"], everything["review"], everything["unknown"]) == (7, 2, 1)
    assert everything["counts"] == {"ACAU": 3, "CDEL": 1, "CINA": 1, "UNKN": 1, "XMUT": 1}
    assert everything["video_counts"] == {"ACAU": 2, "CDEL": 1, "CINA": 1, "UNKN": 1, "XMUT": 1}
    # Species ACAU, CDEL, CINA, XMUT; genera Aplysina, Cliona, Cinachyrella, Xestospongia; Cinachyrella has
    # no family or order in the test taxonomy, so 3 families and 3 orders.
    assert (everything["species"], everything["genus"], everything["family"], everything["order"]) == (4, 4, 3, 3)
    assert everything["phases"] == {"1": 2, "2": 0, "3": 2}
    # Counts 3, 1, 1, 1 (N = 6): H' = -(0.5 ln 0.5 + 3 * (1/6) ln (1/6)) = 0.346574 + 0.895880 = 1.242453.
    # 1 - D = 1 - (0.25 + 3 / 36) = 1 - 0.333333 = 0.666667. Chao1: S = 4, F1 = 3, F2 = 0, so 4 + 3 * 2 / 2 = 7.
    assert (everything["shannon"], everything["simpson"], everything["chao1"]) == (1.242, 0.667, 7.0)
    # H = 4 samples with incidences ACAU 2, CDEL 1, CINA 1, XMUT 1.
    # m = 1: (2 + 1 + 1 + 1) / 4 = 1.25. m = 2: ACAU 1 - C(2,2)/C(4,2) = 5/6; each singleton 1 - C(3,2)/C(4,2) = 1/2;
    # 5/6 + 3/2 = 2.333. m = 3: ACAU 1 - 0 = 1; each singleton 1 - C(3,3)/C(4,3) = 3/4; 1 + 9/4 = 3.25. m = 4: 4.
    assert everything["accumulation"] == [
        {"videos": 1, "species": 1.25},
        {"videos": 2, "species": 2.333},
        {"videos": 3, "species": 3.25},
        {"videos": 4, "species": 4.0},
    ]
    assert [site["site"] for site in answer["sites"]] == ["Buck Island", "Flat Cay"]
    buck, flat = answer["sites"]
    assert (buck["videos"], buck["sightings"], buck["review"], buck["species"], buck["counts"]) == (2, 1, 1, 1, {"CINA": 1})
    # Buck Island: CINA in 1 of 2 samples, so E[S(1)] = 0.5 and E[S(2)] = 1.
    assert buck["accumulation"] == [{"videos": 1, "species": 0.5}, {"videos": 2, "species": 1.0}]
    assert (flat["videos"], flat["sightings"], flat["unknown"], flat["species"]) == (2, 6, 1, 3)
    assert [video["key"] for video in answer["videos"]] == [KEY_BIT_T1, KEY_BIT_DONE, KEY_FLC_T1, KEY_FLC_T2]
    done = answer["videos"][1]
    assert {field: done[field] for field in ("name", "site", "transect", "date", "status")} == {
        "name": "TCRMP20230801_video_BIT_T3.MP4",
        "site": "Buck Island",
        "transect": "T3",
        "date": "2023-08-01",
        "status": "done",
    }
    assert (done["sightings"], done["species"], done["shannon"], done["accumulation"]) == (0, 0, None, [{"videos": 1, "species": 0.0}])
    assert answer["videos"][0]["status"] == "in progress"
    assert answer["videos"][2]["status"] == "done"


def test_a_genus_missing_from_the_taxonomy_counts_at_genus_rank_only():
    answer = payload([row(KEY_FLC_T1, "ACAU"), row(KEY_FLC_T1, "XMUT")], taxonomy={"Aplysina": TAXONOMY["Aplysina"]})
    summary = answer["all"]
    assert (summary["species"], summary["genus"], summary["family"], summary["order"]) == (2, 2, 1, 1)
    assert answer["reference"] == {"species": 5, "genus": 4, "family": 1, "order": 1}
    xmut = next(item for item in answer["taxa"] if item["code"] == "XMUT")
    assert (xmut["genus"], xmut["family"], xmut["order"], xmut["class"]) == ("Xestospongia", "", "", "")


def test_rows_without_a_site_fall_under_unknown_site_and_odd_names_have_no_date():
    answer = payload([row(KEY_ODD, "ACAU"), row(KEY_FLC_T1, "ACAU")])
    assert [site["site"] for site in answer["sites"]] == ["Flat Cay", "Unknown site"]
    odd = answer["videos"][-1]
    assert (odd["site"], odd["transect"], odd["date"], odd["name"]) == ("Unknown site", "", "", "MVI_0203.MOV")


def test_done_video_without_rows_takes_its_site_from_the_site_names_or_its_code():
    log = [screened(KEY_BIT_DONE, "done")]
    assert payload([], log)["videos"][0]["site"] == "Buck Island"
    assert payload([], log, sites={})["videos"][0]["site"] == "BIT"
    odd = payload([], [screened(KEY_ODD, "done")])["videos"][0]
    assert (odd["site"], odd["date"], odd["transect"]) == ("Unknown site", "", "")


def test_a_code_outside_the_species_list_is_named_after_its_rows():
    answer = payload([row(KEY_FLC_T1, "ZOOX", name="Zooxanthella reef")])
    extra = answer["taxa"][-1]
    assert extra == {"code": "ZOOX", "name": "Zooxanthella reef", "part": "", "genus": "Zooxanthella", "family": "", "order": "", "class": ""}
    assert answer["all"]["species"] == 1 and answer["all"]["phases"] == {"1": 0, "2": 0, "3": 0}
    assert answer["reference"]["species"] == 5


def test_hostile_site_names_pass_through_unchanged():
    hostile = 'Reef "A", <script>alert(1)</script> & co'
    rows = [{**row(KEY_FLC_T1, "ACAU"), "Site": hostile}, {**row(KEY_FLC_T2, "AFUL"), "Site": "Flat Cay"}]
    answer = payload(rows)
    assert [site["site"] for site in answer["sites"]] == ["Flat Cay", hostile]
    assert answer["videos"][1]["site"] == hostile


def test_floats_are_rounded_to_three_decimals():
    rows = [row(KEY_FLC_T1, code) for code in ("ACAU", "ACAU", "ACAU", "AFUL", "CDEL", "CDEL", "XMUT")]
    rows += [row(KEY_FLC_T2, "ACAU"), row(KEY_BIT_T1, "XMUT"), row(KEY_BIT_T1, "CDEL")]
    answer = payload(rows)
    values = [answer["all"][field] for field in ("shannon", "simpson", "chao1")]
    values += [point["species"] for point in answer["all"]["accumulation"]]
    assert all(value == round(value, 3) for value in values)
    # Incidences ACAU 2, AFUL 1, CDEL 2, XMUT 2 over 3 videos: E[S(1)] = 7 / 3 = 2.333.
    assert answer["all"]["accumulation"][0]["species"] == 2.333
    # Counts 4, 1, 3, 2 (N = 10): H' = 0.4 ln 2.5 + 0.1 ln 10 + 0.3 ln (10/3) + 0.2 ln 5
    # = 0.366516 + 0.230259 + 0.361192 + 0.321888 = 1.279855, which rounds to 1.28.
    assert answer["all"]["shannon"] == 1.28


@pytest.mark.parametrize(
    "arguments, starts_with",
    [
        (("not a list", TAXONOMY, SITES), "species:"),
        ((SPECIES, ["Aplysina"], SITES), "taxonomy:"),
        ((SPECIES, TAXONOMY, ["FLC"]), "site_names:"),
    ],
)
def test_diversity_payload_refuses_wrong_argument_types(arguments, starts_with):
    with pytest.raises(ValueError) as caught:
        diversity_payload([], [], *arguments)
    assert str(caught.value).startswith(starts_with)


def test_answer_from_a_real_store_counts_its_rows(tmp_path):
    store = make_store(tmp_path)
    add_sighting(store, species_code="ACAU")
    add_sighting(store, species_code="ACAU", time_seconds=10.0)
    add_sighting(store, species_code="CDEL", time_seconds=20.0)
    add_sighting(store, species_code=None, time_seconds=30.0)
    add_sighting(store, key=KEY_BIT_T1, species_code="XMUT")
    store.mark_opened(KEY_BIT_DONE, "LO", ["ACAU"])
    store.mark_done(KEY_BIT_DONE, True, "LO", ["ACAU"])
    answer = diversity_payload(store.rows(), store.screened(), STORE_SPECIES, TAXONOMY, SITES)
    summary = answer["all"]
    assert (summary["videos"], summary["sites"], summary["sightings"], summary["review"]) == (3, 2, 4, 1)
    assert summary["counts"] == {"ACAU": 2, "CDEL": 1, "XMUT": 1}
    assert [video["site"] for video in answer["videos"]] == ["Buck Island", "Buck Island", "Flat Cay"]
    assert answer["videos"][-1]["date"] == "2024-10-22"


def test_module_exposes_the_planned_interface():
    assert {"load_taxonomy", "shannon", "simpson", "chao1", "mao_tau", "summarize", "diversity_payload"} <= set(dir(diversity))
    with open(CONFIG_DIR / "taxonomy.csv", encoding="utf-8", newline="") as handle:
        assert next(csv.reader(handle)) == ["Genus", "Family", "Order", "Class", "AphiaID"]


# ----- tools/fetch_taxonomy.py, without the network -----


def load_tool():
    """Import tools/fetch_taxonomy.py, which is a script and not a package module."""
    spec = importlib.util.spec_from_file_location("fetch_taxonomy", PROJECT_ROOT / "tools" / "fetch_taxonomy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worms_record(name, status="accepted", kingdom="Animalia", rank="Genus", aphia_id=131975, **ranks):
    """Build one AphiaRecord the way the WoRMS REST service answers it."""
    record = {
        "AphiaID": aphia_id,
        "scientificname": name,
        "status": status,
        "kingdom": kingdom,
        "rank": rank,
        "class": "Demospongiae",
        "order": "Verongiida",
        "family": "Aplysinidae",
        "genus": name,
    }
    record.update(ranks)
    return record


def test_fetch_tool_keeps_the_accepted_animal_genus():
    tool = load_tool()
    records = [
        worms_record("Aplysina", status="unaccepted", aphia_id=1),
        worms_record("Aplysina", kingdom="Plantae", aphia_id=2),
        worms_record("Aplysina", rank="Subgenus", aphia_id=3),
        worms_record("Aplysina"),
    ]
    assert tool.accepted_genus(records, "Aplysina") == {
        "Genus": "Aplysina",
        "Family": "Aplysinidae",
        "Order": "Verongiida",
        "Class": "Demospongiae",
        "AphiaID": "131975",
    }
    blank = tool.accepted_genus([worms_record("Oddgenus", family=None, order=None)], "Oddgenus")
    assert (blank["Family"], blank["Order"], blank["Class"]) == ("", "", "Demospongiae")


@pytest.mark.parametrize(
    "records, fragment",
    [
        (None, "found 0"),
        ([], "found 0"),
        ([worms_record("Aplysina", status="unaccepted")], "found 0"),
        ([worms_record("Aplysinae")], "found 0"),
        ([worms_record("Aplysina"), worms_record("Aplysina", aphia_id=9)], "found 2"),
        ({"AphiaID": 1}, "expected a list"),
        (["Aplysina"], "expected a list"),
    ],
)
def test_fetch_tool_refuses_answers_without_exactly_one_accepted_genus(records, fragment):
    with pytest.raises(ValueError) as caught:
        load_tool().accepted_genus(records, "Aplysina")
    assert str(caught.value).startswith("Aplysina:") and fragment in str(caught.value)


def test_fetch_tool_lists_the_species_genera_and_the_extra_ones(tmp_path):
    tool = load_tool()
    species_file = tmp_path / "species.csv"
    species_file.write_text(
        "Code,ScientificName,GuidePart,DefaultPin\nACAU,Aplysina cauliformis,1,1\nAFUL,Aplysina fulva,2,2\n"
        "UNKN,Unknown sponge,,\n",
        encoding="utf-8",
    )
    assert tool.genera_to_fetch(species_file, ["Geodia", "Aplysina"]) == ["Aplysina", "Geodia"]
    with pytest.raises(ValueError, match="^genus:"):
        tool.genera_to_fetch(species_file, ["geodia"])


def test_fetch_tool_rebuilds_the_shipped_file_byte_for_byte(tmp_path):
    tool = load_tool()
    shipped = load_taxonomy(CONFIG_DIR / "taxonomy.csv")

    def fetch(genus):
        """Answer the way WoRMS would, from the shipped table."""
        taxon = shipped[genus]
        ranks = {"family": taxon.family, "order": taxon.order, "class": taxon.class_name}
        return [worms_record(genus, aphia_id=int(taxon.aphia_id), **ranks), worms_record(genus, status="unaccepted")]

    extra = sorted(set(shipped) - set(tool.genera_to_fetch(CONFIG_DIR / "species.csv", [])))
    rows = tool.build_rows(tool.genera_to_fetch(CONFIG_DIR / "species.csv", extra), fetch)
    target = tmp_path / "taxonomy.csv"
    tool.write_rows(target, rows)
    assert target.read_bytes() == (CONFIG_DIR / "taxonomy.csv").read_bytes()
    assert load_taxonomy(target) == shipped
