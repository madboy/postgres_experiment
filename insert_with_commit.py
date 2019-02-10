#!/usr/bin/env python

import psycopg2
import time

def insert():
    conn = psycopg2.connect('host=localhost port=6432 user=postgres password=test')
    cur = conn.cursor()
    cur.execute("INSERT INTO names VALUES('apa', NOW());")
    conn.commit()
    conn.close()

for i in range(0, 10):
    insert()
    time.sleep(1)

