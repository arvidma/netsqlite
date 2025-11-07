# Säkerhetsanalys av NetSQLite

## Sammanfattning

NetSQLite är ett verktyg för att dela SQLite-databaser mellan processer genom att starta en server-process som lyssnar på en localhost-port. Grundpremissen är att **alla deltagande processer redan har läs- och skrivrättigheter till SQLite-filen på filsystemet**. Denna analys fokuserar på säkerhetsproblem som nätverkslagret introducerar utöver den befintliga filsystemsåtkomsten.

## Status: Implementerade Säkerhetsförbättringar

### ✅ 1. Token-baserad Autentisering (IMPLEMENTERAD)
**Implementation:** Enkel token-baserad autentisering med "allt eller inget"-princip.

**Hur det fungerar:**
- Optional `auth_token` parameter i `connect()`
- Första meddelandet efter anslutning måste vara `('auth', token)`
- Server använder `hmac.compare_digest()` för timing-säker jämförelse
- Fel token → omedelbar avvisning av anslutning

**Kod:**
```python
# Användning
conn = netsqlite.connect("mydb.db", auth_token="secret_token_123")
```

**Resultat:** Förhindrar att oauktoriserade processer på samma maskin ansluter till servern.

**Bakåtkompatibilitet:** Fullt bakåtkompatibelt - utan `auth_token` fungerar systemet som tidigare.

### ✅ 2. JSON-serialisering istället för Pickle (IMPLEMENTERAD)
**Implementation:** Ersatt pickle med JSON för att eliminera RCE-sårbarhet.

**Hur det fungerar:**
- Använder `json.dumps(obj, default=str)` för serialisering
- `send_bytes()` och `recv_bytes()` istället för `send()` och `recv()`
- Special-hantering för Exception-objekt
- `default=str` hanterar datetime och andra icke-JSON-typer

**Kod:**
```python
def _serialize(obj):
    """Serialize object to JSON bytes, avoiding pickle vulnerability."""
    if isinstance(obj, Exception):
        return json.dumps({
            '_exception': True,
            'type': type(obj).__name__,
            'args': obj.args
        }, default=str).encode('utf-8')
    return json.dumps(obj, default=str).encode('utf-8')
```

**Resultat:** Eliminerar möjligheten till Remote Code Execution via pickle deserialization.

---

## Återstående Säkerhetsområden

### 3. SQL Injection Prevention (MEDEL-LÅG)
**Nuläge:** Parametriserade queries stöds men är inte obligatoriska.

**Risk:** Utvecklare kan av misstag bygga queries med strängkonkatenering.

**Rekommendation:** Dokumentation och best practices snarare än tekniska begränsningar. SQLite används redan direkt via filsystemet utan extra skydd.

**Bedömning:** Inte högre risk än normal SQLite-användning. Utvecklare har samma ansvar som vid direkt SQLite-access.

---

### 4. Ingen Kryptering av Data i Transit (LÅG)
**Nuläge:** Data skickas okrypterat över localhost.

**Risk:**
- På delade system kan root-användare sniffa localhost-trafik
- Container-escape scenarios

**Rekommendation:** Låg prioritet eftersom:
- Endast localhost-kommunikation
- Root-användare kan ändå läsa SQLite-filen direkt
- Autentisering förhindrar oauktoriserad access

**Möjlig förbättring:** TLS via `ssl.wrap_socket()` för extra skydd, men komplext att implementera korrekt för multiprocessing.connection.

---

### 5. Rate Limiting / DoS Skydd (MEDEL)
**Nuläge:** Ingen begränsning av antalet requests eller anslutningar.

**Risk:**
- Skadlig process på samma maskin kan överbelasta servern
- Långa queries kan blockera andra klienter
- Minnesexhaustion genom stora resultatset

**Möjlig förbättring:**
```python
class NetSQLiteServer:
    def __init__(self, db_path: str, port: int, auth_token: Optional[str] = None,
                 max_concurrent_clients: int = 10):
        self.max_concurrent_clients = max_concurrent_clients
        self.active_clients = 0

    def serve_forever(self):
        while self.running:
            conn = self.listener.accept()
            if self.active_clients >= self.max_concurrent_clients:
                conn.close()
                continue
            self.active_clients += 1
            # ... starta client thread
```

**Bedömning:** Medelprioritering - kan vara värdefullt i multi-tenant scenarios.

---

### 6. Audit Logging (MEDEL)
**Nuläge:** Grundläggande logging finns, men ingen strukturerad audit trail.

**Risk:**
- Svårt att spåra säkerhetsincidenter
- Ingen accountability för databas-operationer
- Compliance-problem (GDPR, etc.)

**Möjlig förbättring:**
```python
class NetSQLiteServer:
    def __init__(self, db_path: str, port: int, auth_token: Optional[str] = None,
                 audit_log: Optional[str] = None):
        self.audit_log = audit_log

    def execute(self, query: str, params: Optional[Sequence[Any]] = None):
        result = self.connection.execute(query, params).fetchall()

        if self.audit_log:
            with open(self.audit_log, 'a') as f:
                f.write(json.dumps({
                    'timestamp': time.time(),
                    'query': query,
                    'param_count': len(params) if params else 0,
                    'result_count': len(result)
                }) + '\n')

        return [list(row) for row in res]
```

**Bedömning:** Värdefullt för produktionsmiljöer, men kan implementeras vid behov.

---

### 7. Port Scanning / Information Disclosure (LÅG)
**Nuläge:** Servern scannar sekventiellt portar 25432-25441.

**Risk:**
- Enkelt att enumerate aktiva NetSQLite-servrar
- Database paths exponeras via `target_database()` metoden

**Bedömning:** Låg risk eftersom:
- Endast localhost-access
- Autentisering förhindrar oauktoriserad anslutning
- Processer med filsystemsåtkomst kan ändå se databasfiler

**Möjlig förbättring:** Registry-baserad server discovery istället för port-scanning, men låg prioritet.

---

### 8. Input Validation (LÅG-MEDEL)
**Nuläge:** Database paths valideras inte särskilt.

**Risk:**
- Path traversal möjlig
- Kan peka på systemfiler (t.ex. `/etc/passwd`)

**Möjlig förbättring:**
```python
def validate_database_path(db_path: str):
    if db_path == ":memory:":
        return db_path

    abs_path = os.path.abspath(db_path)

    # Kontrollera filextension
    if not abs_path.endswith(('.db', '.sqlite', '.sqlite3')):
        raise ValueError("Database must have .db or .sqlite extension")

    # Förhindra access till systemkataloger
    forbidden_dirs = ['/etc', '/sys', '/proc', '/dev']
    if any(abs_path.startswith(d) for d in forbidden_dirs):
        raise ValueError("Access to system directories not allowed")

    return abs_path
```

**Bedömning:** Värt att implementera som extra försvar, men inte kritiskt.

---

### 9. Error Information Disclosure (LÅG)
**Nuläge:** Detaljerade SQLite-felmeddelanden skickas till klienter.

**Risk:**
- Kan läcka information om databasstruktur
- Hjälper vid kartläggning av systemet

**Bedömning:** Mycket låg risk eftersom:
- Endast autentiserade klienter får felmeddelanden
- Dessa klienter har redan fullständig databas-access
- Informationen är nödvändig för debugging

**Rekommendation:** Behåll detaljerade felmeddelanden för användarbarhet.

---

### 10. Process Management (LÅG)
**Nuläge:** Child processes spawnas utan särskilda resource limits.

**Risk:**
- Ingen CPU/minnes-begränsning
- Processer kan läcka fil-descriptors

**Möjlig förbättring:**
```python
def __spawn_server_process__(db_name: str, port: int, auth_token: Optional[str] = None):
    proc = subprocess.Popen(
        cmd,
        close_fds=True,  # Stäng ärvda file descriptors
        start_new_session=True,  # Ny process group
    )
    return proc
```

**Bedömning:** Låg prioritet - kan läggas till vid behov.

---

## Felaktiga eller Ej Tillämpliga Problem

### ❌ "Ingen Auktorisering/Åtkomstkontroll" - EJ ETT PROBLEM
**Varför:** Grundpremissen är att **alla processer redan har full läs- och skriv-access till SQLite-filen**. Att lägga till granulär åtkomstkontroll i nätverkslagret skulle vara meningslöst eftersom:
- Processer kan läsa/skriva filen direkt via filsystemet
- Alla legitima användare är lika betrodda
- "Allt eller inget"-modellen (autentisering) är korrekt design

**Slutsats:** Detta är inte en sårbarhet - det är designen.

---

### ❌ "Race Conditions på Port Binding" - EJ ETT RIKTIGT PROBLEM
**Tidigare analys:** "Flera processer kan försöka starta server samtidigt på samma port."

**Korrektion:** **Detta kan inte hända.** Operativsystemet garanterar att endast en process kan binda till en port:

```python
# Process A
server_A = Listener(('localhost', 25432))  # ✅ OK

# Process B (samtidigt)
server_B = Listener(('localhost', 25432))  # ❌ OSError: Address already in use
```

**Vad som faktiskt händer:**
1. Process A och B försöker ansluta samtidigt → båda får `ConnectionRefusedError`
2. Båda spawnar en server-process
3. Process A:s server binder till porten ✅
4. Process B:s server kraschar med "Address already in use" ❌
5. Process B:s `__poll()` fortsätter vänta och ansluter till A:s server ✅

**Resultat:** Ingen datakorruption, endast potentiellt en onödig process som spawnas och dör. Befintlig retry-logik hanterar detta.

---

## Sammanfattning och Rekommendationer

### Implementerat (Fas 1 - Kritiska Åtgärder) ✅
1. ✅ **Token-baserad autentisering** - Förhindrar oauktoriserad access
2. ✅ **JSON-serialisering** - Eliminerar pickle RCE-sårbarhet

### Rekommenderas för Produktion (Fas 2)
3. **Rate limiting** - Skydd mot DoS från lokala processer
4. **Audit logging** - Spårbarhet och compliance
5. **Input validation** - Extra försvarslager för database paths

### Låg Prioritet (Fas 3)
6. Process resource limits
7. Registry-baserad server discovery
8. TLS för localhost-kommunikation (mycket låg prioritet)

### Designprinciper

NetSQLite följer nu dessa säkerhetsprinciper:

1. **Secure by Default**: Autentisering är enkelt att aktivera
2. **Defense in Depth**: JSON + autentisering ger flera skyddslager
3. **Principle of Least Surprise**: Full access är förväntat (samma som filsystem)
4. **Keep It Simple**: Minimal komplexitet = färre sårbarheter

### Säker Användning

```python
import os
import netsqlite

# Rekommenderad konfiguration för produktionsmiljö
SECRET_TOKEN = os.environ.get('NETSQLITE_AUTH_TOKEN')
if not SECRET_TOKEN:
    raise ValueError("NETSQLITE_AUTH_TOKEN must be set")

conn = netsqlite.connect(
    db_name='/var/app/data/myapp.db',
    auth_token=SECRET_TOKEN
)

# Använd alltid parametriserade queries
conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

### Slutsats

NetSQLite har nu åtgärdat de två **kritiska** säkerhetsproblemen:
1. ✅ Ingen autentisering (nu implementerad)
2. ✅ Pickle RCE-sårbarhet (nu åtgärdad med JSON)

Återstående problem är av lägre prioritet och många är acceptabla givet grundpremissen att processer redan har filsystemsåtkomst. Systemet är nu lämpligt för produktionsanvändning med autentisering aktiverad.

**Rekommendation för produktion:**
- **Obligatoriskt:** Använd `auth_token` för alla databaser
- **Rekommenderat:** Implementera audit logging för compliance
- **Valfritt:** Rate limiting för multi-tenant scenarios
