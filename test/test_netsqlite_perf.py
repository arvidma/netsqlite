import logging
import os
import sqlite3
from datetime import datetime

from netsqlite import netsqlite

logging.basicConfig(
    level=logging.INFO,
    format=f"[%(asctime)s] %(levelname)s [{os.getpid()}:%(name)s]: %(message)s",
)

remote_con = netsqlite.connect(":memory:")
local_con = sqlite3.connect(":memory:")


def the_thing(some_con, times=1000):
    ts = datetime.now()
    some_con.execute("CREATE TABLE apa(heltal1 int, heltal2 int);")
    for n in range(times):
        some_con.execute("INSERT INTO apa VALUES(?, ?)", (n, n * n))

    dur = datetime.now() - ts
    print(f"Did {times} inserts in {dur} seconds. That is {dur / times} each. "
          f"With {type(some_con)}")

    return some_con.execute("SELECT * FROM apa")


the_thing(local_con)
the_thing(remote_con)
