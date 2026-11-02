import sys

import duckdb

path = (
    sys.argv[1] if len(sys.argv) > 1 else "/home/student/revelio/data/input/*.parquet"
)
con = duckdb.connect()
con.execute("SET memory_limit='3GB'; SET threads=8")
con.execute(f"CREATE VIEW raw AS SELECT * FROM read_parquet('{path}')")


def show(title, sql):
    print(f"\n=== {title} ===", flush=True)
    try:
        con.sql(sql).show(max_width=250, max_col_width=60)
    except Exception as e:
        print("ERROR:", e)
    sys.stdout.flush()


show(
    "A. the 'other linkedin form' values",
    """
    SELECT company_website, count(*) n FROM raw
    WHERE company_website ILIKE '%linkedin.com%'
      AND company_website NOT LIKE 'linkedin.com/company/%'
      AND company_website NOT LIKE 'https://www.linkedin.com/company/%'
    GROUP BY 1 ORDER BY 2 DESC LIMIT 20""",
)

con.execute("""
    CREATE TEMP TABLE dup AS
    SELECT user_id, observed_ts, lower(company_raw) c, lower(title_raw) t, startdate,
           count(*) AS copies,
           count(DISTINCT coalesce(enddate::VARCHAR, '∅')) AS n_end,
           count(DISTINCT coalesce(description, '∅')) AS n_desc,
           count(DISTINCT coalesce(location_raw, '∅')) AS n_loc,
           count(DISTINCT coalesce(company_website, '∅')) AS n_url,
           count(DISTINCT company_raw) AS n_company_spelling
    FROM raw GROUP BY user_id, observed_ts, c, t, startdate HAVING count(*) > 1""")

show(
    "B. 6 duplicate-in-one-snapshot cases, side by side",
    """
    WITH d AS (SELECT * FROM dup ORDER BY hash(user_id, observed_ts) LIMIT 6)
    SELECT r.user_id, r.observed_ts, r.order_in_profile AS o, r.company_raw, r.title_raw,
           r.startdate, r.enddate, r.company_website IS NOT NULL AS has_url,
           left(r.description, 40) AS descr
    FROM raw r JOIN d ON r.user_id = d.user_id AND r.observed_ts = d.observed_ts
                     AND lower(r.company_raw) = d.c AND lower(r.title_raw) = d.t AND r.startdate = d.startdate
    ORDER BY r.user_id, r.observed_ts, o""",
)

show(
    "C. how the two copies differ",
    """
    SELECT count(*) AS cases,
           count(*) FILTER (WHERE copies > 2) AS more_than_2_copies,
           count(*) FILTER (WHERE n_end = 1 AND n_desc = 1 AND n_loc = 1 AND n_url = 1 AND n_company_spelling = 1) AS fully_identical,
           count(*) FILTER (WHERE n_end > 1) AS enddate_differs,
           count(*) FILTER (WHERE n_desc > 1) AS description_differs,
           count(*) FILTER (WHERE n_loc > 1) AS location_differs,
           count(*) FILTER (WHERE n_url > 1) AS url_differs,
           count(*) FILTER (WHERE n_company_spelling > 1) AS company_case_differs
    FROM dup""",
)

show(
    "D. 5 users with a 'much smaller' snapshot: number of rows in each snapshot, oldest first",
    """
    WITH s AS (SELECT user_id, observed_ts, count(*) AS n FROM raw GROUP BY ALL),
         m AS (SELECT user_id, median(n) AS med FROM s GROUP BY 1),
         pick AS (SELECT DISTINCT user_id FROM s JOIN m USING (user_id) WHERE n < 0.5 * med AND med >= 4
                  ORDER BY hash(user_id) LIMIT 5)
    SELECT user_id, string_agg(n::VARCHAR, ' ' ORDER BY observed_ts) AS sizes_over_time
    FROM s JOIN pick USING (user_id) GROUP BY 1""",
)

print("\nDONE", flush=True)
