"""
An easy way to share an SQLite databases across multiple processes/threads *on same machine*,
with less risk of weird locking issues than if going via shared file system.

Single file and only standard-library dependencies.

Compatible with Python 3.6 and newer.

About 300x overhead compared to normal sqlite3, allowing 3000+ queries/second!
"""

import logging
import os
import sqlite3
import subprocess
import sys
import threading
from multiprocessing.connection import Client, Listener
from time import sleep
from typing import Any, Optional, Sequence, Union

log = logging.getLogger(__name__)

DUMMY_QUERY = "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1;"
STARTPORT = 25432
SPAWN_COMMAND = "spawn"

ExecuteReturnType = Optional[Sequence[Sequence[Any]]]
ExecuteParamType = Optional[Sequence[Union[str, int]]]


class NetSQLiteConnection:
    def __init__(self, conn, database_name: str, port: int):
        self.database_name = database_name
        self.conn = conn
        self.port = port
        self.child_process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def _send_receive(self, message):
        with self._lock:
            try:
                self.conn.send(message)
                response = self.conn.recv()

                if isinstance(response, Exception):
                    raise response

                return response
            except (EOFError, ConnectionResetError, BrokenPipeError) as e:
                raise ConnectionError(f"Connection to server lost: {e}")

    def execute(self, query: str, params: ExecuteParamType = None, check=True) -> ExecuteReturnType:
        if check and not self.are_we_gainfully_connected():
            new_conn = connect(self.database_name)
            self.conn = new_conn.conn
            self.child_process = new_conn.child_process

        if not params:
            params = tuple()

        return self._send_receive(('execute', query, params))

    def are_we_gainfully_connected(self):
        try:
            self._send_receive(('ping',))
            return True
        except (ConnectionError, EOFError, OSError):
            return False

    def __del__(self):
        if self.child_process:
            self.child_process.kill()
        try:
            self.conn.close()
        except:
            pass


class NetSQLiteServer:
    def __init__(self, db_path: str, port: int):
        self.db_path = db_path
        self.port = port
        self.lock = threading.Lock()
        self.connection = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self.listener = Listener(('localhost', port))
        self.running = True

    def target_database(self):
        return self.db_path

    def execute(
            self, query: str, params: Optional[Sequence[Any]] = None
    ) -> Optional[Sequence[Sequence[Any]]]:
        log.debug(f"Query: {query} with parameters: {params}")
        if not params:
            params = tuple()

        with self.lock:
            res = self.connection.execute(query, params).fetchall()
        return [list(row) for row in res]

    def handle_client(self, conn):
        try:
            while True:
                message = conn.recv()

                if not isinstance(message, tuple) or len(message) == 0:
                    conn.send(Exception("Invalid message format"))
                    continue

                method_name = message[0]

                try:
                    if method_name == 'execute':
                        if len(message) < 3:
                            result = Exception("execute requires query and params")
                        else:
                            result = self.execute(message[1], message[2])

                    elif method_name == 'target_database':
                        result = self.target_database()

                    elif method_name == 'ping':
                        result = 'pong'

                    else:
                        result = Exception(f"Unknown method: {method_name}")

                    conn.send(result)

                except Exception as e:
                    log.error(f"Error handling {method_name}: {e}")
                    conn.send(e)

        except (EOFError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            conn.close()

    def serve_forever(self):
        log.info(f"NetSQLite server listening on port {self.port}")
        try:
            while self.running:
                conn = self.listener.accept()
                log.debug(f"Client connected")

                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(conn,),
                    daemon=True
                )
                client_thread.start()

        except KeyboardInterrupt:
            log.info("Server shutting down")
        finally:
            self.listener.close()


def __server_startup__(port: int, database_name: str):
    log.info("Hello! The NetSQLite server-component is being launched.")
    log.info(f"Connected to sqlite database: '{database_name}'")

    server = NetSQLiteServer(database_name, port)
    log.info(f"Listener instantiated on port {port}")
    log.info("Calling .serve_forever()")
    server.serve_forever()


def __spawn_server_process__(db_name: str, port: int) -> subprocess.Popen:
    proc = subprocess.Popen(["python", __file__, SPAWN_COMMAND, db_name, str(port)])
    log.info(f"An sqlite server was spawned with PID {proc.pid}")
    return proc


def __poll(port: int, db_name: str, timeout: float = 10.0):
    wait = 0.1
    total_waited = 0

    while total_waited < timeout:
        try:
            conn = Client(('localhost', port))
            conn.send(('target_database',))
            response = conn.recv()

            if response == db_name:
                return conn

            conn.close()
            raise RuntimeError(f"Server on port {port} serves different database: {response}")

        except (ConnectionRefusedError, OSError):
            log.info(f"Sleeping {wait} seconds to let server start up.")
            sleep(wait)
            total_waited += wait
            wait = min(wait * 1.5, 1.0)

    raise RuntimeError(f"Giving up waiting for spawned server after {total_waited}+ seconds.")


def connect(db_name: str):
    for port_offset in range(10):
        port = STARTPORT + port_offset

        try:
            conn = Client(('localhost', port))
            conn.send(('target_database',))
            response = conn.recv()

            if response != db_name:
                conn.close()
                log.warning(f"A server is already running on port {port}, "
                            "but serving another database.")
                continue

            conn.send(('ping',))
            conn.recv()

            log.info(f"Connected to existing server on port {port}")
            return NetSQLiteConnection(conn, db_name, port)

        except (ConnectionRefusedError, OSError):
            log.info(f"No server on port {port}, spawning one")
            proc = __spawn_server_process__(db_name=db_name, port=port)
            conn = __poll(port, db_name)

            nsql_conn = NetSQLiteConnection(conn, db_name, port)
            nsql_conn.child_process = proc
            return nsql_conn

    raise RuntimeError(f"Could not create connection to '{db_name}'")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=f"[%(asctime)s] %(levelname)s [{os.getpid()}:%(name)s]: %(message)s"
    )

    if len(sys.argv) == 4 and sys.argv[1] == SPAWN_COMMAND:
        __server_startup__(port=int(sys.argv[3]), database_name=sys.argv[2])

    else:
        filnamn = os.path.basename(__file__)
        print(f"SYNTAX ERROR: {filnamn} {' '.join(sys.argv)}")
        print(f"Usage: {filnamn} {SPAWN_COMMAND} <database_file_path> <port-number>")
