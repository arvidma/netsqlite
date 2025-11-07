# NetSQLite Test Suite

## Running Tests

```bash
python test/test_functional.py    # Basic functionality tests
python test/test_performance.py   # Performance benchmarks
python test/test_integration.py   # Multi-process integration tests
```

## Note on ResourceWarnings

The integration tests may show ResourceWarnings about subprocesses still running. 
This is expected behavior in multi-process tests where:
- Multiple worker processes spawn/connect to servers simultaneously
- Workers that connect to existing servers don't own the server process
- Complex process lifecycle makes perfect cleanup challenging

These warnings don't indicate test failures - all tests verify proper functionality
and data integrity. The warnings are a side effect of Python's subprocess cleanup
in multi-process scenarios.
