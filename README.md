# gasyncio - A minimalistic asyncio event loop based on the GLib main event loop

So far only a proof-of-concept.

Defines `GAsyncIOEventLoopPolicy` and `GAsyncIOEventLoop`.

Use `loop.run_application(app, argv)` to run `Gio.Application`.
While the application is running, the `asyncio` event loop will function normally,
run by the `GLib` main event loop.

Use `loop.run_without_glib_until_complete(future)` for cleanup.

The following should be semantically equivalent:

```
asyncio.set_event_loop_policy(gasyncio.GAsyncIOEventLoopPolicy())
loop = asyncio.get_event_loop().GAsyncIOEventLoop()
loop.start_slave_loop()
App().run(sys.argv)
loop.stop_slave_loop()
loop.close()
del loop
```

```
loop = gasyncio.GAsyncIOEventLoop()
loop.start_slave_loop()
App().run(sys.argv)
loop.stop_slave_loop()
loop.close()
del loop
```

```
gasyncio.GAsyncIOEventLoop().run(App(), sys.argv)
```
