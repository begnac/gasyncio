# coding: utf-8
#
# A minimalistic asyncio event loop based on the GLib main event loop
#
# Copyright (C) 2021 Itaï BEN YAACOV
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA


from gi.repository import GLib

import asyncio
import selectors
import sys


class GAsyncIOSelector(selectors._BaseSelectorImpl):
    def __init__(self):
        super().__init__()
        self._sources = {}
        self._ready = []

    @staticmethod
    def _events_to_io_condition(events):
        return (GLib.IOCondition.IN if events & selectors.EVENT_READ else GLib.IOCondition(0)) | \
            (GLib.IOCondition.OUT if events & selectors.EVENT_WRITE else GLib.IOCondition(0))

    @staticmethod
    def _io_condition_to_events(condition):
        return (selectors.EVENT_READ if condition & GLib.IOCondition.IN else 0) | \
            (selectors.EVENT_WRITE if condition & GLib.IOCondition.OUT else 0)

    def register(self, fileobj, events, data):
        key = super().register(fileobj, events, data)
        io_channel = GLib.IOChannel.unix_new(key.fd)
        io_channel.set_encoding(None)
        io_channel.set_buffered(False)
        source = GLib.io_add_watch(io_channel, GLib.PRIORITY_DEFAULT, self._events_to_io_condition(events), self._channel_watch_cb, key)
        if key.fd in self._sources:
            raise RuntimeError
        self._sources[key.fd] = source
        return key

    def unregister(self, fileobj):
        key = super().unregister(fileobj)
        source = self._sources.pop(key.fd)
        GLib.source_remove(source)
        return key

    def _channel_watch_cb(self, channel, condition, key):
        handle_in, handle_out = key.data
        if condition & GLib.IOCondition.IN:
            handle_in._run()
        if condition & GLib.IOCondition.OUT:
            handle_out._run()
        return True

    def select(self, timeout):
        return ()


class GAsyncIOEventLoop(asyncio.selector_events.BaseSelectorEventLoop):
    def __init__(self):
        super().__init__(GAsyncIOSelector())
        self._giteration = None
        GLib.idle_add(self._schedule_giteration)

    def start_slave_loop(self):
        self._check_closed()
        self._check_running()
        self._set_coroutine_origin_tracking(self._debug)

        self._old_agen_hooks = sys.get_asyncgen_hooks()
        sys.set_asyncgen_hooks(firstiter=self._asyncgen_firstiter_hook,
                               finalizer=self._asyncgen_finalizer_hook)
        asyncio.events._set_running_loop(self)

    def stop_slave_loop(self):
        asyncio.events._set_running_loop(None)
        self._set_coroutine_origin_tracking(False)
        sys.set_asyncgen_hooks(*self._old_agen_hooks)

    def run_application(self, app, argv):
        """
        Run a Gio.Application, enslaving the event loop to the GLib main loop.

        While the application is running, asyncio.get_event_loop() and
        asyncio.get_running_loop() will return self, but self.is_running()
        will return False.  This is since it is the GLib main loop that runs the
        show, the event loop does not actually run iteself.

        Once the application is done running, the event loop closes.
        """
        self.start_slave_loop()
        try:
            app.run(argv)
        finally:
            self.stop_slave_loop()
            self.close()

    def run_without_glib_until_complete(self, future):
        """
        Run loop without the GLib main loop.  This will block the GLib main
        loop, so only use this for a future that will complete immediately,
        or when the GLib main loop isn't running.
        """
        if asyncio._get_running_loop() is self:
            asyncio._set_running_loop(None)
            super().run_until_complete(future)
            asyncio._set_running_loop(self)

    def call_at(self, when, callback, *args, context=None):
        self._check_closed()
        if self._debug:
            self._check_thread()
            self._check_callback(callback, 'call_at')
        timer = asyncio.events.TimerHandle(when, callback, args, self, context)
        if timer._source_traceback:
            del timer._source_traceback[-1]
        timer._scheduled = GLib.timeout_add((when - self.time()) * 1000, self._timeout_cb, timer)
        return timer

    def _timer_handle_cancelled(self, timer):
        if timer._scheduled:
            GLib.source_remove(timer._scheduled)
        timer._scheduled = False

    def _timeout_cb(self, timer):
        timer._run()
        timer._scheduled = False
        return False

    def _call_soon(self, *args, **kwargs):
        handle = super()._call_soon(*args, **kwargs)
        self._schedule_giteration()
        return handle

    def _add_callback(self, *args, **kwargs):
        handle = super()._add_callback(*args, **kwargs)
        self._schedule_giteration()
        return handle

    def _schedule_giteration(self):
        if self._giteration is not None:
            return
        self._giteration = GLib.timeout_add(0, self._giterate)

    def _giterate(self):
        self._run_once()
        if self._ready:
            return True
        else:
            self._giteration = None
            return False


class GAsyncIOEventLoopPolicy(asyncio.events.BaseDefaultEventLoopPolicy):
    _loop_factory = GAsyncIOEventLoop
