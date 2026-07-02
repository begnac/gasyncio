# gasyncio

## A minimalistic asyncio event loop based on the GLib main event loop

### `GAsyncIOEventLoop`

An `asyncio` event loop that sets itself to be run by the `GLib` main
event loop.

* Set up a `GAsyncIOEventLoop` event loop using an `asyncio.Runner`
context manager.
* Inside a `GLib` main loop, start asynchronous operations using
`asyncio.create_task(coroutine())`.
* Outside a `GLib` main loop,  `GAsyncIOEventLoop.run_until_complete()`
will start its own `GLib` main loop.
This is mostly useful for short synchronous operations that
require the async loop, such as cleanups.

```
with asyncio.Runner(loop_factory=GAsyncIOEventLoop):
	# Create async tasks in signal handlers.
	gio_app.run()

	# Start own GLib main loop.
	asyncio.get_event_loop().run_until_complete(cleanup())
```

### `GAsyncIOApplicationMixin`

Wraps `Gio.Application.run()` with an `asyncio.Runner` using
`GAsyncIOEventLoop` as `loop_factory`.
Tasks created by the application will be run by the `GLib` main loop.

```
class MyApp(GAsyncIOApplicationMixin, Gio.Application):
    ...

MyApp().run()
```
