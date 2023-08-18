# gasyncio - A minimalistic asyncio event loop based on the GLib main event loop

Defines `GAsyncIOEventLoopPolicy` and `GAsyncIOEventLoop`.

- `gasyncio.start_slave_loop()` will set up the `asyncio` event loop to be
  run by the `GLib` main event loop.
  While the `GLib` main event loop is running, e.g., inside a running
  `Gio.Application`, code based on `asyncio` will run normally.
- `gasyncio.stop_slave_loop()` will undo this.
- `run_until_complete` will execute in its own `GLib.MainLoop`.

The following should be semantically equivalent:

```
asyncio.set_event_loop_policy(gasyncio.GAsyncIOEventLoopPolicy())
loop = asyncio.get_event_loop()
loop.start_slave_loop()
loop.run_until_complete(asyncio.sleep(1))
loop.stop_slave_loop()
loop.close()
asyncio.set_event_loop_policy(None)
del loop
```

```
gasyncio.start_slave_loop()
asyncio.get_event_loop().run_until_complete(asyncio.sleep(1))
gasyncio.stop_slave_loop()
```
