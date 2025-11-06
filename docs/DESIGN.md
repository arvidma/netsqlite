# Design Notes

## Implementation History

### Original Implementation (XML-RPC)
- **Protocol:** HTTP + XML-RPC over TCP/IP
- **Performance:** ~650 qps, ~1.58 ms/query
- **Overhead:** ~1000x vs direct SQLite

### Current Implementation (multiprocessing.connection)
- **Protocol:** pickle over sockets
- **Performance:** ~3700 qps, ~0.27 ms/query
- **Overhead:** ~300x vs direct SQLite
- **Improvement:** 6x faster than XML-RPC

## Alternatives Considered

### 1. Unix Domain Sockets (platform-specific)
- **Pros:** Lowest latency (~50% faster than TCP)
- **Cons:** Platform-specific (Linux/macOS vs Windows Named Pipes)
- **Estimated:** 2-3x faster than current
- **Decision:** Rejected - complexity not worth marginal gain

### 2. Keep XML-RPC (original)
- **Pros:** Simplest code, automatic method dispatch
- **Cons:** 6x slower than multiprocessing
- **Decision:** Rejected - performance matters

### 3. multiprocessing.connection (chosen)
- **Pros:** 6x faster, cross-platform, standard library only
- **Cons:** Requires manual method dispatch (+40 lines)
- **Decision:** Accepted - best performance/complexity trade-off

## Overhead Breakdown

### XML-RPC (old):
- Network/socket: 49% (0.86 ms)
- HTTP/server: 49% (0.86 ms)
- XML serialization: 3% (0.05 ms)

### multiprocessing (current):
- IPC communication: 29% (0.08 ms) - 20x faster than HTTP+XML!
- Application logic: 71% (0.21 ms)
- Pickle serialization: <1% (0.002 ms)

## Key Finding

The bottleneck was never XML serialization - it was the HTTP/TCP stack overhead. multiprocessing.connection eliminates this by using simpler, more efficient socket handling.
