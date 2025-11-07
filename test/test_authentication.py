"""
Test authentication functionality.
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


class TestAuthentication(unittest.TestCase):
    """Test authentication mechanisms."""

    def test_no_auth_backward_compatible(self):
        """Test that connections without auth still work (backward compatible)."""
        conn = netsqlite.connect(":memory:")
        try:
            conn.execute("CREATE TABLE test(x int);")
            conn.execute("INSERT INTO test VALUES(42);")
            result = conn.execute("SELECT * FROM test")
            self.assertEqual(result, [[42]])
        finally:
            if conn.child_process:
                conn.child_process.kill()
                conn.child_process.wait()

    def test_with_auth_success(self):
        """Test that authentication with correct token works."""
        token = "my_secret_token_123"
        conn = netsqlite.connect(":memory:", auth_token=token)
        try:
            conn.execute("CREATE TABLE test(x int);")
            conn.execute("INSERT INTO test VALUES(42);")
            result = conn.execute("SELECT * FROM test")
            self.assertEqual(result, [[42]])
        finally:
            if conn.child_process:
                conn.child_process.kill()
                conn.child_process.wait()

    def test_with_auth_multiple_clients(self):
        """Test that multiple clients with same token can connect."""
        token = "shared_secret_789"

        # First connection spawns server
        conn1 = netsqlite.connect(":memory:", auth_token=token)
        try:
            conn1.execute("CREATE TABLE test(x int);")
            conn1.execute("INSERT INTO test VALUES(1);")

            # Second connection should connect to same server
            conn2 = netsqlite.connect(":memory:", auth_token=token)
            try:
                result = conn2.execute("SELECT * FROM test")
                self.assertEqual(result, [[1]])

                # Both can write
                conn2.execute("INSERT INTO test VALUES(2);")
                result = conn1.execute("SELECT * FROM test ORDER BY x")
                self.assertEqual(result, [[1], [2]])

            finally:
                if conn2.child_process:
                    conn2.child_process.kill()
                    conn2.child_process.wait()

        finally:
            if conn1.child_process:
                conn1.child_process.kill()
                conn1.child_process.wait()

    def test_with_auth_wrong_token_fails(self):
        """Test that wrong authentication token is rejected."""
        correct_token = "correct_token"
        wrong_token = "wrong_token"

        # First connection with correct token
        conn1 = netsqlite.connect(":memory:", auth_token=correct_token)
        try:
            conn1.execute("CREATE TABLE test(x int);")

            # Try to connect with wrong token
            with self.assertRaises(Exception) as context:
                conn2 = netsqlite.connect(":memory:", auth_token=wrong_token)

            self.assertIn("Authentication failed", str(context.exception))

        finally:
            if conn1.child_process:
                conn1.child_process.kill()
                conn1.child_process.wait()


if __name__ == '__main__':
    unittest.main()
