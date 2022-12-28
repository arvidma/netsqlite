"""
An easy way to share an SQLite databases across multiple processes/threads *on same machine*,
with less risk of weird locking issues than if going via shared file system.

Single file and only standard-library dependencies.

Compatible with Python 3.6 and newer.

About 1000x overhead compared to normal sqlite3, but that still allows 10k queries/second
on the development machine!
"""

import logging
import os
import sqlite3
import subprocess
import sys
import threading
import xmlrpc.client
from time import sleep
from typing import Any, Optional, Sequence, Union
from xmlrpc.server import SimpleXMLRPCServer

log = logging.getLogger(__name__)

DUMMY_QUERY = "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1;"
STARTPORT = 25432
SPAWN_COMMAND = "spawn"

ExecuteReturnType = Optional[Sequence[Sequence[Any]]]  # TypeAlias is only supported from 3.10
ExecuteParamType = Optional[Sequence[Union[str, int]]]


class NetSQLiteConnection:
    def __init__(self, port: int, database_name: str):
        self.database_name = database_name
        self.proxy = xmlrpc.client.ServerProxy(f"http://localhost:{port}/")
        self.child_process: Optional[subprocess.Popen] = None

    def execute(self, query: str, params: ExecuteParamType = None, check=True) -> ExecuteReturnType:
        if check and not self.are_we_gainfully_connected():
            # oops, server is dead. try once to restart it.
            new_nsql = connect(self.database_name)
            self.proxy = new_nsql.proxy

        if not params:
            params = tuple()

        return self.proxy.execute(query, params)

    def are_we_gainfully_connected(self):
        try:
            self.execute(DUMMY_QUERY, check=False)
        except ConnectionError:
            return False

        return True

    def __del__(self):
        # If we started the server, our process will hang until the server is killed. If someone
        # else is using it, they can start up their own server.
        if self.child_process:
            self.child_process.kill()


class NetSQLiteServer:
    def __init__(self, db_path):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.connection = sqlite3.connect(self.db_path)

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
        return res


def __server_startup__(port, database_name):
    log.info("Hello! The NetSQLite server-component is being launched.")
    nsql = NetSQLiteServer(database_name)
    log.info(f"Connected to sqlite database: '{database_name}'")
    with SimpleXMLRPCServer(("localhost", port), logRequests=False) as server:
        log.info(f"XMLRPCServer object is instantiated using port {port}")
        server.register_introspection_functions()
        server.register_instance(nsql)
        log.info("Calling .serve_forever()")
        server.serve_forever()


def __spawn_server_process__(db_name: str, port: int) -> subprocess.Popen:
    proc = subprocess.Popen(["python", __file__, SPAWN_COMMAND, db_name, str(port)])
    log.info(f"An sqlite server was spawned with PID {proc.pid}")
    return proc


def __poll(nsql: NetSQLiteConnection):
    wait = 0.1
    while wait < 10:
        if nsql.are_we_gainfully_connected():
            return

        log.info(f"Sleeping {wait} seconds to let server start up.")
        sleep(wait)
        wait = wait * 1.5

    raise RuntimeError(f"Giving up waiting for spawned server after {wait}+ seconds.")


def connect(db_name: str):
    nsql = None

    for port_offset in range(10):
        port = STARTPORT + port_offset
        nsql = NetSQLiteConnection(port, db_name)
        try:
            if not nsql.proxy.target_database() == db_name:
                log.warning(f"A server is already running on port {port}, "
                            "but serving another database.")
                continue
            elif nsql.are_we_gainfully_connected():
                break
        except ConnectionError:
            proc = __spawn_server_process__(db_name=db_name, port=port)
            nsql.child_process = proc
            __poll(nsql)
            break

    if not nsql:
        raise RuntimeError(f"Could not create connection to '{db_name}'")

    return nsql


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=f"[%(asctime)s] %(levelname)s [{os.getpid()}:%(name)s]: %(message)s"
    )

    if len(sys.argv) == 4 and sys.argv[1] == SPAWN_COMMAND:
        __server_startup__(database_name=sys.argv[2], port=int(sys.argv[3]))

    else:
        filnamn = os.path.basename(__file__)
        print(f"SYNTAX ERROR: {filnamn} {' '.join(sys.argv)}")
        print(f"Usage: {filnamn} {SPAWN_COMMAND} <database_file_path> <port-number>")
