# multiprocessing.connection vs XML-RPC: Implementation Comparison

## Port Scanning Logic

### Current XML-RPC Implementation
```python
def connect(db_name: str):
    for port_offset in range(10):
        port = STARTPORT + port_offset
        nsql = NetSQLiteConnection(port, db_name)
        try:
            if not nsql.proxy.target_database() == db_name:
                # Server exists but wrong database
                continue
            elif nsql.are_we_gainfully_connected():
                break
        except ConnectionError:  # XML-RPC raises ConnectionError
            # No server, spawn one
            proc = __spawn_server_process__(db_name=db_name, port=port)
            nsql.child_process = proc
            __poll(nsql)
            break
```

### With multiprocessing.connection

**Yes, same port-scanning logic works!** But with slight changes:

```python
from multiprocessing.connection import Client, Listener
import errno

def connect(db_name: str):
    for port_offset in range(10):
        port = STARTPORT + port_offset
        try:
            # Try to connect to existing server
            conn = Client(('localhost', port))

            # Check if it's serving the right database
            conn.send(('target_database',))
            response = conn.recv()

            if response != db_name:
                conn.close()
                log.warning(f"Server on port {port} serves different database")
                continue

            # Test if connection works
            conn.send(('ping',))
            conn.recv()

            return MPConnection(conn, db_name)

        except (ConnectionRefusedError, OSError) as e:
            # No server running, spawn one
            proc = __spawn_server_process__(db_name=db_name, port=port)
            # Wait and connect
            conn = __poll_and_connect(port)
            return MPConnection(conn, db_name, child_process=proc)
```

**Key differences in exceptions:**
- XML-RPC: Raises `ConnectionError`
- multiprocessing: Raises `ConnectionRefusedError` (subclass of ConnectionError) or `OSError`

**Port binding on server side:**
```python
# Server with multiprocessing.connection
try:
    listener = Listener(('localhost', port))
except OSError as e:
    if e.errno == errno.EADDRINUSE:
        # Port already in use, try next port
        continue
    raise
```

---

## Method Call Changes

### Current XML-RPC: Automatic Method Dispatch

**Client side (current):**
```python
# XML-RPC automatically marshals method calls
result = nsql.proxy.execute(query, params)
result = nsql.proxy.target_database()
```

**Server side (current):**
```python
# XML-RPC server automatically dispatches to methods
server.register_instance(NetSQLiteServer(db_path))
# Calls like proxy.execute() → nsql.execute()
```

### With multiprocessing.connection: Manual Message Passing

**Client side (needs changes):**
```python
class MPConnection:
    def __init__(self, conn, database_name, child_process=None):
        self.conn = conn
        self.database_name = database_name
        self.child_process = child_process

    def execute(self, query, params=None):
        # Send method name and arguments as tuple
        self.conn.send(('execute', query, params or tuple()))

        # Receive response
        response = self.conn.recv()

        # Check for errors
        if isinstance(response, Exception):
            raise response

        return response

    def target_database(self):
        self.conn.send(('target_database',))
        return self.conn.recv()

    def are_we_gainfully_connected(self):
        try:
            self.conn.send(('ping',))
            self.conn.recv()
            return True
        except:
            return False
```

**Server side (needs changes):**
```python
class MPServer:
    def __init__(self, db_path, port):
        self.db_path = db_path
        self.connection = sqlite3.connect(self.db_path)
        self.lock = threading.Lock()
        self.listener = Listener(('localhost', port))

    def serve_forever(self):
        while True:
            # Accept connection
            conn = self.listener.accept()

            # Handle in thread (to support multiple clients)
            threading.Thread(target=self.handle_client, args=(conn,), daemon=True).start()

    def handle_client(self, conn):
        try:
            while True:
                # Receive message (method_name, *args)
                message = conn.recv()

                if not isinstance(message, tuple) or len(message) == 0:
                    continue

                method_name = message[0]
                args = message[1:] if len(message) > 1 else ()

                # Dispatch manually
                try:
                    if method_name == 'execute':
                        result = self.execute(*args)
                    elif method_name == 'target_database':
                        result = self.target_database()
                    elif method_name == 'ping':
                        result = 'pong'
                    else:
                        result = Exception(f"Unknown method: {method_name}")

                    conn.send(result)

                except Exception as e:
                    conn.send(e)

        except (EOFError, ConnectionResetError):
            # Client disconnected
            conn.close()

    def execute(self, query, params):
        with self.lock:
            res = self.connection.execute(query, params).fetchall()
        return res

    def target_database(self):
        return self.db_path
```

---

## Summary of Changes

| Aspect | XML-RPC (Current) | multiprocessing.connection | Changes Needed? |
|--------|-------------------|---------------------------|-----------------|
| **Port scanning** | ✅ Works | ✅ Works | ⚠️ Minor (different exceptions) |
| **Port binding** | `SimpleXMLRPCServer(('localhost', port))` | `Listener(('localhost', port))` | ✅ Yes |
| **Connection** | `ServerProxy(url)` | `Client(('localhost', port))` | ✅ Yes |
| **Method calls** | Automatic dispatch | Manual message passing | ✅ Yes (biggest change) |
| **Error handling** | `ConnectionError` | `ConnectionRefusedError`, `OSError` | ⚠️ Minor |
| **Serialization** | XML | Pickle | ✅ Automatic |
| **Multiple clients** | Built-in | Need threading | ⚠️ Add threads |

---

## Key Advantages of multiprocessing.connection

1. **Performance**: 2-3x faster (no XML overhead, no HTTP)
2. **Simpler serialization**: Pickle is faster than XML
3. **Same port logic**: Can reuse existing port-scanning approach
4. **Standard library**: No new dependencies

## Key Disadvantages

1. **Manual dispatch**: Need to write method routing code
2. **Threading**: Need to handle multiple clients explicitly
3. **Pickle security**: Less secure than XML-RPC (but same machine only)
4. **More code**: ~50 extra lines for dispatch logic

---

## Proof of Concept Size

**Estimated code changes:**
- `NetSQLiteConnection` class: ~30 lines (was ~30 lines)
- `NetSQLiteServer` class: ~60 lines (was ~15 lines) - **main increase**
- `connect()` function: ~35 lines (was ~23 lines)
- `__server_startup__()`: ~15 lines (was ~9 lines)

**Total:** ~140 lines vs current ~100 lines (+40 lines, +40%)

**Trade-off:** 40% more code for 2-3x better performance

---

## Recommendation

**Worth implementing?**

✅ **YES, if:**
- You want 2-3x performance improvement
- You're okay with ~40 extra lines of code
- Security is not a concern (same machine only anyway)
- You need cross-platform compatibility

❌ **NO, if:**
- Current performance is sufficient
- You prefer simplicity over speed
- XML-RPC's automatic dispatch is valuable to you

**Best approach:** Create `netsqlite_mp.py` as alternative implementation, keep both versions for comparison.
