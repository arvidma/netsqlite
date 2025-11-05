# Platform-Independent IPC Analysis for NetSQLite

## Cross-Platform Socket Options

### Unix Domain Sockets (Linux/macOS)
**Pros:**
- Fast, low-latency IPC on same machine
- ~50% lower overhead than TCP/IP
- File-system based permissions

**Cons on macOS:**
- Socket file permissions can be restrictive
- Path length limitations (104 chars on many systems)
- Cleanup required (socket file persists)
- **Permission issues**: By default, socket files inherit directory permissions
  - May need explicit chmod/chown
  - Can be problematic in multi-user environments

**Python support:**
```python
import socket
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.bind('/tmp/netsqlite.sock')
```

### Named Pipes (Windows)
**Windows equivalent:**
- Named Pipes are Windows' answer to Unix domain sockets
- Similar performance characteristics
- Different API, but Python abstracts some of it

**Python support (limited):**
- No direct socket.AF_UNIX support on Windows
- Need to use `win32pipe` (pywin32 library) or `multiprocessing.connection`
- More complex API

**Example using multiprocessing.connection:**
```python
from multiprocessing.connection import Listener, Client

# Server
listener = Listener(r'\\.\pipe\netsqlite', authkey=b'secret')
conn = listener.accept()

# Client
conn = Client(r'\\.\pipe\netsqlite', authkey=b'secret')
```

### Cross-Platform Solutions

#### Option 1: TCP with localhost binding (CURRENT)
**Pros:**
- ✅ Works everywhere (current implementation)
- ✅ Simple, standard library only
- ✅ No platform-specific code

**Cons:**
- ❌ Higher overhead (~0.86ms network + 0.86ms HTTP)
- ❌ TCP/IP stack overhead even on localhost
- ❌ Port conflicts possible

**Current NetSQLite performance:** ~700 qps

---

#### Option 2: Platform-specific optimized sockets
**Implementation:**
```python
import sys
import socket

if sys.platform == 'win32':
    from multiprocessing.connection import Listener, Client
    # Use Named Pipes
elif sys.platform in ['linux', 'darwin']:
    # Use Unix domain sockets
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
```

**Pros:**
- ✅ Optimal performance on each platform (~2000-3000 qps estimated)
- ✅ Lower latency

**Cons:**
- ❌ More complex code
- ❌ Platform-specific testing required
- ❌ Permission issues on macOS (see below)
- ❌ Different behavior across platforms

---

#### Option 3: Use multiprocessing.connection (RECOMMENDED)
**Python's built-in cross-platform abstraction:**

```python
from multiprocessing.connection import Listener, Client

# Server
address = ('localhost', 25432)  # Or named pipe on Windows
listener = Listener(address, authkey=b'netsqlite')
conn = listener.accept()

# Send/receive Python objects directly
conn.send(('execute', query, params))
result = conn.recv()

# Client
conn = Client(address, authkey=b'netsqlite')
conn.send(('execute', query, params))
result = conn.recv()
```

**Pros:**
- ✅ Cross-platform (Windows, Linux, macOS)
- ✅ Python standard library
- ✅ Automatic pickling (no XML overhead)
- ✅ Much faster than XML-RPC
- ✅ Handles platform differences automatically

**Cons:**
- ❌ Uses pickle (security consideration if exposed)
- ❌ Still some overhead, but less than HTTP+XML-RPC

**Estimated performance:** ~1500-2500 qps (2-3x faster than current)

---

#### Option 4: Memory-mapped files
**For high-performance IPC:**
- `mmap` module in Python
- Shared memory segment
- Lock-based coordination

**Pros:**
- ✅ Extremely fast (almost no overhead)
- ✅ Cross-platform

**Cons:**
- ❌ Complex synchronization required
- ❌ Not suitable for RPC-style interface
- ❌ Overkill for this use case

---

## macOS Permission Issues

### Problem:
On macOS, Unix domain socket files inherit directory permissions, which can cause:
- Permission denied errors when different users try to connect
- Security restrictions in certain directories (/tmp may have sticky bit)

### Solutions:

**1. Explicit socket file permissions:**
```python
import socket
import os
import stat

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock_path = '/tmp/netsqlite.sock'

# Remove old socket if exists
try:
    os.unlink(sock_path)
except FileNotFoundError:
    pass

sock.bind(sock_path)

# Set world-readable/writable (or more restrictive as needed)
os.chmod(sock_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)

sock.listen(1)
```

**2. Use user-specific directories:**
```python
import os
import tempfile

# Use user-specific temp directory
socket_dir = os.path.join(tempfile.gettempdir(), f'netsqlite-{os.getuid()}')
os.makedirs(socket_dir, exist_ok=True)
sock_path = os.path.join(socket_dir, 'netsqlite.sock')
```

**3. Use abstract namespace (Linux only):**
```python
# Linux-specific: abstract socket (no filesystem entry)
sock.bind('\0netsqlite_socket')  # Leading null byte
```

---

## Recommendation for NetSQLite

### Best approach: Hybrid strategy

```python
import sys
from multiprocessing.connection import Listener, Client

def create_server(db_path):
    # Try Unix socket first (Linux/macOS), fall back to TCP
    if sys.platform != 'win32':
        try:
            import socket
            # Use abstract namespace on Linux, file-based on macOS
            if sys.platform == 'linux':
                address = '\0netsqlite_' + str(os.getpid())
            else:  # macOS
                address = f'/tmp/netsqlite_{os.getuid()}_{os.getpid()}.sock'

            # Use raw socket for domain socket
            # ...
        except Exception:
            # Fall back to TCP
            address = ('localhost', find_free_port())
    else:
        # Windows: use localhost TCP (or Named Pipes with more work)
        address = ('localhost', find_free_port())

    return Listener(address)
```

### Benefits:
1. **Cross-platform compatible**
2. **Optimal performance where possible**
3. **Graceful fallback to TCP**
4. **Addresses macOS permission issues** (user-specific paths)
5. **2-3x performance improvement** over current XML-RPC

### Trade-offs:
- More complex than current implementation
- Need thorough testing across platforms
- Still maintains "single file" philosophy (standard library only)

---

## Performance Estimates

| Implementation | qps | Latency | Platform Support | Complexity |
|----------------|-----|---------|-----------------|------------|
| Current (XML-RPC/TCP) | 700 | 1.76ms | ✅ All | ⭐ Simple |
| multiprocessing.connection | 1500-2500 | 0.5-0.8ms | ✅ All | ⭐⭐ Medium |
| Platform-specific optimized | 2000-3000 | 0.3-0.5ms | ⚠️ Per-platform | ⭐⭐⭐ Complex |
| Direct SQLite | 700,000+ | 0.001ms | ✅ All | N/A |

**Conclusion:** `multiprocessing.connection` offers the best balance of performance improvement (2-3x) and cross-platform compatibility while staying in the standard library.
