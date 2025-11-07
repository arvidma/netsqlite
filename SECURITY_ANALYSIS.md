# Säkerhetsanalys av NetSQLite

## Sammanfattning

NetSQLite är ett verktyg för att dela SQLite-databaser mellan processer genom att starta en server-process som lyssnar på en localhost-port. Trots att grundpremissen är att alla processer redan har filsystemsåtkomst till databasen, introducerar nätverkslagret flera säkerhetsproblem som en systemarkitekt eller IT-säkerhetsansvarig skulle invända mot.

## Kritiska Säkerhetsproblem

### 1. Ingen Autentisering (KRITISK)
**Problem:** Ingen som helst autentisering krävs för att ansluta till servern.

**Konsekvenser:**
- Vilken process som helst på localhost kan ansluta till vilken NetSQLite-server som helst
- Om flera användare delar samma system kan de komma åt varandras databaser
- Skadliga processer kan enkelt hitta och ansluta till aktiva servrar

**Kod:** `netsqlite.py:103-139` - `handle_client()` accepterar alla anslutningar utan verifiering

**Förbättringsförslag:**
```python
# Lägg till token-baserad autentisering
class NetSQLiteServer:
    def __init__(self, db_path: str, port: int, auth_token: Optional[str] = None):
        self.auth_token = auth_token or secrets.token_urlsafe(32)
        # ...

    def handle_client(self, conn):
        # Första meddelandet måste vara autentisering
        auth_msg = conn.recv()
        if not isinstance(auth_msg, tuple) or auth_msg[0] != 'auth':
            conn.close()
            return
        if len(auth_msg) < 2 or auth_msg[1] != self.auth_token:
            conn.send(Exception("Authentication failed"))
            conn.close()
            return
        # ...fortsätt med normal hantering
```

### 2. Pickle Deserialization Vulnerability (KRITISK)
**Problem:** `multiprocessing.connection` använder pickle som standard för serialisering, vilket är extremt farligt.

**Konsekvenser:**
- Attackerare kan skicka specialhanterade pickle-objekt som exekverar godtycklig kod
- Detta är en RCE (Remote Code Execution) sårbarhet
- Även om den endast lyssnar på localhost, kan andra processer på systemet exploatera detta

**Kod:** `netsqlite.py:18` - Import av `multiprocessing.connection` som använder pickle

**Förbättringsförslag:**
```python
# Använd JSON istället för pickle
import json

class NetSQLiteConnection:
    def _send_receive(self, message):
        with self._lock:
            try:
                # Serialisera till JSON istället för pickle
                json_msg = json.dumps(message)
                self.conn.send(json_msg.encode())
                response = self.conn.recv().decode()
                response = json.loads(response)
                # ...
```

### 3. Ingen Auktorisering/Åtkomstkontroll (KRITISK)
**Problem:** Alla anslutna klienter har fullständig åtkomst till hela databasen.

**Konsekvenser:**
- Ingen möjlighet att begränsa vad olika processer kan göra
- Alla kan utföra DROP TABLE, DELETE, eller andra destruktiva operationer
- Ingen read-only åtkomst möjlig

**Förbättringsförslag:**
```python
class NetSQLiteConnection:
    def __init__(self, conn, database_name: str, port: int, permissions: Set[str] = None):
        self.permissions = permissions or {'SELECT', 'INSERT', 'UPDATE', 'DELETE'}

    def execute(self, query: str, params = None, check=True):
        # Validera att queryn börjar med tillåten operation
        query_upper = query.strip().upper()
        operation = query_upper.split()[0]

        if operation not in self.permissions:
            raise PermissionError(f"Operation {operation} not allowed")

        # ...fortsätt med normal execution
```

### 4. SQL Injection Potential (HÖG)
**Problem:** Även om parametriserade queries stöds, finns ingen tvingande validering eller check.

**Konsekvenser:**
- Utvecklare kan råka bygga queries med strängkonkatenering
- Ingen statisk analys eller varningar
- Parametrar valideras inte alls

**Kod:** `netsqlite.py:53-62` - `execute()` tar emot råa SQL-strängar

**Förbättringsförslag:**
```python
import re

DANGEROUS_PATTERNS = [
    r';.*(?:DROP|DELETE|UPDATE|INSERT)',  # Multipla statements
    r'--',  # SQL-kommentarer
    r'/\*.*\*/',  # Block-kommentarer
]

def validate_query(query: str):
    """Validera query för misstänkta mönster."""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            raise ValueError(f"Query contains potentially dangerous pattern: {pattern}")

    # Kräv att params används om värden ska inkluderas
    if any(c in query for c in ["'", '"']) and '?' not in query:
        raise ValueError("String literals in query without parameters - potential SQL injection")
```

### 5. Ingen Kryptering av Data i Transit (MEDEL)
**Problem:** All data skickas okrypterad över localhost.

**Konsekvenser:**
- På delade system kan andra användare med root-rättigheter sniffa trafik
- Container-escape eller VM-escape scenarios exponerar data
- Debug-verktyg kan läsa minne och nätverksbuffertar

**Förbättringsförslag:**
```python
import hmac
import hashlib

class NetSQLiteConnection:
    def __init__(self, conn, database_name: str, port: int, shared_secret: bytes = None):
        self.shared_secret = shared_secret or os.urandom(32)

    def _send_receive(self, message):
        with self._lock:
            # Lägg till HMAC för integritet
            msg_bytes = pickle.dumps(message)
            mac = hmac.new(self.shared_secret, msg_bytes, hashlib.sha256).digest()
            self.conn.send((msg_bytes, mac))

            response, response_mac = self.conn.recv()
            expected_mac = hmac.new(self.shared_secret, response, hashlib.sha256).digest()
            if not hmac.compare_digest(response_mac, expected_mac):
                raise SecurityError("Response MAC verification failed")
            # ...
```

### 6. Ingen Rate Limiting / DoS Skydd (HÖG)
**Problem:** Ingen begränsning av antalet requests eller anslutningar.

**Konsekvenser:**
- Skadlig process kan överbelasta servern
- Långa queries kan blockera andra
- Minnesexhaustion möjlig genom stora resultatset

**Kod:** `netsqlite.py:141-158` - `serve_forever()` accepterar obegränsat med klienter

**Förbättringsförslag:**
```python
from collections import defaultdict
from time import time

class NetSQLiteServer:
    def __init__(self, db_path: str, port: int):
        # ...
        self.rate_limits = defaultdict(list)  # IP -> timestamps
        self.max_requests_per_minute = 1000
        self.max_concurrent_clients = 10
        self.active_clients = 0

    def check_rate_limit(self, client_addr):
        now = time()
        # Ta bort gamla timestamps
        self.rate_limits[client_addr] = [
            ts for ts in self.rate_limits[client_addr]
            if now - ts < 60
        ]

        if len(self.rate_limits[client_addr]) >= self.max_requests_per_minute:
            return False

        self.rate_limits[client_addr].append(now)
        return True

    def serve_forever(self):
        while self.running:
            conn = self.listener.accept()

            if self.active_clients >= self.max_concurrent_clients:
                conn.close()
                log.warning("Max concurrent clients reached")
                continue

            self.active_clients += 1
            # ...
```

### 7. Ingen Audit Logging (HÖG)
**Problem:** Inga loggar över vem som gjort vad.

**Konsekvenser:**
- Omöjligt att spåra säkerhetsincidenter
- Ingen accountability
- Svårt att debugga problem
- Compliance-problem (GDPR, etc.)

**Förbättringsförslag:**
```python
import logging
import json
from datetime import datetime

class AuditLogger:
    def __init__(self, audit_log_path: str):
        self.audit_log_path = audit_log_path

    def log_query(self, client_info: dict, query: str, params: tuple, result_count: int):
        audit_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'client_pid': client_info.get('pid'),
            'client_user': client_info.get('user'),
            'query': query,
            'param_count': len(params) if params else 0,
            'result_count': result_count,
        }

        with open(self.audit_log_path, 'a') as f:
            f.write(json.dumps(audit_entry) + '\n')

class NetSQLiteServer:
    def __init__(self, db_path: str, port: int, audit_log: str = None):
        # ...
        self.audit_logger = AuditLogger(audit_log) if audit_log else None

    def execute(self, query: str, params = None, client_info = None):
        # ...
        res = self.connection.execute(query, params).fetchall()

        if self.audit_logger:
            self.audit_logger.log_query(client_info, query, params, len(res))

        return res
```

### 8. Port Scanning / Information Disclosure (MEDEL)
**Problem:** Servern provar sekventiellt portar och exponerar vilka databaser som körs.

**Konsekvenser:**
- Lätt att enumerate alla aktiva NetSQLite-servrar
- Database paths exponeras via `target_database()` metoden
- Attackerare kan kartlägga systemet

**Kod:** `netsqlite.py:202-232` - `connect()` scannar portar 25432-25441

**Förbättringsförslag:**
```python
import secrets
import tempfile
import os

def get_server_registry_path():
    """Använd en fil för att registrera servrar istället för port-scanning."""
    return os.path.join(tempfile.gettempdir(), '.netsqlite_registry.json')

def connect(db_name: str):
    # Läs registry-fil för att hitta vilken port som används för denna databas
    registry_path = get_server_registry_path()

    if os.path.exists(registry_path):
        with open(registry_path, 'r') as f:
            registry = json.load(f)

        if db_name in registry:
            port = registry[db_name]['port']
            try:
                conn = Client(('localhost', port))
                # ...
            except:
                # Ta bort från registry om servern är död
                del registry[db_name]
                with open(registry_path, 'w') as f:
                    json.dump(registry, f)

    # Om inte i registry, starta ny server på slumpmässig port
    port = secrets.randbelow(10000) + 25432
    # ...
```

### 9. Ingen Input Validation (MEDEL)
**Problem:** Database paths och andra inputs valideras inte.

**Konsekvenser:**
- Path traversal möjlig
- Symlink attacks
- Kan peka på känsliga systemfiler

**Förbättringsförslag:**
```python
import os
from pathlib import Path

def validate_database_path(db_path: str, allowed_directories: List[str] = None):
    """Validera att database path är säker."""

    # Specialfall för in-memory databaser
    if db_path == ":memory:":
        return db_path

    # Resolve till absolut path
    abs_path = os.path.abspath(db_path)

    # Kontrollera att det är en fil (inte directory, device, etc.)
    if os.path.exists(abs_path) and not os.path.isfile(abs_path):
        raise ValueError(f"Database path must be a file: {abs_path}")

    # Kontrollera att det slutar med .db eller .sqlite
    if not abs_path.endswith(('.db', '.sqlite', '.sqlite3')):
        raise ValueError("Database must have .db or .sqlite extension")

    # Om allowed_directories är angivet, kontrollera att path är inom dessa
    if allowed_directories:
        if not any(abs_path.startswith(d) for d in allowed_directories):
            raise ValueError(f"Database path not in allowed directories: {abs_path}")

    return abs_path

def connect(db_name: str, allowed_directories: List[str] = None):
    db_name = validate_database_path(db_name, allowed_directories)
    # ...
```

### 10. Race Conditions (MEDEL)
**Problem:** Flera processer kan försöka starta server samtidigt på samma port.

**Konsekvenser:**
- Två servrar kan starta för samma databas
- Port conflicts
- Datakorruption möjlig

**Förbättringsförslag:**
```python
import fcntl

def connect(db_name: str):
    # Använd fil-locking för att garantera endast en server per databas
    lock_file = f"/tmp/netsqlite_{hashlib.md5(db_name.encode()).hexdigest()}.lock"

    lock_fd = open(lock_file, 'w')
    try:
        # Försök få exclusive lock (non-blocking)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        # Om vi fick lock, kolla om server redan kör
        # ...

        # Om inte, starta server
        proc = __spawn_server_process__(db_name, port)

        # Håll lock-filen öppen så länge servern kör
        # ...

    except BlockingIOError:
        # Någon annan har redan startat server, vänta lite och anslut
        sleep(0.1)
        # ...
```

### 11. Error Information Disclosure (LÅG)
**Problem:** Detaljerade felmeddelanden skickas tillbaka till klienter.

**Konsekvenser:**
- Kan läcka information om databasstruktur
- Stack traces kan exponera filpaths
- Hjälper attackerare att kartlägga systemet

**Kod:** `netsqlite.py:132-134` - Exceptions skickas direkt till klient

**Förbättringsförslag:**
```python
class NetSQLiteServer:
    def handle_client(self, conn):
        try:
            while True:
                message = conn.recv()
                # ...
                try:
                    # ... hantera query
                    conn.send(result)
                except Exception as e:
                    # Logga fullständigt fel på servern
                    log.error(f"Error handling {method_name}: {e}", exc_info=True)

                    # Skicka generiskt felmeddelande till klient
                    error_msg = "Database operation failed"
                    if isinstance(e, sqlite3.IntegrityError):
                        error_msg = "Integrity constraint violation"
                    elif isinstance(e, sqlite3.OperationalError):
                        error_msg = "Database operation error"

                    conn.send(Exception(error_msg))
```

### 12. Process Management Säkerhet (MEDEL)
**Problem:** Child processes spawnas utan särskild säkerhet.

**Konsekvenser:**
- Processer ärvs av init om parent dör
- Ingen resource limiting
- Kan läcka fil-descriptors

**Förbättringsförslag:**
```python
import resource

def __spawn_server_process__(db_name: str, port: int) -> subprocess.Popen:
    def limit_resources():
        # Sätt resource limits för child-processen
        resource.setrlimit(resource.RLIMIT_CPU, (300, 300))  # Max 5 min CPU
        resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))  # Max 512MB minne
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))  # Max 256 file descriptors

    proc = subprocess.Popen(
        [sys.executable, __file__, SPAWN_COMMAND, db_name, str(port)],
        preexec_fn=limit_resources,
        close_fds=True,  # Stäng alla ärvda file descriptors
        start_new_session=True,  # Ny process group
    )
    return proc
```

## Sammanfattning av Förbättringar

### Implementeringsprioritet

**Fas 1 - Kritiska åtgärder (måste implementeras):**
1. Byt från pickle till JSON/msgpack för säker serialisering
2. Implementera token-baserad autentisering
3. Lägg till input validation för database paths
4. Implementera audit logging

**Fas 2 - Högt prioriterade (bör implementeras):**
5. Lägg till rate limiting och DoS-skydd
6. Implementera åtkomstkontroll/permissions
7. Fixa race conditions med fil-locking
8. Förbättra error handling

**Fas 3 - Medelprioriterade (rekommenderas):**
9. Lägg till HMAC för message integrity
10. Implementera registry-baserad server discovery
11. Förbättra process management
12. Säkra port allocation

### Designprinciper för Säker Implementation

1. **Defense in Depth**: Flera lager av säkerhet
2. **Principle of Least Privilege**: Minimal default permissions
3. **Secure by Default**: Säkerhet aktiverad som standard
4. **Fail Secure**: Vid fel, stäng ner säkert
5. **Audit Everything**: Logga alla säkerhetsrelevanta events

### Exempel på Säker Configuration

```python
# Säker användning av NetSQLite
import netsqlite

# Skapa connection med säkerhetsparametrar
conn = netsqlite.connect(
    db_name='/var/app/data/myapp.db',
    auth_token=os.environ['NETSQLITE_TOKEN'],  # Från miljövariabel
    permissions={'SELECT', 'INSERT', 'UPDATE'},  # Ingen DROP eller DELETE
    allowed_directories=['/var/app/data'],  # Begränsa till app-directory
    audit_log='/var/log/netsqlite_audit.log',  # Audit logging
    rate_limit=1000,  # Max 1000 queries/minut
    use_encryption=True,  # Kryptera data i transit
)
```

## Slutsatser

Trots att grundpremissen är att alla processer redan har filsystemsåtkomst, introducerar NetSQLite flera nya attack vectors genom nätverkslagret:

1. **Pickle deserialization är den största risken** - möjliggör RCE
2. **Ingen autentisering** gör det lätt för andra processer att hitta och missbruka servrar
3. **Ingen auktorisering** innebär att en process med läs-access plötsligt kan få skriv-access
4. **Brist på logging** gör det omöjligt att upptäcka eller utreda säkerhetsincidenter

Dessa problem är **inte teoretiska** - de kan enkelt exploateras av:
- Andra användare på delade system
- Komprometterade processer på samma maskin
- Malware eller skadlig kod
- Utvecklingsmisstag som exponerar databaser

**Rekommendation**: Implementera åtminstone Fas 1 kritiska åtgärder innan produktionsanvändning.
