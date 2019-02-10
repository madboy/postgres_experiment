#!/usr/bin/env python
# displays the number of entries in the names table on the replica

import psycopg2
import sys
import time

conn = psycopg2.connect('host=localhost port=5433 user=postgres password=test')
cur = conn.cursor()

def get_count():
    cur.execute("select count(*) from names;")
    return cur.fetchone()[0]

start_count = get_count()

for i in range(0, 100):
    cur.execute("select count(*) from names;")
    sys.stdout.write("\r{} names in names".format(get_count()))
    sys.stdout.flush()
    time.sleep(1)

end_count = get_count()
print("\n{} names inserted".format(end_count - start_count))
