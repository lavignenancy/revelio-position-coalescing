import duckdb

con = duckdb.connect()
con.execute("SET memory_limit='3GB'; SET threads=8")
con.execute(
    "CREATE VIEW raw AS SELECT * FROM read_parquet('/home/student/revelio/data/input/*.parquet')"
)


def show(title, sql):
    print(f"\n=== {title} ===")
    print(con.sql(sql))


show(
    "P1 company_website formats",
    """
    SELECT CASE
             WHEN company_website IS NULL THEN 'NULL'
             WHEN company_website LIKE 'linkedin.com/company/%' THEN 'linkedin.com/company/...'
             WHEN company_website LIKE 'https://www.linkedin.com/company/%' THEN 'https://www.linkedin.com/company/...'
             WHEN company_website ILIKE '%linkedin.com%' THEN 'other linkedin form'
             ELSE 'not linkedin'
           END AS format,
           count(*) AS n_rows,
           round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct
    FROM raw GROUP BY 1 ORDER BY 2 DESC""",
)
show(
    "P1b examples of non-linkedin values",
    """
    SELECT company_website, count(*) n FROM raw
    WHERE company_website IS NOT NULL AND company_website NOT ILIKE '%linkedin.com%'
    GROUP BY 1 ORDER BY 2 DESC LIMIT 15""",
)

show(
    "P2 smallest order_in_profile per snapshot",
    """
    SELECT min_order, count(*) AS n_snapshots FROM (
        SELECT user_id, observed_ts, min(order_in_profile) AS min_order FROM raw GROUP BY ALL)
    GROUP BY 1 ORDER BY 2 DESC LIMIT 5""",
)

show(
    "P3 snapshot size vs the user's median size",
    """
    WITH s AS (SELECT user_id, observed_ts, count(*) AS n FROM raw GROUP BY ALL),
         m AS (SELECT user_id, median(n) AS med FROM s GROUP BY 1)
    SELECT CASE WHEN n >= med THEN 'normal or bigger'
                WHEN n >= 0.5 * med THEN 'a bit smaller (>=50%)'
                ELSE 'much smaller (<50% of usual)' END AS size_class,
           count(*) AS n_snapshots,
           round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct
    FROM s JOIN m USING (user_id) GROUP BY 1 ORDER BY 2 DESC""",
)

show(
    "P4 half-empty rows",
    """
    SELECT count(*) FILTER (WHERE company_raw IS NOT NULL AND title_raw IS NULL AND startdate IS NULL) AS company_only,
           count(*) FILTER (WHERE company_raw IS NULL AND title_raw IS NULL) AS no_company_no_title,
           count(*) AS total
    FROM raw""",
)

show(
    "P5 most common very short company / title values",
    """
    SELECT 'company' AS col, company_raw AS value, count(*) n FROM raw WHERE length(trim(company_raw)) <= 2 GROUP BY ALL
    UNION ALL
    SELECT 'title', title_raw, count(*) FROM raw WHERE length(trim(title_raw)) <= 2 GROUP BY ALL
    ORDER BY n DESC LIMIT 15""",
)

show(
    "P6 same user+company+start with more than one title",
    """
    SELECT count(*) AS n_groups FROM (
        SELECT user_id, lower(company_raw), startdate FROM raw
        WHERE startdate IS NOT NULL AND title_raw IS NOT NULL
        GROUP BY ALL HAVING count(DISTINCT lower(title_raw)) > 1)""",
)

show(
    "P7 same company+title+start appearing twice in ONE snapshot",
    """
    SELECT count(*) AS n_cases FROM (
        SELECT user_id, observed_ts, lower(company_raw), lower(title_raw), startdate FROM raw
        GROUP BY ALL HAVING count(*) > 1)""",
)
