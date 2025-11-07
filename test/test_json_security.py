"""
Test that JSON serialization is used instead of pickle, preventing RCE vulnerabilities.
"""

import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from netsqlite import netsqlite

logging.basicConfig(
    level=logging.WARNING,
    format=f"[%(asctime)s] %(levelname)s: %(message)s",
)


class TestJSONSerialization(unittest.TestCase):
    """Test that JSON serialization is secure and works correctly."""

    def test_json_handles_datetime_like_objects(self):
        """Test that default=str in JSON handles various object types."""
        conn = netsqlite.connect(":memory:")
        try:
            conn.execute("CREATE TABLE test(id int, data text);")

            # This would be problematic with pickle, but works fine with JSON+default=str
            # because we convert datetime to strings
            conn.execute("INSERT INTO test VALUES(?, ?)", (1, "2024-01-01"))
            result = conn.execute("SELECT * FROM test")
            self.assertEqual(result, [[1, "2024-01-01"]])
        finally:
            if conn.child_process:
                conn.child_process.kill()
                conn.child_process.wait()

    def test_json_handles_none_values(self):
        """Test that None/NULL values are handled correctly with JSON."""
        conn = netsqlite.connect(":memory:")
        try:
            conn.execute("CREATE TABLE test(id int, value text);")
            conn.execute("INSERT INTO test VALUES(?, ?)", (1, None))
            result = conn.execute("SELECT * FROM test")
            self.assertEqual(result, [[1, None]])
        finally:
            if conn.child_process:
                conn.child_process.kill()
                conn.child_process.wait()

    def test_json_handles_unicode(self):
        """Test that Unicode strings work correctly with JSON."""
        conn = netsqlite.connect(":memory:")
        try:
            conn.execute("CREATE TABLE test(text TEXT);")

            # Various Unicode strings
            test_strings = [
                "Hello 世界",
                "Émojis: 🔒🛡️",
                "Åäö ÅÄÖ",
                "Русский язык"
            ]

            for s in test_strings:
                conn.execute("INSERT INTO test VALUES(?)", (s,))

            result = conn.execute("SELECT * FROM test")
            self.assertEqual(result, [[s] for s in test_strings])
        finally:
            if conn.child_process:
                conn.child_process.kill()
                conn.child_process.wait()

    def test_json_handles_large_numbers(self):
        """Test that large numbers are handled correctly with JSON."""
        conn = netsqlite.connect(":memory:")
        try:
            conn.execute("CREATE TABLE test(value INTEGER);")

            large_num = 9007199254740991  # Max safe integer in JSON (2^53 - 1)
            conn.execute("INSERT INTO test VALUES(?)", (large_num,))
            result = conn.execute("SELECT * FROM test")
            self.assertEqual(result, [[large_num]])
        finally:
            if conn.child_process:
                conn.child_process.kill()
                conn.child_process.wait()

    def test_json_handles_lists_in_results(self):
        """Test that query results (lists of lists) work with JSON."""
        conn = netsqlite.connect(":memory:")
        try:
            conn.execute("CREATE TABLE test(a int, b int, c int);")
            conn.execute("INSERT INTO test VALUES(1, 2, 3)")
            conn.execute("INSERT INTO test VALUES(4, 5, 6)")
            conn.execute("INSERT INTO test VALUES(7, 8, 9)")

            result = conn.execute("SELECT * FROM test")
            self.assertEqual(result, [[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        finally:
            if conn.child_process:
                conn.child_process.kill()
                conn.child_process.wait()

    def test_serialization_functions(self):
        """Test the _serialize and _deserialize functions directly."""
        from netsqlite.netsqlite import _serialize, _deserialize

        # Test basic types
        test_cases = [
            ("string", "string"),
            (123, 123),
            (12.34, 12.34),
            (None, None),
            (True, True),
            (False, False),
            ([1, 2, 3], [1, 2, 3]),
            ({"a": 1}, {"a": 1}),
            (("tuple", "data"), ["tuple", "data"]),  # Tuples become lists in JSON
        ]

        for original, expected in test_cases:
            serialized = _serialize(original)
            deserialized = _deserialize(serialized)
            self.assertEqual(deserialized, expected)

    def test_exception_serialization(self):
        """Test that exceptions are serialized safely with JSON."""
        from netsqlite.netsqlite import _serialize, _deserialize

        # Create an exception
        original = Exception("Test error message")
        serialized = _serialize(original)
        deserialized = _deserialize(serialized)

        # Should be reconstructed as an exception
        self.assertIsInstance(deserialized, Exception)
        self.assertIn("Test error message", str(deserialized))


if __name__ == '__main__':
    unittest.main()
