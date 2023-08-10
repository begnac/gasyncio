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
import subprocess
import selectors
import warnings
import sys
import os

if sys.platform == 'win32':
    _GLib_IOChannel_new_socket = GLib.IOChannel.win32_new_socket
else:
    _GLib_IOChannel_new_socket = GLib.IOChannel.unix_new

class GAsyncIOSelector(selectors._BaseSelectorImpl):
    def __init__(self):
        super().__init__()
        self._sources = {}

    @staticmethod
    def _events_to_io_condition(events):
        return \
            (GLib.IOCondition.IN if events & selectors.EVENT_READ else GLib.IOCondition(0)) | \
            (GLib.IOCondition.OUT if events & selectors.EVENT_WRITE else GLib.IOCondition(0))

    @staticmethod
    def _io_condition_to_events(condition):
        return \
            (selectors.EVENT_READ if condition & GLib.IOCondition.IN else 0) | \
            (selectors.EVENT_WRITE if condition & GLib.IOCondition.OUT else 0)

    def register(self, fileobj, events, data):
        key = super().register(fileobj, events, data)
        if key.fd in self._sources:
            raise RuntimeError
        io_channel = _GLib_IOChannel_new_socket(key.fd)
        io_channel.set_encoding(None)
        io_channel.set_buffered(False)
        self._sources[key.fd] = GLib.io_add_watch(io_channel, GLib.PRIORITY_DEFAULT, self._events_to_io_condition(events), self._channel_watch_cb, key)
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

class _GLibSubprocessTransport(asyncio.base_subprocess.BaseSubprocessTransport):
    class _GlibProcEmulator():
        def __init__(self, child):
            self.pid = child.child_pid
            self.stdin = child.standard_input
            self.stderr = child.standard_error
            self.stdout = child.standard_output
            self.returncode = None

        def poll(self):
            if self.returncode is None:
                raise NotImplementedError
            # Should return returncode
            return self.returncode

        def kill(self):
            raise NotImplementedError

        def send_signal(self, signal):
            raise NotImplementedError

        def terminate(self):
            raise NotImplementedError

    def _on_exit(self, pid, waitstatus):
        returncode = waitstatus
        GLib.spawn_close_pid(pid)
        self._loop.call_soon_threadsafe(self._loop.call_soon, self._process_exited, returncode)

    def _start(self, args, shell, stdin, stdout, stderr, bufsize, **kwargs):
        working_dir = None
        flags = GLib.SpawnFlags.DO_NOT_REAP_CHILD
        flags |= GLib.SpawnFlags.SEARCH_PATH | GLib.SpawnFlags.SEARCH_PATH_FROM_ENVP
        #if stdin != asyncio.subprocess.PIPE:
        #    flags |= GLib.SpawnFlags.STDIN_FROM_DEV_NULL
        if stdout != asyncio.subprocess.PIPE:
            GLib.SpawnFlags.STDOUT_TO_DEV_NULL
        if stderr != asyncio.subprocess.PIPE:
            GLib.SpawnFlags.STDERR_TO_DEV_NULL
        if shell:
            if sys.platform == 'win32':
                comspec = os.environ.get("COMSPEC", "cmd.exe")
                args = [comspec, '/c', subprocess.list2cmdline(args)]
            else:
                unix_shell = ('/system/bin/sh' if hasattr(sys, 'getandroidapilevel') else '/bin/sh')
                args = [unix_shell, '-c'] + args
        child = GLib.spawn_async_with_pipes(
            working_dir, args,
            None, #[k + '=' + v for k, v in os.environ.items()],
            flags, None)
        if not child:
            raise RuntimeError("Failed to open child process")
        self._proc = _GLibSubprocessTransport._GlibProcEmulator(child)
        GLib.child_watch_add(GLib.PRIORITY_DEFAULT_IDLE, self._proc.pid, self._on_exit)

class _GLibBasePipeTransport(asyncio.transports._FlowControlMixin, asyncio.transports.WriteTransport):
    def __init__(self, loop, pipe, protocol, waiter=None, extra=None):
        super().__init__(extra, loop)
        self._extra['pipe'] = pipe
        self._pipe = pipe
        self._protocol = protocol
        self._loop = loop
        self._io = GLib.IOChannel(pipe)
        try:
            self._io.set_flags(GLib.IOFlags.NONBLOCK)
        except:
            # We are most likely on windows, here we need to disable buffering
            #self._io.set_buffered(False)
            pass
        self._extra['io'] = self._io
        self._conn_lost = 0
        self._closing = False  # Set when close() or write_eof() called.
        self._watch_source = None

        self._loop.call_soon(self._protocol.connection_made, self)
        if waiter is not None:
            # only wake up the waiter when connection_made() has been called
            self._loop.call_soon(asyncio.futures._set_result_unless_cancelled,
                                 waiter, None)

    def set_protocol(self, protocol):
        self._protocol = protocol

    def get_protocol(self):
        return self._protocol

    def is_closing(self):
        return self._closing

    def __del__(self, _warn=warnings.warn):
        if self._io is not None:
            _warn(f"unclosed transport {self!r}", ResourceWarning, source=self)
            self._io.shutdown(False)

    def abort(self):
        self._close(None)

    def _remove_watch(self):
        if self._watch_source:
            GLib.source_remove(self._watch_source)
            self._watch_source = None

    def _do_channel_errors(self, condition):
        if condition & GLib.IOCondition.ERR:
            self._fatal_error(None, 'Fatal error on pipe transport')
            self._remove_watch()
            self._io.shutdown(False)
            return True
        if condition & GLib.IOCondition.HUP:
            self._call_connection_lost(None)
            return True
        return False

    def _fatal_error(self, exc, message='Fatal error on pipe transport'):
        # should be called by exception handler only
        if isinstance(exc, OSError):
            if self._loop.get_debug():
                logger.debug("%r: %s", self, message, exc_info=True)
        else:
            self._loop.call_exception_handler({
                'message': message,
                'exception': exc,
                'transport': self,
                'protocol': self._protocol,
            })
        self._close(exc)

    def _close(self, exc=None):
        if self._closing:
            return
        self._closing = True
        self._remove_watch()
        self._loop.call_soon(self._call_connection_lost, exc)

    def _call_connection_lost(self, exc):
        try:
            self._protocol.connection_lost(exc)
        finally:
            self._closing = True
            self._remove_watch()
            self._io.shutdown(True)
            self._io = None
            self._protocol = None
            self._loop = None


class _GLibWritePipeTransport(_GLibBasePipeTransport):
    def __init__(self, loop, pipe, protocol, waiter=None, extra=None):
        super().__init__(loop, pipe, protocol, waiter, extra)
        self._buffer = bytearray()

    def get_write_buffer_size(self):
        return len(self._buffer)

    def write(self, data):
        assert isinstance(data, (bytes, bytearray, memoryview)), repr(data)
        if isinstance(data, bytearray):
            data = memoryview(data)
        if not data:
            return

        if self._conn_lost or self._closing:
            if self._conn_lost >= constants.LOG_THRESHOLD_FOR_CONNLOST_WRITES:
                logger.warning('pipe closed by peer or '
                               'IOChannel.write_chars(pipe, data) raised exception.')
            self._conn_lost += 1
            return

        if not self._buffer:
            # Attempt to send it right away first.
            try:
                status, n = self._io.write_chars(data, len(data))
                print(status, n)
            except (BlockingIOError, InterruptedError):
                n = 0
            except (SystemExit, KeyboardInterrupt):
                raise
            except BaseException as exc:
                self._conn_lost += 1
                self._fatal_error(exc, 'Fatal write error on pipe transport')
                return
            if n == len(data):
                return
            elif n > 0:
                data = memoryview(data)[n:]
            self._watch_source = GLib.io_add_watch(self._io, GLib.PRIORITY_DEFAULT,
                GLib.IOCondition.OUT | GLib.IOCondition.ERR | GLib.IOCondition.HUP,
                self._write_ready)

        self._buffer += data
        self._maybe_pause_protocol()

    def _write_ready(self, channel, condition):
        assert self._buffer, 'Data should not be empty'
        if self._do_channel_errors(condition):
            return
        try:
            status, n = self._io.write_chars(self._buffer, len(self._buffer))
            print(status, n)
        except (BlockingIOError, InterruptedError):
            pass
        except (SystemExit, KeyboardInterrupt):
            raise
        except BaseException as exc:
            self._buffer.clear()
            self._conn_lost += 1
            self._fatal_error(exc, 'Fatal write error on pipe transport')
        else:
            if n == len(self._buffer):
                self._buffer.clear()
                self._remove_watch()
                self._maybe_resume_protocol()  # May append to buffer.
                if self._closing:
                    self._call_connection_lost(None)
                return
            elif n > 0:
                del self._buffer[:n]

    def close(self):
        if self._io is not None and not self._closing:
            # write_eof is all what we needed to close the write pipe
            self.write_eof()

    def _close(self, exc=None):
        self._buffer.clear()
        super()._close(exc)

    def can_write_eof(self):
        return True

    def write_eof(self):
        if self._closing:
            return
        assert self._pipe
        self._closing = True
        if not self._buffer:
            self._loop.call_soon(self._call_connection_lost, None)


class _GLibReadPipeTransport(_GLibBasePipeTransport):
    def __init__(self, loop, pipe, protocol, waiter=None, extra=None):
        super().__init__(loop, pipe, protocol, waiter, extra)
        self._paused = False
        # only start reading when connection_made() has been called
        self._loop.call_soon(self._start_reading)

    def _start_reading(self):
        self._watch_source = GLib.io_add_watch(self._io,
            GLib.PRIORITY_DEFAULT, GLib.IOCondition.IN | GLib.IOCondition.ERR | GLib.IOCondition.HUP,
            self._read_ready)

    def _read_ready(self, channel, condition):
        if self._do_channel_errors(condition):
            return
        try:
            data = channel.read()
        except (BlockingIOError, InterruptedError):
            pass
        except OSError as exc:
            self._fatal_error(exc, 'Fatal read error on pipe transport')
        else:
            if data:
                self._protocol.data_received(data)
            else:
                if self._loop.get_debug():
                    logger.info("%r was closed by peer", self)
                self._closing = True
                self._remove_watch()
                self._loop.call_soon(self._protocol.eof_received)
                self._loop.call_soon(self._call_connection_lost, None)        

    def pause_reading(self):
        if self._closing or self._paused:
            return
        self._paused = True
        self._remove_watch()
        if self._loop.get_debug():
            logger.debug("%r pauses reading", self)

    def resume_reading(self):
        if self._closing or not self._paused:
            return
        self._paused = False
        self._start_reading()
        if self._loop.get_debug():
            logger.debug("%r resumes reading", self)

    def close(self):
        if not self._closing:
            self._close(None)


class GAsyncIOEventLoop(asyncio.selector_events.BaseSelectorEventLoop):
    def __init__(self):
        self._is_slave = False
        super().__init__(GAsyncIOSelector())
        self._giteration = None
        GLib.idle_add(self._schedule_giteration)

    def is_running(self):
        return self._is_slave

    def start_slave_loop(self):
        """
        Prepare loop to be run by the GLib main event loop.
        asyncio.get_event_loop() and asyncio.get_running_loop() will
        return self, but self.is_running() will return False.
        """
        self._check_closed()
        self._check_running()
        self._set_coroutine_origin_tracking(self._debug)

        self._old_agen_hooks = sys.get_asyncgen_hooks()
        sys.set_asyncgen_hooks(firstiter=self._asyncgen_firstiter_hook,
                               finalizer=self._asyncgen_finalizer_hook)
        asyncio.events._set_running_loop(self)
        self._is_slave = True

    def stop_slave_loop(self):
        """
        Undo the effects of self.start_slave_loop().
        """
        if not self._is_slave:
            raise RuntimeError('This event loop is not running as a slave')
        self._is_slave = False
        asyncio.events._set_running_loop(None)
        self._set_coroutine_origin_tracking(False)
        sys.set_asyncgen_hooks(*self._old_agen_hooks)

    def run_without_glib_until_complete(self, future):
        """
        Run loop without the GLib main loop.  This will block the GLib
        main loop, so only use this for a future that will complete
        immediately, or when the GLib main loop isn't running.
        """
        if asyncio._get_running_loop() is self:
            is_slave, self._is_slave = self._is_slave, False
            asyncio._set_running_loop(None)
            super().run_until_complete(future)
            asyncio._set_running_loop(self)
            self._is_slave = is_slave

    def run_application(self, app, argv):
        """
        Run a Gio.Application in a GAsyncIOEventLoop.
        Calls self.start_slave_loop(), app.run(), self.stop_slave_loop(),
        and self.close().
        """
        self.start_slave_loop()
        try:
            app.run(argv)
        finally:
            self.stop_slave_loop()
            self.close()

    def close(self):
        if self._giteration is not None:
            GLib.source_remove(self._giteration)
            self._giteration = None
        super().close()

    def call_at(self, when, callback, *args, context=None):
        self._check_closed()
        if self._debug:
            self._check_thread()
            self._check_callback(callback, 'call_at')
        timer = asyncio.events.TimerHandle(when, callback, args, self, context)
        if timer._source_traceback:
            del timer._source_traceback[-1]
        delay = (when - self.time()) * 1000
        if delay < 0:
            delay = 0
        timer._scheduled = GLib.timeout_add(delay, self._timeout_cb, timer)
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

    # subprocess_exec implementation
    async def _make_subprocess_transport(self, protocol, args, shell,
                                         stdin, stdout, stderr, bufsize,
                                         extra=None, **kwargs):
        waiter = self.create_future()
        transp = _GLibSubprocessTransport(self, protocol, args, shell,
                                          stdin, stdout, stderr, bufsize,
                                          waiter=waiter, extra=extra,
                                          **kwargs)
        try:
            await waiter
        except (SystemExit, KeyboardInterrupt):
            raise
        except BaseException:
            transp.close()
            await transp._wait()
            raise
        return transp

    def _make_read_pipe_transport(self, pipe, protocol, waiter=None,
                                  extra=None):
        return _GLibReadPipeTransport(self, pipe, protocol, waiter, extra)

    def _make_write_pipe_transport(self, pipe, protocol, waiter=None,
                                   extra=None):
        return _GLibWritePipeTransport(self, pipe, protocol, waiter, extra)


class GAsyncIOEventLoopPolicy(asyncio.events.BaseDefaultEventLoopPolicy):
    _loop_factory = GAsyncIOEventLoop
