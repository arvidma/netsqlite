"""
Profiling test to identify where NetSQLite overhead comes from.

Breaks down the ~1.4ms overhead into components:
- XML serialization/deserialization
- Network/socket communication
- Thread locking on server
- Actual SQLite execution
"""

import logging
import os
import sqlite3
import time
import xmlrpc.client
from xmlrpc.server import SimpleXMLRPCServer
import threading
import subprocess
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from netsqlite import netsqlite

logging.basicConfig(
    level=logging.WARNING,
    format=f"[%(asctime)s] %(levelname)s [{os.getpid()}:%(name)s]: %(message)s",
)

ITERATIONS = 1000

print("=" * 80)
print("NetSQLite Overhead Profiling Analysis")
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
# 2. XML Serialization/Deserialization overhead
# ============================================================================
print("\n2. XML SERIALIZATION/DESERIALIZATION")
print("-" * 80)

query = "INSERT INTO test VALUES(?, ?)"
params = (42, 84)

# Measure XML-RPC marshalling
start = time.perf_counter()
for i in range(ITERATIONS):
    # Simulate what XML-RPC does: marshal the request
    request_xml = xmlrpc.client.dumps((query, params), methodname='execute')
    # Unmarshal on server side
    method, params_back = xmlrpc.client.loads(request_xml)
    # Marshal response
    response_xml = xmlrpc.client.dumps(([[1, 2]],), methodresponse=True)
    # Unmarshal response on client
    result = xmlrpc.client.loads(response_xml)

xml_overhead = (time.perf_counter() - start) / ITERATIONS * 1000  # ms per query

print(f"XML marshalling time: {xml_overhead:.4f} ms/query")
print(f"  - This includes: request serialization, deserialization, response serialization, deserialization")

# ============================================================================
# 3. Network/Socket communication overhead
# ============================================================================
print("\n3. NETWORK/SOCKET COMMUNICATION")
print("-" * 80)

# Create a minimal XML-RPC server for testing
class DummyServer:
    def echo(self, data):
        return data

dummy_port = 25500
server_ready = threading.Event()

def run_dummy_server():
    with SimpleXMLRPCServer(("localhost", dummy_port), logRequests=False) as server:
        server.register_instance(DummyServer())
        server_ready.set()
        server.serve_forever()

# Start dummy server
server_thread = threading.Thread(target=run_dummy_server, daemon=True)
server_thread.start()
server_ready.wait(timeout=2)
time.sleep(0.1)  # Extra time to ensure ready

dummy_proxy = xmlrpc.client.ServerProxy(f"http://localhost:{dummy_port}/")

# Measure round-trip time for minimal RPC call
start = time.perf_counter()
for i in range(ITERATIONS):
    result = dummy_proxy.echo(42)

network_overhead = (time.perf_counter() - start) / ITERATIONS * 1000

print(f"Network round-trip time: {network_overhead:.4f} ms/query")
print(f"  - This includes: TCP/socket overhead for localhost communication")

# ============================================================================
# 4. Thread locking overhead (simulated)
# ============================================================================
print("\n4. THREAD LOCKING OVERHEAD")
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
# 5. Full NetSQLite overhead (for comparison)
# ============================================================================
print("\n5. ACTUAL NETSQLITE OVERHEAD")
print("-" * 80)

remote_con = netsqlite.connect(":memory:")
remote_con.execute("CREATE TABLE test(a int, b int);")

start = time.perf_counter()
for i in range(ITERATIONS):
    remote_con.execute("INSERT INTO test VALUES(?, ?)", (i % 100, (i * 2) % 100))

netsqlite_time = (time.perf_counter() - start) / ITERATIONS * 1000
total_overhead = netsqlite_time - direct_sqlite_time

print(f"NetSQLite total time: {netsqlite_time:.4f} ms/query")
print(f"NetSQLite overhead: {total_overhead:.4f} ms/query")

remote_con.execute("DROP TABLE test;")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("OVERHEAD BREAKDOWN SUMMARY")
print("=" * 80)

print(f"\nDirect SQLite execution:     {direct_sqlite_time:7.4f} ms")
print(f"XML serialization overhead:  {xml_overhead:7.4f} ms  ({xml_overhead/total_overhead*100:5.1f}%)")
print(f"Network/socket overhead:     {network_overhead:7.4f} ms  ({network_overhead/total_overhead*100:5.1f}%)")
print(f"Thread locking overhead:     {locking_overhead:7.4f} ms  ({locking_overhead/total_overhead*100:5.1f}%)")
print(f"Unaccounted overhead:        {max(0, total_overhead - xml_overhead - network_overhead - locking_overhead):7.4f} ms")
print(f"{'-' * 80}")
print(f"Total NetSQLite overhead:    {total_overhead:7.4f} ms  (100.0%)")
print(f"Total NetSQLite time:        {netsqlite_time:7.4f} ms")

print("\n" + "=" * 80)
print("OPTIMIZATION OPPORTUNITIES")
print("=" * 80)

print("\nBased on the breakdown:")
print(f"  1. XML-RPC overhead: {xml_overhead:.2f} ms ({xml_overhead/total_overhead*100:.0f}%)")
print("     → Consider: MessagePack, Protocol Buffers, or JSON-RPC")
print(f"  2. Network overhead: {network_overhead:.2f} ms ({network_overhead/total_overhead*100:.0f}%)")
print("     → Consider: Unix domain sockets instead of TCP")
print(f"  3. Locking overhead: {locking_overhead:.2f} ms ({locking_overhead/total_overhead*100:.0f}%)")
print("     → Already minimal for single-threaded access")
print(f"\nPotential speedup: {total_overhead / max(locking_overhead + direct_sqlite_time, 0.001):.1f}x faster with optimal protocol")
