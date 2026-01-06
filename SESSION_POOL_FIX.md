# Session Pool Bug Fix

## Issue
The session pool was causing a `RuntimeError: Attempted to exit cancel scope in a different task than it was entered in` error.

## Root Cause
The `stdio_client` context manager was being entered but not properly stored, causing it to be garbage collected and exited in a different async task.

## Fix
Updated `session_pool.py`:

1. **Store the context manager** in `_create_session()`:
   ```python
   # Before
   read, write = await stdio_client(server_params).__aenter__()
   
   # After
   stdio_context = stdio_client(server_params)
   read, write = await stdio_context.__aenter__()
   # Store it in session info
   'stdio_context': stdio_context
   ```

2. **Properly exit context** in `_cleanup_session()`:
   ```python
   stdio_context = session_info.get('stdio_context')
   if stdio_context:
       await stdio_context.__aexit__(None, None, None)
   ```

## Testing
Restart the server and test - the error should be resolved.

```bash
# Stop current server (Ctrl+C)
# Restart
python server.py
```
