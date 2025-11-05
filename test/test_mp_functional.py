"""
Functional correctness test for NetSQLite-MP implementation.

Tests that the multiprocessing.connection version produces the same
results as the XML-RPC version.
"""

import logging
import os
import sys
import tempfile

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from netsqlite import netsqlite, netsqlite_mp

logging.basicConfig(
    level=logging.WARNING,
    format=f"[%(asctime)s] %(levelname)s [{os.getpid()}:%(name)s]: %(message)s",
)

print("=" * 80)
print("NetSQLite-MP Functional Correctness Test")
print("=" * 80)

# Create temporary database file
db_file = tempfile.mktemp(suffix='.db')

try:
    print(f"\nUsing temporary database: {db_file}")

    # ========================================================================
    # Test 1: Basic connection and table creation
    # ========================================================================
    print("\n1. TEST: Basic connection and table creation")
    print("-" * 80)

    xmlrpc_conn = netsqlite.connect(db_file)
    mp_conn = netsqlite_mp.connect(db_file + "_mp")

    # Create tables
    xmlrpc_conn.execute("CREATE TABLE test(id INTEGER PRIMARY KEY, name TEXT, value INTEGER);")
    mp_conn.execute("CREATE TABLE test(id INTEGER PRIMARY KEY, name TEXT, value INTEGER);")

    print("✓ Tables created successfully")

    # ========================================================================
    # Test 2: Insert data
    # ========================================================================
    print("\n2. TEST: Insert data with parameters")
    print("-" * 80)

    test_data = [
        (1, "Alice", 100),
        (2, "Bob", 200),
        (3, "Charlie", 300),
        (4, "Diana", 400),
        (5, "Eve", 500),
    ]

    for row in test_data:
        xmlrpc_conn.execute("INSERT INTO test VALUES(?, ?, ?)", row)
        mp_conn.execute("INSERT INTO test VALUES(?, ?, ?)", row)

    print(f"✓ Inserted {len(test_data)} rows into each database")

    # ========================================================================
    # Test 3: Query and verify results
    # ========================================================================
    print("\n3. TEST: Query and verify results match")
    print("-" * 80)

    xmlrpc_result = xmlrpc_conn.execute("SELECT * FROM test ORDER BY id;")
    mp_result = mp_conn.execute("SELECT * FROM test ORDER BY id;")

    print(f"XML-RPC result: {len(xmlrpc_result)} rows")
    print(f"MP result:      {len(mp_result)} rows")

    if xmlrpc_result == mp_result:
        print("✓ Results match perfectly!")
    else:
        print("✗ MISMATCH!")
        print(f"  XML-RPC: {xmlrpc_result}")
        print(f"  MP:      {mp_result}")
        sys.exit(1)

    # ========================================================================
    # Test 4: Aggregation queries
    # ========================================================================
    print("\n4. TEST: Aggregation queries")
    print("-" * 80)

    queries = [
        "SELECT COUNT(*) FROM test;",
        "SELECT SUM(value) FROM test;",
        "SELECT AVG(value) FROM test;",
        "SELECT MAX(value) FROM test;",
        "SELECT MIN(value) FROM test;",
    ]

    for query in queries:
        xmlrpc_result = xmlrpc_conn.execute(query)
        mp_result = mp_conn.execute(query)

        if xmlrpc_result == mp_result:
            print(f"✓ {query:40} → {mp_result[0][0]}")
        else:
            print(f"✗ MISMATCH for {query}")
            print(f"  XML-RPC: {xmlrpc_result}")
            print(f"  MP:      {mp_result}")
            sys.exit(1)

    # ========================================================================
    # Test 5: WHERE clause with parameters
    # ========================================================================
    print("\n5. TEST: WHERE clause with parameters")
    print("-" * 80)

    query = "SELECT name, value FROM test WHERE value > ? ORDER BY value;"
    params = (250,)

    xmlrpc_result = xmlrpc_conn.execute(query, params)
    mp_result = mp_conn.execute(query, params)

    print(f"Query: {query} with params {params}")
    print(f"XML-RPC result: {xmlrpc_result}")
    print(f"MP result:      {mp_result}")

    if xmlrpc_result == mp_result:
        print("✓ Parameterized WHERE clause works correctly")
    else:
        print("✗ MISMATCH!")
        sys.exit(1)

    # ========================================================================
    # Test 6: Multiple clients (serial)
    # ========================================================================
    print("\n6. TEST: Multiple sequential queries")
    print("-" * 80)

    for i in range(10):
        result = mp_conn.execute("SELECT COUNT(*) FROM test WHERE id > ?;", (i,))
        expected_count = max(0, 5 - i)
        actual_count = result[0][0]

        if actual_count != expected_count:
            print(f"✗ MISMATCH at iteration {i}: expected {expected_count}, got {actual_count}")
            sys.exit(1)

    print("✓ 10 sequential queries completed successfully")

    # ========================================================================
    # Test 7: Update and Delete
    # ========================================================================
    print("\n7. TEST: Update and Delete operations")
    print("-" * 80)

    # Update
    mp_conn.execute("UPDATE test SET value = ? WHERE id = ?;", (999, 3))
    result = mp_conn.execute("SELECT value FROM test WHERE id = ?;", (3,))
    if result[0][0] == 999:
        print("✓ UPDATE works correctly")
    else:
        print(f"✗ UPDATE failed: expected 999, got {result[0][0]}")
        sys.exit(1)

    # Delete
    mp_conn.execute("DELETE FROM test WHERE id = ?;", (5,))
    result = mp_conn.execute("SELECT COUNT(*) FROM test;")
    if result[0][0] == 4:
        print("✓ DELETE works correctly")
    else:
        print(f"✗ DELETE failed: expected 4 rows, got {result[0][0]}")
        sys.exit(1)

    # ========================================================================
    # Test 8: target_database() method
    # ========================================================================
    print("\n8. TEST: target_database() method")
    print("-" * 80)

    xmlrpc_db = xmlrpc_conn.proxy.target_database()
    mp_db = mp_conn.target_database()

    print(f"XML-RPC database: {xmlrpc_db}")
    print(f"MP database:      {mp_db}")

    if xmlrpc_db == db_file and mp_db == db_file + "_mp":
        print("✓ target_database() returns correct paths")
    else:
        print("✗ target_database() mismatch")
        sys.exit(1)

    # ========================================================================
    # Test 9: Connection check
    # ========================================================================
    print("\n9. TEST: are_we_gainfully_connected() method")
    print("-" * 80)

    if xmlrpc_conn.are_we_gainfully_connected():
        print("✓ XML-RPC connection check passed")
    else:
        print("✗ XML-RPC connection check failed")
        sys.exit(1)

    if mp_conn.are_we_gainfully_connected():
        print("✓ MP connection check passed")
    else:
        print("✗ MP connection check failed")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("ALL FUNCTIONAL TESTS PASSED! ✓")
    print("=" * 80)
    print("\nThe multiprocessing.connection implementation is functionally equivalent")
    print("to the XML-RPC version.")

finally:
    # Cleanup
    try:
        if os.path.exists(db_file):
            os.unlink(db_file)
        if os.path.exists(db_file + "_mp"):
            os.unlink(db_file + "_mp")
    except:
        pass
