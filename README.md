# gasyncio - A minimalistic asyncio event loop based on the GLib main event loop

When used as a context manager, `GAsyncIOEventLoop` sets itself to be run by the
`GLib` main event loop.
`GAsyncIOEventLoop.run_until_complete()` will execute in its own `GLib.MainLoop`,
and can be used for cleanup after the `GLib` main loop has stopped.

```
with GAsyncIOEventLoop() as loop:
  gio_app.run()
  loop.run_until_complete(cleanup())
```

`GAsyncIOApplicationMixin` wraps run() by the context manager, ensuring that the
slave loop is set up before that `startup` signal and closed after the `shutdown`.

```
class MyApp(GAsyncIOApplicationMixin, Gio.Application):
    ...


MyApp().run()
```
