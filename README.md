gasyncio
========

A minimalistic asyncio event loop based on the GLib main event loop

So far only a proof-of-concept.

Defines `GAsyncIOEventLoopPolicy` and `GAsyncIOEventLoop`.

Use `loop.run_application(app, argv)` to run `Gio.Application`.
While the application is running, the `asyncio` event loop will function normally,
run by the `GLib` main event loop.

Use `loop.run_without_glib_until_complete(future)` for cleanup.
