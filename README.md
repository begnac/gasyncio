# gasyncio

## A minimalistic asyncio event loop based on the GLib main event loop

### `GAsyncIOEventLoop`

When used as a context manager, sets itself to be run by the `GLib` main
event loop.

* Within the scope of the context manager, start asynchronous
operations with `asyncio.create_task(coroutine())`.
* `GAsyncIOEventLoop.run_until_complete()` will execute in its
own `GLib.MainLoop`.
This is mostly useful for short synchronous operations that
require the async loop, such as cleanups.

```
with GAsyncIOEventLoop() as loop:
    gio_app.run()
    loop.run_until_complete(cleanup())
```

### `GAsyncIOApplicationMixin`

Wraps `Gio.Application.run()` with the `GAsyncIOEventLoop` context
manager, ensuring that the slave loop is set up before the `startup` 
signal and closed after the `shutdown`.

```
class MyApp(GAsyncIOApplicationMixin, Gio.Application):
    ...

MyApp().run()
```
