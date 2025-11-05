# NetSQLite Documentation

This directory contains technical documentation and design analysis for NetSQLite.

## Files

- **performance_analysis.md** - Summary of performance characteristics and overhead breakdown for both XML-RPC and multiprocessing implementations
- **platform_socket_analysis.md** - Cross-platform IPC considerations, including Unix domain sockets, Windows Named Pipes, and recommendations
- **multiprocessing_implementation_comparison.md** - Detailed comparison of implementation approaches between XML-RPC and multiprocessing.connection

## Quick Reference

### Performance Summary

| Implementation | Throughput | Latency | Overhead vs SQLite |
|---------------|------------|---------|-------------------|
| XML-RPC | ~650 qps | ~1.58 ms | ~1000x |
| multiprocessing | ~3700 qps | ~0.27 ms | ~300x |
| Direct SQLite | ~950k qps | ~0.001 ms | 1x |

### When to Use Which Implementation

**Use XML-RPC (netsqlite.py) when:**
- Simplicity is paramount
- 600-800 qps is sufficient
- You prefer automatic method dispatch

**Use multiprocessing (netsqlite_mp.py) when:**
- Performance is important
- You need 3000+ qps
- You want 6x better performance
- All processes are on the same machine (same as XML-RPC requirement)
