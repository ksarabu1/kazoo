"""Kazoo Logging for Zookeeper

Zookeeper logging redirects that fashion the appropriate logging setup based
on the handler used for the :class:`~kazoo.client.KazooClient`.

"""
import os
import logging

import zookeeper

from kazoo.handlers.util import get_realthread

zk_log = logging.getLogger('ZooKeeper')
_logging_setup = False


def setup_logging(use_gevent=False):
    global _logging_setup

    if _logging_setup:
        return

    if use_gevent:
        import gevent
        from kazoo.handlers.gevent import _pipe
        _logging_pipe = _pipe()
        zookeeper.set_log_stream(os.fdopen(_logging_pipe[1], 'w'))

        gevent.spawn(_logging_greenlet, _logging_pipe)
    else:
        _logging_pipe = os.pipe()
        zookeeper.set_log_stream(os.fdopen(_logging_pipe[1], 'w'))

        thread = get_realthread()
        thread.start_new_thread(_logging_thread, (_logging_pipe,))
    _logging_setup = True


def _process_message(line):
    """Line processor used by all loggers"""
    log = zk_log.log
    levels = dict(ZOO_INFO=logging.INFO,
                  ZOO_WARN=logging.WARNING,
                  ZOO_ERROR=logging.ERROR,
                  ZOO_DEBUG=logging.DEBUG,
                  )
    try:
        if '@' in line:
            level, message = line.split('@', 1)
            level = levels.get(level.split(':')[-1])

            if 'Exceeded deadline by' in line and level == logging.WARNING:
                level = logging.DEBUG

        else:
            level = None

        if level is None:
            log(logging.INFO, line)
        else:
            log(level, message)
    except Exception as v:
        zk_log.exception("Logging error: %s", v)


def _logging_greenlet(logging_pipe):
    """Zookeeper logging redirect

    This greenlet based logger waits for the pipe to get data, then reads
    lines off it and processes them.

    Used for gevent.

    """
    from gevent.socket import wait_read
    r, w = logging_pipe
    while 1:
        wait_read(r)
        data = []
        char = os.read(r, 1)
        while char != '\n':
            data.append(char)
            char = os.read(r, 1)
        line = ''.join(data).strip()
        if not line:
            return
        _process_message(line)


def _logging_thread(logging_pipe):
    """Zookeeper logging redirect

    Zookeeper by default logs directly out. This thread handles reading
    off the pipe that the above `set_log_stream` call designates so
    that the Zookeeper logging output can be turned into Python logging
    statements under the `Zookeeper` name.

    Used for threading.

    """
    r, w = logging_pipe
    f = os.fdopen(r)
    while 1:
        line = f.readline().strip()

        # Skip empty lines
        if not line:
            continue
        _process_message(line)
