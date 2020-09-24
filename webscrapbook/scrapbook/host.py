"""Scrapbook host handler.
"""
import os
import time
from threading import Thread
from .. import WSB_DIR
from .. import Config
from .. import util


class LockError(Exception):
    def __init__(self, msg, name=None, file=None):
        self.msg = msg
        self.name = name
        self.file = file


class LockAcquireError(LockError):
    pass


class LockTimeoutError(LockAcquireError):
    pass


class LockGenerateError(LockAcquireError):
    pass


class LockRegenerateError(LockGenerateError):
    pass


class LockExtendError(LockError):
    pass


class LockExtendNotAcquiredError(LockExtendError):
    pass


class LockExtendNotFoundError(LockExtendError):
    pass


class LockReleaseError(LockError):
    pass


class LockReleaseNotAcquiredError(LockReleaseError):
    pass


class LockReleaseNotFoundError(LockReleaseError):
    pass


class _FileLockAcquireProxy:
    """A help class object returned by FileLock.acquire() for using in a
       with statement.
    """
    def __init__(self, lock):
        self.lock = lock

    def __enter__(self):
        self.lock.keep()
        return self.lock

    def __exit__(self, exc_type, exc_value, traceback):
        if self.lock.locked:
            self.lock.release()


class FileLock:
    """Controller of file lock.
    """
    def __init__(self, host, name, *,
            timeout=5, stale=60, poll_interval=0.1,
            assume_acquired=False):
        self.host = host
        self.name = name
        self.timeout = timeout
        self.stale = stale
        self.poll_interval = poll_interval
        self.file = os.path.join(host.locks, f'{util.encrypt(name, method="md5")}.lock')
        self._lock = assume_acquired
        self._keeper = None

    @property
    def locked(self):
        """Check if this object holds a locking.
        """
        return self._lock

    def acquire(self):
        """Acquire the lock.

        Use this method in a context manager:

            with lock.acquire():
                '''do something'''

        or an acquire...release way:

            lock.acquire()
            try:
                '''do something'''
            finally:
                lock.release()
        """
        # skip if we are already locking
        if self._lock:
            return _FileLockAcquireProxy(self)

        timeout_time = time.time() + self.timeout

        try:
            os.makedirs(os.path.dirname(self.file))
        except FileExistsError:
            pass
        except OSError as exc:
            raise LockGenerateError(f'unable to create lock "{name}"',
                name=self.name, file=self.file) from exc

        while True:
            try:
                with open(self.file, 'x') as fh:
                    pass
            except FileExistsError:
                t = time.time()

                if t >= timeout_time:
                    raise LockTimeoutError(f'timeout when acquiring lock "{self.name}"',
                        name=self.name, file=self.file)

                try:
                    stale_time = os.stat(self.file).st_mtime + self.stale
                except FileNotFoundError:
                    # A rare case that lock file has been removed during the
                    # short inverval. Try acquire again.
                    continue
                except OSError as exc:
                    raise LockGenerateError(f'unable to create lock "{self.name}"',
                        name=self.name, file=self.file) from exc

                if t >= stale_time:
                    # Current lock file is stale. Touch rather than recreate
                    # for atomicity.
                    try:
                        os.utime(self.file)
                    except OSError as exc:
                        raise LockRegenerateError(
                            f'unable to regenerate stale lock "{self.name}"',
                            name=self.name, file=self.file) from exc
                    else:
                        break

                time.sleep(self.poll_interval)
            except OSError as exc:
                raise LockGenerateError(f'unable to create lock "{self.name}"',
                    name=self.name, file=self.file) from exc
            else:
                break

        self._lock = True
        return _FileLockAcquireProxy(self)

    def extend(self):
        """Extend duration of the lock.
        """
        if not self._lock:
            raise LockExtendNotAcquiredError(f'lock "{self.name}" has not been acquired',
                name=self.name, file=self.file)

        try:
            os.utime(self.file)
        except FileNotFoundError as exc:
            raise LockExtendNotFoundError(f'file for lock "{self.name}" does not exist',
                name=self.name, file=self.file) from exc
        except OSError as exc:
            raise LockExtendError(f'unable to extend lock "{self.name}"',
                name=self.name, file=self.file) from exc

    def release(self):
        """Release the lock.
        """
        if not self._lock:
            raise LockReleaseNotAcquiredError(f'lock "{self.name}" has not been acquired',
                name=self.name, file=self.file)

        try:
            os.remove(self.file)
        except FileNotFoundError as exc:
            raise LockReleaseNotFoundError(f'file for lock "{self.name}" does not exist',
                name=self.name, file=self.file) from exc
        except OSError as exc:
            raise LockReleaseError(f'unable to release lock "{self.name}"',
                name=self.name, file=self.file) from exc
        else:
            self._lock = False

    def keep(self):
        """Spawn a keeper thread to keep the lock fresh until released.

        Do not respawn if already have one.
        """
        if self._keeper:
            return self._keeper

        if not self._lock:
            return None

        self._keeper = Thread(target=self._extend, daemon=True)
        self._keeper.start()
        return self._keeper

    def _extend(self):
        """Auto extend the lock before stale in a shorter interval.
        """
        poll_interval = self.stale * 0.2
        while True:
            time.sleep(poll_interval)

            # Skip if the lock has been released.
            # If this lock is re-acquired after a previous release, this
            # keeper will keep working until next release.
            if not self._lock:
                self._keeper = None
                break

            self.extend()


class Host:
    """Controller for a scrapbook set defined by a root directory and configs.
    """
    REPR_ATTRS = ('name', 'root')

    def __init__(self, root, config=None):
        # use the same realpath during the process lifetime
        root = os.path.realpath(root)

        if not config:
            config = Config()
            config.load(root)

        self.root = root
        self.config = config
        self.name = config['app']['name']

        self.chroot = os.path.normpath(os.path.join(root, self.config['app']['root']))
        self.themes = [
            os.path.join(root, WSB_DIR, 'themes', config['app']['theme']),
            os.path.normpath(os.path.join(__file__, '..', '..', 'themes', config['app']['theme'])),
            ]
        self.statics = [os.path.join(t, 'static') for t in self.themes]
        self.templates = [os.path.join(t, 'templates') for t in self.themes]

        self.locks = os.path.join(root, WSB_DIR, 'locks')

    def __repr__(self):
        repr_str = ', '.join(f'{attr}={repr(getattr(self, attr))}' for attr in self.REPR_ATTRS)
        return f'{self.__class__.__name__}({repr_str})'

    def get_static_file(self, filepath):
        """Search for a static file.
        """
        for i in self.statics:
            file = os.path.join(i, filepath)
            if os.path.isfile(file):
                return file
        return None

    def get_lock(self, name, *args, **kwargs):
        """Get a lock object to control lock.
        """
        return FileLock(self, name, *args, **kwargs)
