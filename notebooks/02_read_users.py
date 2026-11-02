import duckdb

con = duckdb.connect()
con.execute("SET threads = 4")
con.execute("SET memory_limit = '3GB'")

data = "data/input/**/*.parquet"

users = con.execute(f"""
    SELECT user_id
    FROM read_parquet('{data}')
    GROUP BY user_id
    HAVING COUNT(DISTINCT observed_ts) >= 5
    ORDER BY hash(user_id)
    LIMIT 10
""").fetchall()

user_ids = [row[0] for row in users]

print("\nSELECTED USERS:", user_ids)

for user_id in user_ids:
    print(f"\n{'=' * 70}")
    print(f"USER: {user_id}")
    print("=" * 70)

    rows = con.execute(
        f"""
        SELECT
            observed_ts,
            order_in_profile,
            company_raw,
            company_website,
            title_raw,
            startdate,
            enddate
        FROM read_parquet('{data}')
        WHERE user_id = ?
        ORDER BY observed_ts, order_in_profile, company_raw, title_raw
    """,
        [user_id],
    ).fetchall()

    for row in rows:
        print(" | ".join(str(value) for value in row))

con.close()
