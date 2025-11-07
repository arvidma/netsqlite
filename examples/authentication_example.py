"""
Example showing how to use authentication in NetSQLite.

Authentication is optional and backward compatible. If no auth_token is provided,
the system works as before. If an auth_token is provided, only clients with the
same token can connect.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from netsqlite import netsqlite

# Example 1: Without authentication (backward compatible)
print("Example 1: Without authentication")
conn1 = netsqlite.connect(":memory:")
conn1.execute("CREATE TABLE users(id int, name text);")
conn1.execute("INSERT INTO users VALUES(1, 'Alice');")
result = conn1.execute("SELECT * FROM users")
print(f"Result: {result}")
if conn1.child_process:
    conn1.child_process.kill()
    conn1.child_process.wait()

print("\n" + "="*60 + "\n")

# Example 2: With authentication
print("Example 2: With authentication")
SECRET_TOKEN = "my_secret_database_token_123"

# First client connects with token
conn2 = netsqlite.connect(":memory:", auth_token=SECRET_TOKEN)
conn2.execute("CREATE TABLE products(id int, name text);")
conn2.execute("INSERT INTO products VALUES(1, 'Widget');")

# Second client can connect with same token
conn3 = netsqlite.connect(":memory:", auth_token=SECRET_TOKEN)
result = conn3.execute("SELECT * FROM products")
print(f"Second client can read: {result}")

# Both clients can write
conn3.execute("INSERT INTO products VALUES(2, 'Gadget');")
result = conn2.execute("SELECT * FROM products ORDER BY id")
print(f"First client sees both: {result}")

if conn2.child_process:
    conn2.child_process.kill()
    conn2.child_process.wait()

print("\n" + "="*60 + "\n")

# Example 3: Wrong token is rejected
print("Example 3: Authentication failure")
CORRECT_TOKEN = "correct_token"
WRONG_TOKEN = "wrong_token"

conn4 = netsqlite.connect(":memory:", auth_token=CORRECT_TOKEN)
conn4.execute("CREATE TABLE secret_data(value text);")
print("Server started with correct token")

try:
    # This will fail
    conn5 = netsqlite.connect(":memory:", auth_token=WRONG_TOKEN)
    print("ERROR: Should not reach here!")
except Exception as e:
    print(f"Connection rejected as expected: {e}")

if conn4.child_process:
    conn4.child_process.kill()
    conn4.child_process.wait()

print("\nAll examples completed!")
