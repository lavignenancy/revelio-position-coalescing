"""Rule checks on an output folder.  python tools/check_output.py data/input output"""

import sys

import duckdb

inp, out = sys.argv[1], sys.argv[2]
con = duckdb.connect()
I, O = f"read_parquet('{inp}/*.parquet')", f"read_parquet('{out}/*.parquet')"
q = lambda s: con.sql(s).fetchall()[0]
rows, keys = q(f"SELECT count(*), count(DISTINCT (position_id, asof_ts)) FROM {O}")
print(f"1. (position_id, asof_ts) unique:            {rows == keys}   ({rows:,} rows)")
print(
    f"2. position_ids shared by two users:          {q(f'SELECT count(*) FROM (SELECT position_id FROM {O} GROUP BY 1 HAVING count(DISTINCT user_id) > 1)')[0]}  (should be 0)"
)
print(
    f"3. output (user, date) pairs not in input:    {q(f'SELECT count(*) FROM (SELECT DISTINCT user_id, asof_ts FROM {O}) o ANTI JOIN (SELECT DISTINCT user_id, observed_ts AS asof_ts FROM {I}) i USING (user_id, asof_ts)')[0]}  (should be 0)"
)
print(
    f"4. times a user's position count went DOWN:   {q(f'WITH c AS (SELECT user_id, asof_ts, count(*) n FROM {O} GROUP BY ALL) SELECT count(*) FROM (SELECT n < lag(n) OVER (PARTITION BY user_id ORDER BY asof_ts) AS down FROM c) WHERE down')[0]}  (should be 0)"
)
