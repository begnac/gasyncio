import socket
import select
import selectors
import asyncio
import threading

# Based on an idea from tornado HTTP server
class ThreadSelector(selectors.SelectSelector):
    def __init__(self):
        self._loop = None
        self._thread = None
        self._closed = False
        super().__init__()

    def register(self, fileobj, events, data):
        super().register(fileobj, events, data)
        self._wake_selector()

    def unregister(self, fileobj):
        key = super().unregister(fileobj)
        self._wake_selector()

    def select(self, timeout=None):
        # Never actually call select in the main thread
        return []

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._thread is None:
            return
        self._wake_selector()
        self._thread.join()
        self._loop.remove_reader(self._waker_r)
        self._waker_r.close()
        self._waker_w.close()

    def create_thread(self):
        thread = threading.Thread(
            name="Thread selector",
            daemon=True,
            target=self._run_select,
        )
        self._waker_r, self._waker_w = socket.socketpair()
        self._waker_r.setblocking(False)
        self._waker_w.setblocking(False)
        self._thread = thread
        thread.start()
        self._loop.add_reader(self._waker_r, self._consume_waker)

    def _wake_selector(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._thread is None:
            self._loop = loop
            self.create_thread()
        assert self._loop == loop
        try:
            self._waker_w.send(b"W")
        except BlockingIOError:
            pass

    def _consume_waker(self):
        if self._thread is None:
            return
        try:
            self._waker_r.recv(1024)
        except BlockingIOError:
            pass

    def _run_select(self):
        while not self._closed:
            try:
                # Commonly used execute select
                rs, ws, xs = select.select(self._readers, self._writers, self._writers)
                ws = ws + xs
            except OSError as e:
                # Error handling taken from tornado thread selector
                if e.errno == getattr(errno, "WSAENOTSOCK", errno.EBADF):
                    rs, _, _ = select.select([self._waker_r.fileno()], [], [], 0)
                    if rs:
                        ws = []
                    else:
                        raise
                else:
                    raise

            try:
                self._loop.call_soon_threadsafe(self._handle_select, rs, ws)
            # Some common errors on race with closing the loop
            except RuntimeError:
                pass
            except AttributeError:
                pass

    def _handle_select(self, r, w):
        # Select processing rutine from selectors.py from cpython
        ready = []
        r = frozenset(r)
        w = frozenset(w)
        rw = r | w
        fd_to_key_get = self._fd_to_key.get
        for fd in rw:
            key = fd_to_key_get(fd)
            if key:
                events = ((fd in r and selectors.EVENT_READ) | (fd in w and selectors.EVENT_WRITE))
                ready.append((key, events & key.events))
        self._loop._process_events(ready)
