# Open transactions and effects

## Summary

Having a transaction open for a long time does not affect over all replication delay. But it does consume a connection. So having many long running transactions will have you running low on connections. Eventually that might affect replication as well as the replica might not be able to connect.

## Tests

### Test 1 - Inserting data while having an open transaction on master

#### Setup 

```bash
# terminal 1
$ docker-compose up
# terminal 2
$ psql -U postgres -h localhost -p 5432
postgres=# begin;
postgres=# insert into names VALUES ('dude larsson', NOW());
# terminal 3
$ ./count.py
# terminal 4
$ ./insert_with_commit.py
```

#### Result

You'll see a steady tick in the count of entries in names. So having the transaction open on master does not affect the replication.

### Test 2 - Slow and quick transactions at the same time

#### Setup

```bash
# terminal 1
$ docker-compose up
# terminal 3
$ ./count.py
# terminal 3
$ for (( i = 0; i < 100; i++)); do         
./insert.py &   
done
# terminal 4
$ for (( i = 0; i < 100; i++)); do         
./insert_with_commit.py &   
done
```


#### Result

Watch things blow up

For the running scripts you might see something like this:

```
postgres_replication Traceback (most recent call last):
  File "./insert.py", line 6, in <module>
    conn = psycopg2.connect('host=localhost port=5432 user=postgres password=test')
  File "/home/krl/.pyenv/versions/3.6.1/lib/python3.6/site-packages/psycopg2/__init__.py", line 130, in connect
    conn = _connect(dsn, connection_factory=connection_factory, **kwasync)
psycopg2.OperationalError: FATAL:  sorry, too many clients already

Traceback (most recent call last):
  File "./insert.py", line 6, in <module>
    conn = psycopg2.connect('host=localhost port=5432 user=postgres password=test')
  File "/home/krl/.pyenv/versions/3.6.1/lib/python3.6/site-packages/psycopg2/__init__.py", line 130, in connect
    conn = _connect(dsn, connection_factory=connection_factory, **kwasync)
psycopg2.OperationalError: FATAL:  sorry, too many clients already
```

Compose log:

```
primary-postgres | 2019-02-09 09:35:40.255 UTC [146] FATAL:  sorry, too many clients already
primary-postgres | 2019-02-09 09:35:40.258 UTC [148] FATAL:  sorry, too many clients already
replica-postgres | 2019-02-09 09:37:01.827 UTC [33] FATAL:  terminating connection due to conflict with recovery
replica-postgres | 2019-02-09 09:37:01.827 UTC [33] DETAIL:  User was holding a relation lock for too long.
replica-postgres | 2019-02-09 09:37:01.827 UTC [33] HINT:  In a moment you should be able to reconnect to the database and repeat your command.
```

### Test 3 - A lot of quick transactions 

Compare with doing the same amount of inserts but always closing the transaction directly.

#### Setup

```bash
# terminal 1
$ docker-compose up
# terminal 2
$./count.py
# terminal 3
$ for (( i = 0; i < 200; i++)); do         
./insert_with_commit.py &   
done
```

#### Result

You should (hopefully) not see any failures.

#### Test 4 - Add pgbouncer to the mix

#### Setup

Modify compose file to include pgbouncer.

```bash
# terminal 1
$ docker-compose up
Starting replica-postgres ... 
Starting primary-postgres ... 
Starting replica-postgres
Starting primary-postgres ... done
Starting postgresreplication_pgbouncer_1 ... 
Starting replica-postgres ... done
...
# terminal 2
$ for (( i = 0; i < 100; i++)); do         
./insert.py &   
done
```

#### Result

You should not see any failed connections from the client.

## Setup

### Requirements

- docker
- docker-compose
- postgres client

###  running the databases

Create a docker-compose.yml with the following contents (make sure to swap out home directory):

```yaml
version: '2'
services:
  primary:
    container_name: primary-postgres
    image: launcher.gcr.io/google/postgresql10
    environment:
      "POSTGRES_PASSWORD": "test"
      "PGDATA": "/var/lib/postgresql/primary/data"
    ports:
      - '5432:5432'
    volumes:
      - /home/krl/primary/postgresql:/var/lib/postgresql/primary/data
  replica:
    container_name: replica-postgres
    image: launcher.gcr.io/google/postgresql10
    environment:
      "POSTGRES_PASSWORD": "test"
      "PGDATA": "/var/lib/postgresql/replica/data"
    ports:
      - '5433:5432'
    volumes:
      - /home/krl/replica/postgresql:/var/lib/postgresql/replica/data
```

```bash
# create directories we'll use for permanent storage
# this means we'll the data will still be around even if we restart docker
$ mkdir -p ~/primary/postgresql
$ mkdir -p ~/replica/postgresql
# in the same directory as the compose file
$ docker-compose up
Starting replica-postgres ... 
Starting primary-postgres ... 
Starting replica-postgres
Starting replica-postgres ... done
Attaching to primary-postgres, replica-postgres
...
```

Edit the master config files:

```bash
$ sudo vim ~/primary/postgresql/postgresql.conf
-> listen_addresses = '*'
-> wal_level = replica
-> max_wal_senders = 3 # max number of walsender processes
-> wal_keep_segments = 64 # in logfile segments, 16MB each; 0 disables

$ sudo vim ~/primary/postgresql/pg_hba.conf
# add, change ip to whatever your local ip is according to ifconfig
host replication replicate 172.19.0.1/32 scram-sha-256
```

Add replication user `replicate` with password `test` to primary

```bash
$ docker exec -it primary-postgres /bin/bash
/# psql -U postgres
postgres # CREATE ROLE replicate WITH REPLICATION LOGIN ;
postgres # set password_encryption = 'scram-sha-256';
postgres # \password replicate
```

In order for the replica to be able to work as a replica is has to be set up using a base backup from the master.

```bash
$ docker exec -it replica-postges /bin/bash
/# ps -ef | grep postgres
/# kill <postgres pid>
...
$ rm -rf ~/replica/postgres
$ mkdir -p ~/replica/postgres
$ cd ~/replica/postgres
$ pg_basebackup -h 172.19.0.1 -D . -P -U replicate --wal-method=stream
```

Modify config files to make the replica a replics

```bash
$ sudo vim ~/replica/postgres/postgresql.conf
-> hot_standby = on
# create a recovery file for the replica
$ sudo vim ~/replica/postgres/recovery.conf
standby_mode          = 'on'
primary_conninfo      = 'host=172.17.0.2 port=5432 user=replicate password=MySuperPassword'
trigger_file = '/tmp/MasterNow'
```

Restart docker compose

```bash
# in docker compose terminal
Ctrl-C
$ docker-compose up
```

Hopefully you now see a clean startup and the replica being connected to the primary.

### create table

```bash
$ psql -U postgres -h localhost -p 5432
postgres=# CREATE TABLE names(name TEXT, date timestamp);
```

### test scripts

```python
#!/usr/bin/env python
# insert_with_commit.py

import psycopg2
import time

def insert():
    conn = psycopg2.connect('host=localhost port=5432 user=postgres password=test')
    cur = conn.cursor()
    cur.execute("INSERT INTO names VALUES('apa', NOW());")
    conn.commit()
    conn.close()

for i in range(0, 10):
    insert()
    time.sleep(1)
```

```python
#!/usr/bin/env python
# insert.py

import psycopg2
import time

conn = psycopg2.connect('host=localhost port=5432 user=postgres password=test')
cur = conn.cursor()

for i in range(0, 10):
    cur.execute("INSERT INTO names VALUES('apa', NOW());")
    time.sleep(1)
```

```python
#!/usr/bin/env python
# count.py
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
```

### Add pgbouncer

```yml
  pgbouncer:
      image: brainsam/pgbouncer:1.7.2
      environment:
        DB_HOST: postgres
        DB_USER: postgres
        DB_PASSWORD: test
        DB_port: 5432
      links:
        - primary:postgres
      ports:
        - 6432:6432
```

## Further Experiments

- local connection pool
- pg_bouncer
- transaction manager
- inserting a lot of data
- stat monitoring
- multiple replicas
- chaining replicas (replication of replicas)

## Reading

[primary article for setup](https://blog.raveland.org/post/postgresql_sr/)
[secondary article for setup](https://lnxslck.wordpress.com/2018/10/06/postgres-and-docker-replication-with-hot-standby/)
[docker image](https://github.com/GoogleCloudPlatform/postgresql-docker/tree/master/10)
[pgbouncer setup](https://github.com/guedim/docker-postgres-pgbouncer)
