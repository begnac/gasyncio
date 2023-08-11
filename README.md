# gasyncio - A minimalistic asyncio event loop based on the GLib main event loop

Defines `GAsyncIOEventLoopPolicy` and `GAsyncIOEventLoop`.

- `gasyncio.start_slave_loop()` will set up the `asyncio` event loop to be
  run by the `GLib` main event loop.
- `gasyncio.stop_slave_loop()` will undo this.
- If you want to be sure a quick future is done before the slave loop is
  stopped (e.g., for cleanup), or if the slave loop is not running, use
  `loop.run_without_glib_until_complete(future)`.

The following should be semantically equivalent:

```
asyncio.set_event_loop_policy(gasyncio.GAsyncIOEventLoopPolicy())
loop = asyncio.get_event_loop()
loop.start_slave_loop()
.
.
.
loop.stop_slave_loop()
loop.close()
asyncio.set_event_loop_policy()
del loop
```

```
gasyncio.start_slave_loop()
.
.
.
gasyncio.start_slave_loop()
```
