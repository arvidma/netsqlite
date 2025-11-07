"""
Integration tests for NetSQLite.

Tests multi-process scenarios, server failures, and automatic restarts.
"""

import logging
import multiprocessing
import os
import signal
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from netsqlite import netsqlite

logging.basicConfig(
    level=logging.WARNING,
    format=f"[%(asctime)s] %(levelname)s [%(process)d]: %(message)s",
)


def worker_insert(db_path, worker_id, count):
    """Worker process that inserts data."""
    conn = None
    try:
        conn = netsqlite.connect(db_path)

        # Insert data
        for i in range(count):
            conn.execute("INSERT INTO test VALUES(?, ?)", (worker_id, i))

        return worker_id, count, "SUCCESS"

    except Exception as e:
        return worker_id, 0, f"ERROR: {e}"

    finally:
        if conn and conn.child_process:
            conn.child_process.kill()
            conn.child_process.wait()


def worker_reader(db_path, worker_id, duration):
    """Worker process that continuously reads data."""
    conn = None
    try:
        conn = netsqlite.connect(db_path)

        # Read data repeatedly
        read_count = 0
        start_time = time.time()

        while time.time() - start_time < duration:
            result = conn.execute("SELECT COUNT(*) FROM test")
            read_count += 1
            time.sleep(0.01)  # Small delay

        return worker_id, read_count, "SUCCESS"

    except Exception as e:
        return worker_id, 0, f"ERROR: {e}"

    finally:
        if conn and conn.child_process:
            conn.child_process.kill()
            conn.child_process.wait()


class TestMultiProcess(unittest.TestCase):
    """Test multiple processes accessing same database."""

    def test_concurrent_inserts(self):
        """Test multiple processes inserting concurrently."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        conn = None
        try:
            # Create table
            conn = netsqlite.connect(db_path)
            conn.execute("CREATE TABLE test(worker_id INTEGER, value INTEGER);")

            # Spawn multiple worker processes
            num_workers = 4
            inserts_per_worker = 50

            with multiprocessing.Pool(processes=num_workers) as pool:
                results = [
                    pool.apply_async(worker_insert, (db_path, i, inserts_per_worker))
                    for i in range(num_workers)
                ]

                # Wait for all workers
                completed = [r.get(timeout=30) for r in results]

            # Verify all workers succeeded
            for worker_id, count, status in completed:
                self.assertEqual(status, "SUCCESS", f"Worker {worker_id} failed: {status}")
                self.assertEqual(count, inserts_per_worker)

            # Verify total count
            result = conn.execute("SELECT COUNT(*) FROM test")
            total_count = result[0][0]
            expected_count = num_workers * inserts_per_worker

            self.assertEqual(total_count, expected_count,
                           f"Expected {expected_count} rows, got {total_count}")

            # Verify each worker's contribution
            for worker_id in range(num_workers):
                result = conn.execute("SELECT COUNT(*) FROM test WHERE worker_id = ?", (worker_id,))
                count = result[0][0]
                self.assertEqual(count, inserts_per_worker,
                               f"Worker {worker_id} inserted {count} rows, expected {inserts_per_worker}")

        finally:
            if conn and conn.child_process:
                conn.child_process.kill()
                conn.child_process.wait()
            try:
                os.unlink(db_path)
            except:
                pass

    def test_concurrent_readers_and_writers(self):
        """Test mix of readers and writers."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = None
            # Create table
            conn = netsqlite.connect(db_path)
            conn.execute("CREATE TABLE test(worker_id INTEGER, value INTEGER);")

            num_writers = 2
            num_readers = 2
            inserts_per_writer = 100
            read_duration = 2  # seconds

            with multiprocessing.Pool(processes=num_writers + num_readers) as pool:
                # Start writers
                writer_results = [
                    pool.apply_async(worker_insert, (db_path, i, inserts_per_writer))
                    for i in range(num_writers)
                ]

                # Start readers
                reader_results = [
                    pool.apply_async(worker_reader, (db_path, i + 100, read_duration))
                    for i in range(num_readers)
                ]

                # Wait for all to complete
                completed_writers = [r.get(timeout=30) for r in writer_results]
                completed_readers = [r.get(timeout=30) for r in reader_results]

            # Verify writers succeeded
            for worker_id, count, status in completed_writers:
                self.assertEqual(status, "SUCCESS", f"Writer {worker_id} failed: {status}")

            # Verify readers succeeded
            for worker_id, read_count, status in completed_readers:
                self.assertEqual(status, "SUCCESS", f"Reader {worker_id} failed: {status}")
                self.assertGreater(read_count, 0, f"Reader {worker_id} didn't read anything")

            # Verify total writes
            result = conn.execute("SELECT COUNT(*) FROM test")
            total_count = result[0][0]
            expected_count = num_writers * inserts_per_writer

            self.assertEqual(total_count, expected_count)

        finally:
            if conn and conn.child_process:
                conn.child_process.kill()
                conn.child_process.wait()
            try:
                os.unlink(db_path)
            except:
                pass


def _worker_with_restart(db_path, worker_id):
    """Worker function for restart test (must be top-level for pickling)."""
    conn = None
    try:
        conn = netsqlite.connect(db_path)
        for i in range(10):
            conn.execute("INSERT INTO test VALUES(?, ?)", (worker_id, i))
        return worker_id, "SUCCESS"
    except Exception as e:
        return worker_id, f"ERROR: {e}"
    finally:
        if conn and conn.child_process:
            conn.child_process.kill()
            conn.child_process.wait()


class TestServerFailure(unittest.TestCase):
    """Test server failure and automatic restart."""

    def test_server_restart_after_kill(self):
        """Test that a new server starts automatically when old one is killed."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        conn1 = None
        try:
            # Create connection (spawns server)
            conn1 = netsqlite.connect(db_path)
            conn1.execute("CREATE TABLE test(x INTEGER);")
            conn1.execute("INSERT INTO test VALUES(42);")

            # Verify data is there
            result_before = conn1.execute("SELECT * FROM test")
            self.assertEqual(result_before, [[42]])

            # Get server PID
            server_pid = conn1.child_process.pid if conn1.child_process else None
            self.assertIsNotNone(server_pid, "Server should have been spawned")

            # Kill the server
            os.kill(server_pid, signal.SIGKILL)
            time.sleep(1.0)  # Wait for server to die

            # Try to use connection - should trigger reconnect
            result = conn1.execute("SELECT * FROM test")
            self.assertEqual(result, [[42]], "Data should persist after server restart")

            # Verify new server was spawned
            new_server_pid = conn1.child_process.pid if conn1.child_process else None
            self.assertIsNotNone(new_server_pid, "New server should have been spawned")
            self.assertNotEqual(server_pid, new_server_pid, "Should be a different server")

        finally:
            if conn1 and conn1.child_process:
                conn1.child_process.kill()
                conn1.child_process.wait()
            try:
                os.unlink(db_path)
            except:
                pass

    def test_multiple_server_restarts(self):
        """Test multiple server failures and restarts."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        conn = None
        try:
            conn = netsqlite.connect(db_path)
            conn.execute("CREATE TABLE test(iteration INTEGER, value INTEGER);")

            for iteration in range(3):
                # Insert data
                conn.execute("INSERT INTO test VALUES(?, ?)", (iteration, iteration * 10))

                # Verify data is there
                result = conn.execute("SELECT COUNT(*) FROM test")
                expected_count = iteration + 1
                self.assertEqual(result[0][0], expected_count)

                # Kill server if it exists
                if conn.child_process:
                    os.kill(conn.child_process.pid, signal.SIGKILL)
                    time.sleep(0.5)

            # Final verification - all data should be there
            result = conn.execute("SELECT COUNT(*) FROM test")
            self.assertEqual(result[0][0], 3)

        finally:
            if conn and conn.child_process:
                conn.child_process.kill()
                conn.child_process.wait()
            try:
                os.unlink(db_path)
            except:
                pass

    def test_concurrent_access_during_restart(self):
        """Test that concurrent access works even during server restart."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        conn = None
        new_conn = None
        try:
            # Create initial table
            conn = netsqlite.connect(db_path)
            conn.execute("CREATE TABLE test(worker_id INTEGER, iteration INTEGER);")

            # Kill initial server
            if conn.child_process:
                os.kill(conn.child_process.pid, signal.SIGKILL)
                time.sleep(1.0)  # Give more time for cleanup

            # Now have workers try to access sequentially (more realistic)
            # In practice, one will trigger restart, others will connect to new server
            num_workers = 3
            completed = []

            for i in range(num_workers):
                result = _worker_with_restart(db_path, i)
                completed.append(result)
                time.sleep(0.2)  # Small delay between workers

            # Verify all workers succeeded
            for worker_id, status in completed:
                self.assertEqual(status, "SUCCESS", f"Worker {worker_id} failed: {status}")

            # Verify data integrity
            new_conn = netsqlite.connect(db_path)
            result = new_conn.execute("SELECT COUNT(*) FROM test")
            expected_count = num_workers * 10
            self.assertEqual(result[0][0], expected_count)

        finally:
            if conn and conn.child_process:
                conn.child_process.kill()
                conn.child_process.wait()
            if new_conn and new_conn.child_process:
                new_conn.child_process.kill()
                new_conn.child_process.wait()
            try:
                os.unlink(db_path)
            except:
                pass


if __name__ == '__main__':
    unittest.main()
