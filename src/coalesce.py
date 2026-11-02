"""
Revelio Labs Position Coalescing Pipeline

This pipeline combines incomplete profile observations to rebuild each person's work history over time. Since jobs can disappear, change, or
have missing information between scrapes, I use previous observations to keep the work history as complete as possible.

The pipeline has three main steps:

1. Splitting the data

   I use DuckDB to read the Parquet files and split the records into buckets based on user_id. This keeps each person's observations
   together and allows multiple workers to process different users without loading the entire dataset into memory.

2. Rebuilding work histories

   Each worker processes a user's observations from oldest to newest to avoid using information from future observations.

   For each observation, I:
   - Check for corrupted data and skip unreliable snapshots.
   - Compare positions with previously recorded jobs.
   - Assign a new position_id when a new job is identified.
   - Update existing positions using the latest reliable information.
   - Keep previously observed jobs even when they disappear from
     later scrapes.
   - Save all known positions for the current observation date.

   This helps me preserve missing information, avoid duplicate positions, and keep position IDs consistent across observations.

3. Writing the output

   The reconstructed histories are saved as Parquet files, with one row per position for each valid observation date. Each position keeps its
   original position_id, and the asof_ts shows what was known about that position at that time.

All the important design choices I made are marked with # DECISION in the code and explained them in DECISIONS.md.
"""

import argparse
import datetime as dt
import glob
import hashlib
import os
import re
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

# Step 1: Data Cleaning : Before comapring positions, I clean and standardize the text. The same company or job title
# can be written in many ways, so I use regex to extract the meaningful parts and ignore the rest. I also create matching keys for company names, job titles, and URLs
# so that differences in formatting don't affect the comparison. Since the same names appear across multiple observations, I use lru_cache to avoid cleaning the same values repeatedly.

# Decision 5: Handling missing and invalid text
# While exploring the data, I found that "-" appears 32,585 times and "." appears 1,689 times as company names. These are placeholders
# rather than actual company names, so I treat them as missing values. However, short names like EY, HP, and 3M are real company names, and RN is a valid job title. Because of this, I decided to remove
# only known placeholders instead of rejecting text based on its length. This helps me clean the data without losing useful information.

PLACEHOLDERS = {"", "-", "--", ".", "..", "n/a", "na", "none", "null", "nil", "unknown"}

COMPANY_SUFFIXES = frozenset(
    {
        "inc",
        "llc",
        "ltd",
        "limited",
        "plc",
        "corp",
        "corporation",
        "co",
        "company",
        "gmbh",
        "sa",
        "ag",
        "the",
        "and",
        "group",
    }
)
NO_WORDS = frozenset()


def clean(value):
    if value is None:
        return None
    value = str(value).strip()
    return None if value.lower() in PLACEHOLDERS else value


# Since the same company names and job titles appear in different observations, I use caching to avoid cleaning them every time.
# This means Regex only processes each unique value once, which helps reduce repeated work and makes the pipeline faster.
@lru_cache(maxsize=500_000)
def name_key(text, drop_words=NO_WORDS):
    if text is None:
        return None
    words = [w for w in re.findall(r"\w+", text.lower()) if w not in drop_words]
    return "".join(words) or None


@lru_cache(maxsize=500_000)
def acronym(text, drop_words=NO_WORDS):
    if text is None:
        return None
    words = [w for w in re.findall(r"\w+", text.lower()) if w not in drop_words]
    return "".join(w[0] for w in words) if len(words) >= 2 else None


@lru_cache(maxsize=500_000)
def url_key(url):
    if url is None:
        return None
    m = re.search(r"linkedin\.com/(company|school|showcase)/([^/?#\s]+)", url.lower())
    return f"{m.group(1)}/{m.group(2)}" if m else url.lower().strip("/")


def to_row(observed, company, website, title, location, description, start, end):
    r = {
        "company": clean(company),
        "url": clean(website),
        "title": clean(title),
        "location": clean(location),
        "description": clean(description),
        "start": start,
        "end": end,
    }
    r["company_key"] = name_key(r["company"], COMPANY_SUFFIXES)
    r["company_acr"] = acronym(r["company"], COMPANY_SUFFIXES)
    r["url_key"] = url_key(r["url"])
    r["title_key"] = name_key(r["title"])
    r["title_acr"] = acronym(r["title"])
    return r


# Step 2: Identifying Bad Data
# I check for observations with incorrect or unrealistic information so they don't affect the reconstructed work histories.

# Decision 4: Handling unrealistic employment dates
# While inspecting the dataset, I found valid-looking employment dates going back to 1966 and 1979. Because of this, I don't want to reject
# dates simply because they are old. I also found records with employment dates later than the day the profile was observed.
# I will compare these dates with the observation date and check for other inconsistencies before deciding whether
EARLIEST_DATE = dt.date(1940, 1, 1)
MAX_DAYS_AHEAD = 2 * 366


def row_is_empty(r):
    return r["company"] is None and r["title"] is None and r["url"] is None


def row_has_bad_dates(r, observed):
    limit = observed + dt.timedelta(days=MAX_DAYS_AHEAD)
    for d in (r["start"], r["end"]):
        if d is not None and (d < EARLIEST_DATE or d > limit):
            return True
    return r["start"] is not None and r["end"] is not None and r["end"] < r["start"]


def snapshot_is_bad(rows, observed):

    # Decision 3: Handling incorrect dates and incomplete snapshots
    # While exploring the data, I found 2,676 rows where the end date comes before the start date. I decided to avoid using these
    # incorrect records so they don't affect the reconstructed history. I also found that 1.92% of snapshots contain less than half the
    # number of positions a user normally has. I decided to keep these snapshots because having fewer positions doesn't necessarily mean
    # the scrape is corrupted. Since the pipeline carries forward previously observed jobs, missing positions can still appear in the reconstructed history.
    # This helps me preserve useful information without rejecting incomplete snapshots unnecessarily.

    if all(row_is_empty(r) for r in rows):
        return True
    return any(row_has_bad_dates(r, observed) for r in rows)


# Step 3: Matching Positions
# I compare each new observation with the jobs already recorded for that user. I use a points system based on the company, employment
# dates, and job title to decide whether it is the same position.

# Decision 5: Setting the matching threshold
# I decided to start with a matching threshold of 4 points. Since some information may be missing or change between observations,
# I don't want to rely on exact matches for every field.I will test this threshold against real user histories to check whether it correctly matches
# existing positions without combining two different jobs. If the results show too many incorrect matches or duplicates, I will adjust the threshold.

MATCH_THRESHOLD = 4


def company_points(row, old):
    if row["url_key"] and old["url_key"]:
        # If both positions have LinkedIn company URLs, I compare them
        # to check whether they belong to the same company.
        return 4 if row["url_key"] == old["url_key"] else None

    a, b = row["company_key"], old["company_key"]

    if a is None or b is None:
        # If either company name is missing, I can't compare them.
        return 0

    if a == b:
        # The cleaned company names are exactly the same.
        return 3

    if a == old["company_acr"] or b == row["company_acr"]:
        # Check whether one company name is an abbreviation of the other, such as NYU and New York University.
        return 2

    if a.startswith(b) or b.startswith(a):
        # Check whether one company name starts with the other, such as Digital Natives and Digital Natives Content.
        return 1

    # If none of these conditions match, I treat the companies as different.
    return None


def date_points(row, old):
    points = 0

    if row["start"] is not None and old["start"] is not None:
        gap = abs((row["start"] - old["start"]).days)

        # Decision 6: Comparing employment start dates
        # While looking at user 515901977, I noticed that the start date changed by a few months for what appears to be the same job.
        # However, user 508914085 had a new role at the same company about a year later, which looks like a promotion. Because of this, I decided to allow small
        # differences in start dates instead of requiring them to match exactly. Large differences reduce the matching score because they could
        # indicate a separate position.

        if gap == 0:
            # The start dates match exactly, so I add 2 points.
            points += 2

        elif gap <= 62:
            # The dates are within roughly two months of each other, so I add 1 point to allow for possible date corrections.
            points += 1

        elif gap <= 366:
            # The dates differ by up to about a year, which could indicate a different role, so I subtract 1 point.
            points -= 1

        else:
            # The dates are more than a year apart, making it less likely that they describe the same position.
            points -= 3

    if (
        row["end"] is not None
        and old["end"] is not None
        and abs((row["end"] - old["end"]).days) > 366
    ):
        # If the end dates differ by more than a year, I subtract 1 point because the positions may be different.
        points -= 1

    return points


def title_points(row, old):
    a, b = row["title_key"], old["title_key"]

    if a is None or b is None:
        # If either title is missing, I give 0 points because there isn't enough information to compare them. I don't reward or penalize missing information.
        return 0

    if a == b:
        # Both titles match exactly, so I add 2 points.
        return 2

    if a == old["title_acr"] or b == row["title_acr"]:
        # One title is an abbreviation of the other, such as MLE and Machine Learning Engineer.
        return 1

    # Decision 5: Handling different job titles
    # I found 55,857 cases where the same company and start date had different titles. This suggests that titles can change
    # between observations without necessarily being a new job. I decided not to penalize different titles automatically.
    # Instead, I give 0 points and use the company and employment dates to help determine whether the positions match.
    return -1


def match_score(row, position):
    best = None
    for old in position["versions"]:
        c = company_points(row, old)
        if c is None:
            continue
        s = c + date_points(row, old) + title_points(row, old)
        if best is None or s > best:
            best = s
    return best if best is not None else -1000


## Step 4: Coalescing a User's History
FIELDS = ("company", "url", "title", "location", "description", "start", "end")


def position_id(user_id, observed, slot):
    h = hashlib.blake2b(f"{user_id}|{observed}|{slot}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "little") & 0x7FFFFFFFFFFFFFFF


def signature(r):
    return (r["company_key"], r["url_key"], r["title_key"], r["start"], r["end"])


def coalesce_user(user_id, snapshots, stats):
    positions = (
        []
    )  # I keep track of every position found for a user, including its unique position ID, the most recent information about the job, and any previous versions recorded across observations.
    out = []
    for observed, rows in snapshots:
        if snapshot_is_bad(rows, observed):
            stats["dropped"] += 1
            continue
        stats["kept"] += 1
        rows = [r for r in rows if not row_is_empty(r)]

        # Step 1: # Compare each row with known jobs and match the best ones first. Where each job can only match one row in the same snapshot.
        pairs = sorted(
            (
                (match_score(r, p), i, j)
                for i, r in enumerate(rows)
                for j, p in enumerate(positions)
            ),
            reverse=True,
        )
        assigned, taken = {}, set()
        for score, i, j in pairs:
            if score < MATCH_THRESHOLD:
                break
            if i not in assigned and j not in taken:
                assigned[i] = j
                taken.add(j)

        # Step 2: Handle rows that didn't match any known job.
        # Decision 5:  Handling duplicate positions
        # I found 154,506 cases where the same job appeared more than once in a snapshot. About 77% were identical, while the others had differences in end dates, descriptions, or URLs.
        # I need to check for these duplicates before creating new jobs to avoid assigning different IDs to the same position.

        slot = 0
        for i, r in enumerate(rows):
            if i in assigned:
                continue
            # Is this a copy of a job already matched today, with the same start date?
            used_today = {j: rows[k]["start"] for k, j in assigned.items()}
            twins = [
                (match_score(r, positions[j]), j)
                for j, s in used_today.items()
                if r["start"] is None or s is None or s == r["start"]
            ]
            twins = [t for t in twins if t[0] >= MATCH_THRESHOLD]
            if twins:
                assigned[i] = max(twins)[1]
                continue
            # Otherwise it's a job we haven't seen before.
            positions.append(
                {
                    "id": position_id(user_id, observed, slot),
                    "values": dict.fromkeys(FIELDS),
                    "versions": [r],
                }
            )
            slot += 1
            assigned[i] = len(positions) - 1

        # Step 3: Update each job with the latest information.
        # Decision 8: Handling missing and updated values
        # In Case B, the new title "MLE" is used, but the old description is kept because the latest one is missing.I decided to use the newest available values and keep older
        # information whenever the new observation has missing fields.

        for i, r in enumerate(rows):
            p = positions[assigned[i]]
            for f in FIELDS:
                if r[f] is not None:
                    p["values"][f] = r[f]
            if all(signature(v) != signature(r) for v in p["versions"]):
                p["versions"].append(r)

        # Step 4: Save all jobs known at this date, including those missing from the current snapshot. I only use information from this date and earlier observations to avoid using future data.

        for p in positions:
            v = p["values"]
            out.append(
                (
                    observed,
                    user_id,
                    v["company"],
                    v["url"],
                    v["title"],
                    v["location"],
                    v["description"],
                    v["start"],
                    v["end"],
                    p["id"],
                )
            )
    return out


# Step 5: RUNNING IT ON THE WHOLE DATASET

OUT_COLS = [
    "asof_ts",
    "user_id",
    "company_raw",
    "company_linkedin_url",
    "title_raw",
    "location_raw",
    "description",
    "startdate",
    "enddate",
    "position_id",
]
OUT_TYPES = [
    pa.date32(),
    pa.int64(),
    pa.string(),
    pa.string(),
    pa.string(),
    pa.string(),
    pa.string(),
    pa.date32(),
    pa.date32(),
    pa.int64(),
]


def shuffle(input_dir, tmp_dir, n_buckets, sample_users, threads, mem):
    con = duckdb.connect()
    con.execute(
        f"SET threads={threads}; SET memory_limit='{mem}'; "
        f"SET temp_directory='{tmp_dir}/spill'; SET preserve_insertion_order=false"
    )
    src = f"read_parquet('{input_dir}/**/*.parquet', union_by_name=true)"
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()}

    # Decision 1:Handling company LinkedIn URLs
    # The input uses company_website instead of company_linkedin_url. I found that all non-empty values are LinkedIn URLs, but they appear in different formats, including company and school pages.
    # I decided to use this column for company_linkedin_url in the output and standardize the URLs when comparing positions.

    url_col = "company_website" if "company_website" in cols else "company_linkedin_url"
    where = "user_id IS NOT NULL"
    if sample_users:
        where += (
            f" AND user_id IN (SELECT DISTINCT user_id FROM {src} "
            f"ORDER BY hash(user_id) LIMIT {sample_users})"
        )
    con.execute(
        f"""
        COPY (SELECT observed_ts, user_id, company_raw, {url_col} AS company_website,
                     title_raw, location_raw, description, startdate, enddate, order_in_profile,
                     hash(user_id) % {n_buckets} AS bucket
              FROM {src} WHERE {where})
        TO '{tmp_dir}/buckets' (FORMAT parquet, PARTITION_BY (bucket), OVERWRITE_OR_IGNORE true)"""
    )
    con.close()


def process_bucket(bucket_dir, out_path):
    con = duckdb.connect()
    con.execute("SET threads=1; SET memory_limit='1GB'")
    cur = con.execute(f"""
        SELECT user_id, observed_ts, company_raw, company_website, title_raw, location_raw,
               description, startdate, enddate
        FROM read_parquet('{bucket_dir}/*.parquet')
        ORDER BY user_id, observed_ts, order_in_profile""")
    stats = {"kept": 0, "dropped": 0}
    out = []
    user, snaps, snap_date, snap_rows = None, [], None, []

    def finish_user():
        if snap_rows:
            snaps.append((snap_date, snap_rows))
        if snaps:
            out.extend(coalesce_user(user, snaps, stats))

    # I group the rows by user and observation date. When I reach a new user, I process the previous user's work history.
    while True:
        batch = cur.fetchmany(50_000)
        if not batch:
            break
        for uid, observed, *values in batch:
            if isinstance(observed, dt.datetime):
                observed = observed.date()
            if uid != user:
                if user is not None:
                    finish_user()
                user, snaps, snap_date, snap_rows = uid, [], observed, []
            elif observed != snap_date:
                snaps.append((snap_date, snap_rows))
                snap_date, snap_rows = observed, []
            snap_rows.append(to_row(observed, *values))
    if user is not None:
        finish_user()
    con.close()

    if out:
        columns = list(zip(*out))
        table = pa.table(
            [pa.array(c, type=t) for c, t in zip(columns, OUT_TYPES)], names=OUT_COLS
        )
        pq.write_table(table, out_path)
    return stats["kept"], stats["dropped"], len(out)


def available_cpus():
    try:
        quota, period = open("/sys/fs/cgroup/cpu.max").read().split()
        if quota != "max":
            return max(1, int(int(quota) / int(period)))
    except (OSError, ValueError):
        pass
    return os.cpu_count() or 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/output")
    ap.add_argument("--tmp", default="/tmp/coalesce")
    ap.add_argument("--workers", type=int, default=available_cpus())
    ap.add_argument("--buckets", type=int, default=64)
    ap.add_argument("--sample-users", type=int, default=0, help="0 = all users")
    ap.add_argument("--mem", default="4GB", help="DuckDB memory limit for the shuffle")
    args = ap.parse_args()

    t0 = time.time()
    shutil.rmtree(args.tmp, ignore_errors=True)
    os.makedirs(args.tmp)
    os.makedirs(args.output, exist_ok=True)
    for old in glob.glob(os.path.join(args.output, "part-*.parquet")):
        os.remove(old)

    shuffle(
        args.input, args.tmp, args.buckets, args.sample_users, args.workers, args.mem
    )
    t1 = time.time()
    print(f"phase 1 (shuffle into {args.buckets} buckets): {t1 - t0:.0f}s", flush=True)

    buckets = sorted(glob.glob(os.path.join(args.tmp, "buckets", "bucket=*")))
    kept = dropped = rows = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = [
            pool.submit(
                process_bucket,
                b,
                os.path.join(args.output, f"part-{int(b.split('=')[-1]):03d}.parquet"),
            )
            for b in buckets
        ]
        for n, job in enumerate(jobs, 1):
            k, d, r = job.result()
            kept, dropped, rows = kept + k, dropped + d, rows + r
            if n % max(1, len(jobs) // 8) == 0 or n == len(jobs):
                print(f"  {n}/{len(jobs)} buckets done", flush=True)
    shutil.rmtree(args.tmp, ignore_errors=True)
    print(f"phase 2 (coalesce, {args.workers} workers): {time.time() - t1:.0f}s")
    print(
        f"snapshots kept {kept:,} | dropped as bad {dropped:,} | output rows {rows:,} | "
        f"total {time.time() - t0:.0f}s"
    )


if __name__ == "__main__":
    main()
