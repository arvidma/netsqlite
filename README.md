# netsqlite

An easy way to share an SQLite databases across multiple processes/threads *on same machine*,
with less risk of weird locking issues than if going via shared file system.

* Single file and only standard-library dependencies.

* Compatible with Python 3.6 and newer.

* About 300x overhead compared to normal sqlite3...

* ...But that allows 3000+ queries/second on a single thread!
