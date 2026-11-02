"""Tests: the PDF's Case A and Case B, plus edge cases from the real data.
Run from the project folder:  python -m pytest -q tests
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from coalesce import coalesce_user, to_row

D = dt.date
RL = "linkedin.com/company/revelio-labs"
NYU = "linkedin.com/company/nyu"


def run(snapshots):
    snaps = []
    for observed in sorted(snapshots):
        rows = [
            to_row(observed, c, u, t, l, d, s, e)
            for (c, u, t, l, d, s, e) in snapshots[observed]
        ]
        snaps.append((observed, rows))
    stats = {"kept": 0, "dropped": 0}
    out = coalesce_user(12345, snaps, stats)
    by_date = {}
    for row in out:
        by_date.setdefault(row[0], []).append(row)
    return by_date


CASE_A = {
    D(2026, 7, 19): [
        (
            "NYU",
            NYU,
            "Research Assistant",
            "New York, NY",
            "Wrapping up NLP research",
            D(2025, 9, 1),
            None,
        ),
        (
            "NYU",
            NYU,
            "TA",
            "NYC",
            "TA for data science 101",
            D(2024, 9, 1),
            D(2025, 6, 1),
        ),
    ],
    D(2026, 9, 1): [
        (
            "Revelio Labs",
            RL,
            "Machine Learning Engineer",
            "New York, NY",
            "Making workforce data more accurate",
            D(2026, 8, 1),
            None,
        ),
        (
            "NYU",
            NYU,
            "Research Assistant",
            "New York, NY",
            "Research on various NLP models",
            D(2025, 9, 1),
            D(2026, 8, 1),
        ),
    ],
    D(2026, 9, 16): [
        (
            "Revelio Labs",
            RL,
            "Machine Learning Engineer",
            "New York, NY",
            "Making workforce data more accurate",
            D(2026, 8, 1),
            None,
        )
    ],
}


def test_case_a_keeps_deleted_positions():
    out = run(CASE_A)
    assert [len(out[d]) for d in sorted(out)] == [2, 3, 3]
    titles = {r[4]: r for r in out[D(2026, 9, 16)]}
    assert set(titles) == {"Machine Learning Engineer", "Research Assistant", "TA"}
    assert titles["Research Assistant"][6] == "Research on various NLP models"
    assert titles["Research Assistant"][8] == D(2026, 8, 1)


def test_case_a_ids_are_stable():
    out = run(CASE_A)
    first = {r[4]: r[9] for r in out[D(2026, 7, 19)]}
    last = {r[4]: r[9] for r in out[D(2026, 9, 16)]}
    assert (
        first["TA"] == last["TA"]
        and first["Research Assistant"] == last["Research Assistant"]
    )


def test_case_b_edit_does_not_duplicate():
    snaps = dict(CASE_A)
    snaps[D(2026, 9, 16)] = [
        ("RL", RL, "MLE", "New York, NY", None, D(2026, 8, 1), None)
    ]
    out = run(snaps)
    last = out[D(2026, 9, 16)]
    assert len(last) == 3
    rl = [r for r in last if r[3] == RL][0]
    assert rl[2] == "RL" and rl[4] == "MLE"  # newest values
    assert rl[6] == "Making workforce data more accurate"  # older description kept
    before = [r for r in out[D(2026, 9, 1)] if r[3] == RL][0]
    assert before[2] == "Revelio Labs"  # no future data leaks back


def test_half_empty_row_matches_existing_job():  # like user 75438999 on 2025-11-16
    out = run(
        {
            D(2025, 1, 1): [
                ("Williams", None, "Intern", None, None, D(2013, 5, 1), D(2013, 8, 1))
            ],
            D(2025, 2, 1): [("Williams", None, None, None, None, None, None)],
        }
    )
    assert len(out[D(2025, 2, 1)]) == 1


def test_promotion_is_a_new_position():  # like user 508914085
    out = run(
        {
            D(2021, 8, 4): [
                (
                    "Digital Natives Content",
                    "linkedin.com/company/dn",
                    "Junior Creative",
                    None,
                    None,
                    D(2020, 1, 1),
                    None,
                )
            ],
            D(2021, 9, 1): [
                (
                    "Digital Natives",
                    "linkedin.com/company/dn",
                    "Creative",
                    None,
                    None,
                    D(2021, 5, 1),
                    None,
                ),
                (
                    "Digital Natives",
                    "linkedin.com/company/dn",
                    "Junior Creative",
                    None,
                    None,
                    D(2020, 1, 1),
                    D(2021, 5, 1),
                ),
            ],
        }
    )
    assert len(out[D(2021, 9, 1)]) == 2


def test_https_url_form_matches():  # 'https://www.' form vs plain form
    out = run(
        {
            D(2024, 1, 1): [
                (
                    "Williams",
                    "linkedin.com/company/williams-company",
                    "Intern",
                    None,
                    None,
                    D(2013, 5, 1),
                    None,
                )
            ],
            D(2024, 2, 1): [
                (
                    "Williams",
                    "https://www.linkedin.com/company/williams-company",
                    "Intern",
                    None,
                    None,
                    D(2013, 5, 1),
                    None,
                )
            ],
        }
    )
    assert len(out[D(2024, 2, 1)]) == 1


def test_placeholder_company_is_null():  # like user 113722842
    out = run(
        {
            D(2021, 1, 1): [(None, None, "Gerente", None, None, D(1989, 1, 1), None)],
            D(2021, 2, 1): [("-", None, "Gerente", None, None, D(1989, 1, 1), None)],
        }
    )
    assert len(out[D(2021, 2, 1)]) == 1 and out[D(2021, 2, 1)][0][2] is None


def test_bad_snapshot_is_dropped():
    out = run(
        {
            D(2025, 1, 1): [
                ("Acme", None, "Engineer", None, None, D(2020, 1, 1), None)
            ],
            D(2025, 2, 1): [
                ("Acme", None, "Engineer", None, None, D(2022, 1, 1), D(2021, 1, 1))
            ],
        }
    )
    assert sorted(out) == [D(2025, 1, 1)]


def test_chinese_title_survives_cleaning():
    out = run(
        {
            D(2025, 1, 1): [("某公司", None, "经理", None, None, D(2020, 1, 1), None)],
            D(2025, 2, 1): [("某公司", None, "经理", None, None, D(2020, 1, 1), None)],
        }
    )
    assert len(out[D(2025, 2, 1)]) == 1


def test_same_day_duplicates_become_one_position():  # P7: 154,506 cases
    out = run(
        {
            D(2025, 1, 1): [
                ("Acme", None, "Engineer", None, None, D(2020, 1, 1), None),
                (
                    "Acme",
                    None,
                    "Engineer",
                    None,
                    "built things",
                    D(2020, 1, 1),
                    D(2024, 6, 1),
                ),
            ]
        }
    )
    assert len(out[D(2025, 1, 1)]) == 1
    assert out[D(2025, 1, 1)][0][8] == D(2024, 6, 1)  # the end date is kept


def test_same_url_different_title_no_dates_stays_separate():
    out = run(
        {
            D(2025, 1, 1): [
                (
                    "Acme",
                    "linkedin.com/company/acme",
                    "Engineer",
                    None,
                    None,
                    None,
                    None,
                )
            ],
            D(2025, 2, 1): [
                (
                    "Acme",
                    "linkedin.com/company/acme",
                    "Sales Manager",
                    None,
                    None,
                    None,
                    None,
                )
            ],
        }
    )
    assert len(out[D(2025, 2, 1)]) == 2
