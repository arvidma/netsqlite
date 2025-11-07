"""
Functional tests for NetSQLite.

Tests basic functionality: CRUD operations, queries, parameters, etc.
"""

import logging
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from netsqlite import netsqlite

logging.basicConfig(
    level=logging.WARNING,
    format=f"[%(asctime)s] %(levelname)s: %(message)s",
)


class TestBasicFunctionality(unittest.TestCase):
    """Test basic CRUD operations."""

    def setUp(self):
        self.conn = netsqlite.connect(":memory:")
        self.conn.execute("CREATE TABLE test(id INTEGER PRIMARY KEY, name TEXT, value INTEGER);")

    def tearDown(self):
        if hasattr(self, 'conn') and self.conn.child_process:
            self.conn.child_process.kill()
            self.conn.child_process.wait()

    def test_insert(self):
        """Test INSERT with parameters."""
        self.conn.execute("INSERT INTO test VALUES(?, ?, ?)", (1, "Alice", 100))
        result = self.conn.execute("SELECT * FROM test WHERE id = ?", (1,))
        self.assertEqual(result, [[1, "Alice", 100]])

    def test_insert_multiple(self):
        """Test multiple INSERTs."""
        for i in range(5):
            self.conn.execute("INSERT INTO test VALUES(?, ?, ?)", (i, f"User{i}", i * 10))

        result = self.conn.execute("SELECT COUNT(*) FROM test")
        self.assertEqual(result[0][0], 5)

    def test_select_where(self):
        """Test SELECT with WHERE clause."""
        self.conn.execute("INSERT INTO test VALUES(1, 'Alice', 100)")
        self.conn.execute("INSERT INTO test VALUES(2, 'Bob', 200)")
        self.conn.execute("INSERT INTO test VALUES(3, 'Charlie', 300)")

        result = self.conn.execute("SELECT name FROM test WHERE value > ?", (150,))
        self.assertEqual(len(result), 2)
        self.assertIn(['Bob'], result)
        self.assertIn(['Charlie'], result)

    def test_update(self):
        """Test UPDATE operation."""
        self.conn.execute("INSERT INTO test VALUES(1, 'Alice', 100)")
        self.conn.execute("UPDATE test SET value = ? WHERE id = ?", (999, 1))

        result = self.conn.execute("SELECT value FROM test WHERE id = ?", (1,))
        self.assertEqual(result[0][0], 999)

    def test_delete(self):
        """Test DELETE operation."""
        self.conn.execute("INSERT INTO test VALUES(1, 'Alice', 100)")
        self.conn.execute("INSERT INTO test VALUES(2, 'Bob', 200)")

        self.conn.execute("DELETE FROM test WHERE id = ?", (1,))
        result = self.conn.execute("SELECT COUNT(*) FROM test")
        self.assertEqual(result[0][0], 1)


class TestAggregation(unittest.TestCase):
    """Test aggregation functions."""

    def setUp(self):
        self.conn = netsqlite.connect(":memory:")
        self.conn.execute("CREATE TABLE numbers(value INTEGER);")
        for i in range(1, 11):
            self.conn.execute("INSERT INTO numbers VALUES(?)", (i,))

    def tearDown(self):
        if hasattr(self, 'conn') and self.conn.child_process:
            self.conn.child_process.kill()
            self.conn.child_process.wait()

    def test_count(self):
        """Test COUNT aggregation."""
        result = self.conn.execute("SELECT COUNT(*) FROM numbers")
        self.assertEqual(result[0][0], 10)

    def test_sum(self):
        """Test SUM aggregation."""
        result = self.conn.execute("SELECT SUM(value) FROM numbers")
        self.assertEqual(result[0][0], 55)  # 1+2+...+10

    def test_avg(self):
        """Test AVG aggregation."""
        result = self.conn.execute("SELECT AVG(value) FROM numbers")
        self.assertEqual(result[0][0], 5.5)

    def test_min_max(self):
        """Test MIN and MAX."""
        result = self.conn.execute("SELECT MIN(value), MAX(value) FROM numbers")
        self.assertEqual(result[0], [1, 10])


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        self.conn = netsqlite.connect(":memory:")

    def tearDown(self):
        if hasattr(self, 'conn') and self.conn.child_process:
            self.conn.child_process.kill()
            self.conn.child_process.wait()

    def test_empty_table(self):
        """Test querying empty table."""
        self.conn.execute("CREATE TABLE empty(x int);")
        result = self.conn.execute("SELECT * FROM empty")
        self.assertEqual(result, [])

    def test_null_values(self):
        """Test NULL values."""
        self.conn.execute("CREATE TABLE nullable(id int, name TEXT);")
        self.conn.execute("INSERT INTO nullable VALUES(1, NULL)")

        result = self.conn.execute("SELECT * FROM nullable")
        self.assertEqual(result, [[1, None]])

    def test_large_numbers(self):
        """Test handling of large integers."""
        self.conn.execute("CREATE TABLE large(value INTEGER);")
        large_num = 2**31 - 1  # Max 32-bit signed int
        self.conn.execute("INSERT INTO large VALUES(?)", (large_num,))

        result = self.conn.execute("SELECT * FROM large")
        self.assertEqual(result[0][0], large_num)

    def test_special_characters(self):
        """Test special characters in strings."""
        self.conn.execute("CREATE TABLE special(text TEXT);")
        special_str = "Hello 'world' \"test\" \n\t\r"
        self.conn.execute("INSERT INTO special VALUES(?)", (special_str,))

        result = self.conn.execute("SELECT * FROM special")
        self.assertEqual(result[0][0], special_str)


class TestPersistence(unittest.TestCase):
    """Test database file persistence."""

    def test_file_database(self):
        """Test writing to and reading from file database."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        conn1 = None
        conn2 = None
        try:
            # Write data
            conn1 = netsqlite.connect(db_path)
            conn1.execute("CREATE TABLE test(x int);")
            conn1.execute("INSERT INTO test VALUES(42);")

            # Read data (new connection)
            conn2 = netsqlite.connect(db_path)
            result = conn2.execute("SELECT * FROM test")
            self.assertEqual(result, [[42]])

        finally:
            if conn1 and conn1.child_process:
                conn1.child_process.kill()
                conn1.child_process.wait()
            if conn2 and conn2.child_process:
                conn2.child_process.kill()
                conn2.child_process.wait()
            try:
                os.unlink(db_path)
            except:
                pass


class TestConnection(unittest.TestCase):
    """Test connection management."""

    def test_connection_check(self):
        """Test are_we_gainfully_connected()."""
        conn = netsqlite.connect(":memory:")
        try:
            self.assertTrue(conn.are_we_gainfully_connected())
        finally:
            if conn.child_process:
                conn.child_process.kill()
                conn.child_process.wait()

    def test_multiple_connections_same_db(self):
        """Test multiple connections to same database."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        conn1 = None
        conn2 = None
        try:
            conn1 = netsqlite.connect(db_path)
            conn1.execute("CREATE TABLE test(x int);")
            conn1.execute("INSERT INTO test VALUES(1);")

            # Second connection should connect to same server
            conn2 = netsqlite.connect(db_path)
            result = conn2.execute("SELECT * FROM test")
            self.assertEqual(result, [[1]])

        finally:
            if conn1 and conn1.child_process:
                conn1.child_process.kill()
                conn1.child_process.wait()
            if conn2 and conn2.child_process:
                conn2.child_process.kill()
                conn2.child_process.wait()
            try:
                os.unlink(db_path)
            except:
                pass


if __name__ == '__main__':
    unittest.main()
