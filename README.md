# netsqlite
SQLite, almost transparently shared across processes

An easy way to share an SQLite databases across multiple processes/threads *on same machine*,
with less risk of weird locking issues than if going via shared file system.

* Single file and only standard-library dependencies.

* Compatible with Python 3.6 and newer.

* About 300x overhead compared to normal sqlite3...

* ...But that allows 3000+ queries/second on a single thread!

## Basic Usage

```python
import netsqlite

# Connect to a database
conn = netsqlite.connect("mydb.db")

# Use it like normal sqlite3
conn.execute("CREATE TABLE users(id int, name text)")
conn.execute("INSERT INTO users VALUES(?, ?)", (1, "Alice"))
result = conn.execute("SELECT * FROM users")
print(result)  # [[1, 'Alice']]
```

## Authentication (Optional)

NetSQLite supports optional authentication to prevent unauthorized processes from connecting:

```python
import netsqlite

# Connect with an authentication token
SECRET_TOKEN = "my_secret_token"
conn = netsqlite.connect("mydb.db", auth_token=SECRET_TOKEN)

# Only processes with the correct token can connect
conn.execute("CREATE TABLE secret_data(value text)")

# Another process with the same token can connect
conn2 = netsqlite.connect("mydb.db", auth_token=SECRET_TOKEN)
result = conn2.execute("SELECT * FROM secret_data")

# Wrong token = connection rejected
try:
    conn3 = netsqlite.connect("mydb.db", auth_token="wrong_token")
except Exception as e:
    print(f"Rejected: {e}")  # "Authentication failed"
```

**Note**: Authentication is entirely optional. Without an `auth_token`, the system works as before (backward compatible).
