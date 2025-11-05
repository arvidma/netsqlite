import logging
import os
import sqlite3
from datetime import datetime

from netsqlite import netsqlite

logging.basicConfig(
    level=logging.WARNING,  # Reduce noise
    format=f"[%(asctime)s] %(levelname)s [{os.getpid()}:%(name)s]: %(message)s",
)

print("=" * 80)
print("Extended Performance Test - NetSQLite vs SQLite")
print("=" * 80)

# First, establish connection (this includes server startup time)
print("\n1. Initial connection (includes server startup overhead)...")
remote_con = netsqlite.connect(":memory:")
print("   NetSQLite server is now running!\n")

def benchmark(some_con, times=1000, label=""):
    ts = datetime.now()
    some_con.execute("CREATE TABLE test_table(col1 int, col2 int);")
    for n in range(times):
        # Use modulo to keep numbers small and avoid XML-RPC overflow
        some_con.execute("INSERT INTO test_table VALUES(?, ?)", (n % 1000, (n * n) % 1000))

    dur = (datetime.now() - ts).total_seconds()
    qps = times / dur if dur > 0 else 0

    print(f"{label}:")
    print(f"  - Total time: {dur:.4f} seconds")
    print(f"  - Time per query: {dur/times*1000:.4f} ms")
    print(f"  - Queries per second: {qps:.0f}")

    # Cleanup
    some_con.execute("DROP TABLE test_table;")
    return dur

# Test different query counts
for count in [1000, 10000, 50000]:
    print(f"\n{'='*80}")
    print(f"Testing with {count} queries")
    print(f"{'='*80}")

    local_con = sqlite3.connect(":memory:")
    local_time = benchmark(local_con, times=count, label=f"Local SQLite ({count} queries)")

    print()
    remote_time = benchmark(remote_con, times=count, label=f"NetSQLite ({count} queries)")

    overhead_factor = remote_time / local_time if local_time > 0 else 0
    print(f"\n  => NetSQLite is {overhead_factor:.1f}x slower than local SQLite")
    local_con.close()

print("\n" + "=" * 80)
print("Test complete!")
print("=" * 80)
