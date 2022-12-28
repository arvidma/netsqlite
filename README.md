# netsqlite
SQLite almost transparantly over XML-RPC

An easy way to share an SQLite databases across multiple processes/threads *on same machine*,
with less risk of weird locking issues than if going via shared file system.

* Single file and only standard-library dependencies.

* Compatible with Python 3.6 and newer.

* About 1000x overhead compared to normal sqlite3...

* ...But that still allows 10k queries/second before maxing out a single thread!
