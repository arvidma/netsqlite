"""
Detailed overhead profiling for multiprocessing.connection implementation.

Breaks down where the ~0.27ms overhead comes from.
"""

import logging
import os
import sqlite3
import sys
import time
import pickle
from multiprocessing.connection import Client, Listener
import threading

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from netsqlite import netsqlite_mp

logging.basicConfig(
    level=logging.WARNING,
    format=f"[%(asctime)s] %(levelname)s [{os.getpid()}:%(name)s]: %(message)s",
)

ITERATIONS = 1000

print("=" * 80)
print("NetSQLite-MP Overhead Profiling Analysis")
print("=" * 80)

# ============================================================================
# 1. Baseline: Direct SQLite execution time
# ============================================================================
print("\n1. BASELINE: Direct SQLite execution")
print("-" * 80)

local_con = sqlite3.connect(":memory:")
local_con.execute("CREATE TABLE test(a int, b int);")

start = time.perf_counter()
for i in range(ITERATIONS):
    local_con.execute("INSERT INTO test VALUES(?, ?)", (i % 100, (i * 2) % 100))
direct_sqlite_time = (time.perf_counter() - start) / ITERATIONS * 1000  # ms per query

print(f"Direct SQLite time: {direct_sqlite_time:.4f} ms/query")
local_con.execute("DROP TABLE test;")

# ============================================================================
# 2. Pickle Serialization/Deserialization overhead
# ============================================================================
print("\n2. PICKLE SERIALIZATION/DESERIALIZATION")
print("-" * 80)

query = "INSERT INTO test VALUES(?, ?)"
params = (42, 84)

# Measure pickle marshalling
start = time.perf_counter()
for i in range(ITERATIONS):
    # Simulate what multiprocessing.connection does: pickle the message
    request_data = pickle.dumps(('execute', query, params))
    # Unpickle on server side
    method, q, p = pickle.loads(request_data)
    # Pickle response
    response_data = pickle.dumps([[1, 2]])
    # Unpickle response on client
    result = pickle.loads(response_data)

pickle_overhead = (time.perf_counter() - start) / ITERATIONS * 1000  # ms per query

print(f"Pickle marshalling time: {pickle_overhead:.4f} ms/query")
print(f"  - This includes: request serialization, deserialization, response serialization, deserialization")

# ============================================================================
# 3. Socket communication overhead (raw, no application logic)
# ============================================================================
print("\n3. SOCKET COMMUNICATION (localhost)")
print("-" * 80)

# Create a minimal echo server
class MinimalEchoServer:
    def echo(self, data):
        return data

echo_port = 25500
server_ready = threading.Event()

def run_echo_server():
    listener = Listener(('localhost', echo_port))
    server_ready.set()

    while True:
        conn = listener.accept()
        try:
            while True:
                msg = conn.recv()
                conn.send(msg)
        except (EOFError, ConnectionResetError):
            conn.close()
            break

# Start echo server
server_thread = threading.Thread(target=run_echo_server, daemon=True)
server_thread.start()
server_ready.wait(timeout=2)
time.sleep(0.1)  # Extra time to ensure ready

echo_conn = Client(('localhost', echo_port))

# Measure round-trip time for minimal message
start = time.perf_counter()
for i in range(ITERATIONS):
    echo_conn.send(42)
    result = echo_conn.recv()

socket_overhead = (time.perf_counter() - start) / ITERATIONS * 1000

print(f"Socket round-trip time: {socket_overhead:.4f} ms/query")
print(f"  - This is raw socket overhead for localhost (no serialization, no processing)")

echo_conn.close()

# ============================================================================
# 4. Combined: Socket + Pickle (message passing overhead)
# ============================================================================
print("\n4. COMBINED: Socket + Pickle overhead")
print("-" * 80)

ipc_port = 25501
ipc_ready = threading.Event()

def run_ipc_server():
    listener = Listener(('localhost', ipc_port))
    ipc_ready.set()

    while True:
        conn = listener.accept()
        try:
            while True:
                msg = conn.recv()  # Automatic pickle deserialization
                conn.send(msg)  # Automatic pickle serialization
        except (EOFError, ConnectionResetError):
            conn.close()
            break

# Start IPC server
ipc_thread = threading.Thread(target=run_ipc_server, daemon=True)
ipc_thread.start()
ipc_ready.wait(timeout=2)
time.sleep(0.1)

ipc_conn = Client(('localhost', ipc_port))

# Measure round-trip with pickle
start = time.perf_counter()
for i in range(ITERATIONS):
    ipc_conn.send(('execute', query, params))
    result = ipc_conn.recv()

ipc_overhead = (time.perf_counter() - start) / ITERATIONS * 1000

print(f"IPC (socket+pickle) time: {ipc_overhead:.4f} ms/query")
print(f"  - This combines socket communication with automatic pickle serialization")

ipc_conn.close()

# ============================================================================
# 5. Thread locking overhead
# ============================================================================
print("\n5. THREAD LOCKING OVERHEAD")
print("-" * 80)

test_lock = threading.Lock()

start = time.perf_counter()
for i in range(ITERATIONS):
    with test_lock:
        # Simulate minimal work
        _ = i * 2

locking_overhead = (time.perf_counter() - start) / ITERATIONS * 1000

print(f"Thread lock acquisition time: {locking_overhead:.4f} ms/query")
print(f"  - This is uncontended lock (best case)")

# ============================================================================
# 6. Method dispatch overhead
# ============================================================================
print("\n6. METHOD DISPATCH OVERHEAD")
print("-" * 80)

# Simulate the manual dispatch logic in MPServer
def dispatch(message):
    method_name = message[0]
    if method_name == 'execute':
        return "result"
    elif method_name == 'ping':
        return "pong"
    return None

start = time.perf_counter()
for i in range(ITERATIONS):
    message = ('execute', query, params)
    result = dispatch(message)

dispatch_overhead = (time.perf_counter() - start) / ITERATIONS * 1000

print(f"Method dispatch time: {dispatch_overhead:.4f} ms/query")
print(f"  - This is the manual routing logic overhead")

# ============================================================================
# 7. Full NetSQLite-MP overhead (for comparison)
# ============================================================================
print("\n7. ACTUAL NETSQLITE-MP OVERHEAD")
print("-" * 80)

remote_con = netsqlite_mp.connect(":memory:")
remote_con.execute("CREATE TABLE test(a int, b int);")

start = time.perf_counter()
for i in range(ITERATIONS):
    remote_con.execute("INSERT INTO test VALUES(?, ?)", (i % 100, (i * 2) % 100))

netsqlite_mp_time = (time.perf_counter() - start) / ITERATIONS * 1000
total_overhead = netsqlite_mp_time - direct_sqlite_time

print(f"NetSQLite-MP total time: {netsqlite_mp_time:.4f} ms/query")
print(f"NetSQLite-MP overhead: {total_overhead:.4f} ms/query")

remote_con.execute("DROP TABLE test;")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("OVERHEAD BREAKDOWN SUMMARY")
print("=" * 80)

print(f"\nDirect SQLite execution:     {direct_sqlite_time:7.4f} ms")
print(f"Pickle serialization:        {pickle_overhead:7.4f} ms  ({pickle_overhead/total_overhead*100:5.1f}%)")
print(f"Socket communication:        {socket_overhead:7.4f} ms  ({socket_overhead/total_overhead*100:5.1f}%)")
print(f"IPC (socket+pickle):         {ipc_overhead:7.4f} ms  ({ipc_overhead/total_overhead*100:5.1f}%)")
print(f"Thread locking:              {locking_overhead:7.4f} ms  ({locking_overhead/total_overhead*100:5.1f}%)")
print(f"Method dispatch:             {dispatch_overhead:7.4f} ms  ({dispatch_overhead/total_overhead*100:5.1f}%)")
print(f"Unaccounted overhead:        {max(0, total_overhead - ipc_overhead - locking_overhead - dispatch_overhead):7.4f} ms")
print(f"{'-' * 80}")
print(f"Total NetSQLite-MP overhead: {total_overhead:7.4f} ms  (100.0%)")
print(f"Total NetSQLite-MP time:     {netsqlite_mp_time:7.4f} ms")

print("\n" + "=" * 80)
print("COMPARISON WITH XML-RPC")
print("=" * 80)

# From previous profiling, XML-RPC overhead is ~1.76ms
xmlrpc_overhead = 1.76
improvement_factor = xmlrpc_overhead / total_overhead

print(f"\nXML-RPC total overhead:      {xmlrpc_overhead:.4f} ms")
print(f"MP total overhead:           {total_overhead:.4f} ms")
print(f"Improvement:                 {improvement_factor:.2f}x faster")
print(f"Time saved per query:        {xmlrpc_overhead - total_overhead:.4f} ms")

print("\n" + "=" * 80)
print("KEY FINDINGS")
print("=" * 80)

print("\n1. Serialization efficiency:")
print(f"   - Pickle: {pickle_overhead:.4f} ms ({pickle_overhead/total_overhead*100:.1f}% of overhead)")
print(f"   - XML: ~0.05 ms (3% of XML-RPC overhead)")
print(f"   → Pickle is slightly slower but not the bottleneck")

print("\n2. IPC efficiency:")
print(f"   - multiprocessing.connection (socket+pickle): {ipc_overhead:.4f} ms")
print(f"   - XML-RPC (TCP+HTTP+XML): ~1.72 ms")
print(f"   → {(1.72/ipc_overhead):.1f}x faster IPC mechanism")

print("\n3. Main improvement sources:")
print(f"   - No HTTP overhead (headers, parsing)")
print(f"   - More efficient socket handling")
print(f"   - Simpler protocol stack")

print(f"\n4. Remaining overhead ({total_overhead:.2f}ms) breakdown:")
print(f"   - IPC communication: ~{ipc_overhead:.2f}ms ({ipc_overhead/total_overhead*100:.0f}%)")
print(f"   - Application logic: ~{total_overhead - ipc_overhead:.2f}ms ({(total_overhead - ipc_overhead)/total_overhead*100:.0f}%)")
