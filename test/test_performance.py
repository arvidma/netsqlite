"""
Performance tests for NetSQLite.

Compares NetSQLite performance with direct SQLite access.
"""

import logging
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from netsqlite import netsqlite

logging.basicConfig(
    level=logging.WARNING,
    format=f"[%(asctime)s] %(levelname)s: %(message)s",
)


def benchmark(conn, label, iterations=1000):
    """Run benchmark on a connection."""
    # Setup
    conn.execute("CREATE TABLE bench(a INTEGER, b INTEGER);")

    # Benchmark INSERTs
    start = time.perf_counter()
    for i in range(iterations):
        conn.execute("INSERT INTO bench VALUES(?, ?)", (i % 100, (i * 2) % 100))
    insert_duration = time.perf_counter() - start
    insert_qps = iterations / insert_duration

    # Benchmark SELECTs
    start = time.perf_counter()
    for i in range(iterations):
        conn.execute("SELECT * FROM bench WHERE a = ?", (i % 100,))
    select_duration = time.perf_counter() - start
    select_qps = iterations / select_duration

    # Cleanup
    conn.execute("DROP TABLE bench;")

    return {
        'label': label,
        'insert_qps': insert_qps,
        'insert_latency_ms': (insert_duration / iterations) * 1000,
        'select_qps': select_qps,
        'select_latency_ms': (select_duration / iterations) * 1000,
    }


def main():
    print("=" * 80)
    print("NetSQLite Performance Benchmark")
    print("=" * 80)

    iterations = 1000
    print(f"\nRunning {iterations} iterations of each test...\n")

    # Benchmark local SQLite
    local_conn = sqlite3.connect(":memory:")
    local_results = benchmark(local_conn, "Local SQLite", iterations)

    # Benchmark NetSQLite
    remote_conn = netsqlite.connect(":memory:")
    remote_results = benchmark(remote_conn, "NetSQLite", iterations)

    # Print results
    print(f"{'Implementation':<20} {'INSERT qps':<15} {'INSERT ms':<15} {'SELECT qps':<15} {'SELECT ms':<15}")
    print("-" * 80)

    for results in [local_results, remote_results]:
        print(f"{results['label']:<20} "
              f"{results['insert_qps']:>14.0f} "
              f"{results['insert_latency_ms']:>14.4f} "
              f"{results['select_qps']:>14.0f} "
              f"{results['select_latency_ms']:>14.4f}")

    # Calculate overhead
    insert_overhead = remote_results['insert_latency_ms'] / local_results['insert_latency_ms']
    select_overhead = remote_results['select_latency_ms'] / local_results['select_latency_ms']

    print("\n" + "=" * 80)
    print("Overhead Analysis")
    print("=" * 80)
    print(f"INSERT overhead: {insert_overhead:.1f}x slower")
    print(f"SELECT overhead: {select_overhead:.1f}x slower")
    print(f"Average overhead: {(insert_overhead + select_overhead) / 2:.1f}x slower")

    # Verify performance target
    target_qps = 2000
    if remote_results['insert_qps'] >= target_qps:
        print(f"\n✓ Performance target met: {remote_results['insert_qps']:.0f} qps >= {target_qps} qps")
    else:
        print(f"\n✗ Performance target NOT met: {remote_results['insert_qps']:.0f} qps < {target_qps} qps")

    print()


if __name__ == '__main__':
    main()
