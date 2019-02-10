#!/usr/bin/env python

import psycopg2
import time

conn = psycopg2.connect('host=localhost port=6432 user=postgres password=test')
cur = conn.cursor()

for i in range(0, 10):
    cur.execute("INSERT INTO names VALUES('apa', NOW());")
    time.sleep(1)
