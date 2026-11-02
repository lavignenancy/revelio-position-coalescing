import duckdb

con = duckdb.connect()
con.execute("SET memory_limit='3GB'; SET threads=8")
src = "read_parquet('/home/student/revelio/data/input/*.parquet')"

print("Columns and types")
print(con.sql(f"DESCRIBE SELECT * FROM {src}"))

print("=== Size ===")
print(
    con.sql(
        f"SELECT count(*) AS rows, count(DISTINCT user_id) AS users, count(DISTINCT (user_id, observed_ts)) AS snapshots FROM {src}"
    )
)

print("=== First 5 rows ===")
print(con.sql(f"SELECT * FROM {src} LIMIT 5"))
