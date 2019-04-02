import datetime as dt
import logging
import subprocess
import os
import io
import sys
import threading
import contextlib
import textwrap


import pandas as pd


from oplus import __version__, CONF

logger = logging.getLogger(__name__)


def sort_df(df):
    version = tuple([int(x) for x in pd.__version__.split(".")])
    if version < (0, 20, 0):
        return df.sort()
    else:
        return df.sort_index()


def get_multi_line_copyright_message(prefix="! "):
    return textwrap.indent(
        "-"*45 + f"""\nGenerated by oplus version {__version__}
Copyright (c) {dt.datetime.now().year}, Openergy development team
http://www.openergy.fr
https://github.com/openergy/oplus\n""" + "-"*45 + "\n\n",
        prefix,
        lambda line: True
    )


def get_mono_line_copyright_message():
    return "oplus version %s - copyright (c) %s - Openergy development team" % (__version__, dt.datetime.now().year)


def _redirect_stream(src, dst, stop_event, freq):
    while not stop_event.is_set():  # read all filled lines
        try:
            content = src.readline()
        except UnicodeDecodeError as e:
            logger.error(str(e))
            content = "unicode decode error"
        if content == "":  # empty: break
            break
        dst.write(content)
        if hasattr(dst, "flush"):
            dst.flush()


@contextlib.contextmanager
def redirect_stream(src, dst, freq=0.1):
    stop_event = threading.Event()
    t = threading.Thread(target=_redirect_stream, args=(src, dst, stop_event, freq))
    t.daemon = True
    t.start()
    try:
        yield
    finally:
        stop_event.set()
        t.join()


class LoggerStreamWriter:
    def __init__(self, logger_name, level):
        self._logger = logging.getLogger(logger_name)
        self._level = level

    def write(self, message):
        message = message.strip()
        if message != "":
            self._logger.log(self._level, message)


def run_subprocess(command, cwd=None, stdout=None, stderr=None, shell=False, beat_freq=None):
    """
    Parameters
    ----------
    command: command
    cwd: current working directory
    stdout: output info stream (must have 'write' method)
    stderr: output error stream (must have 'write' method)
    shell: see subprocess.Popen
    beat_freq: if not none, stdout will be used at least every beat_freq (in seconds)
    """
    sys.encoding = CONF.encoding
    # prepare variables
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr

    # run subprocess
    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        shell=shell,
        universal_newlines=True
    ) as sub_p:
        # link output streams
        with redirect_stream(sub_p.stdout, stdout), redirect_stream(sub_p.stderr, stderr):
            while True:
                try:
                    sub_p.wait(timeout=beat_freq)
                    break
                except subprocess.TimeoutExpired:
                    stdout.write("subprocess is still running\n")
                    if hasattr(sys.stdout, "flush"):
                        sys.stdout.flush()
        return sub_p.returncode


def get_string_buffer(path_or_content, expected_extension):
    """
    path_or_content: path or content_str or content_bts or string_io or bytes_io

    Returns
    -------
    string_buffer, path

    path will be None if input was not a path
    """
    buffer, path = None, None

    # path or content string

    if isinstance(path_or_content, str):
        if path_or_content[-len(expected_extension)-1:] == ".%s" % expected_extension:
            if not os.path.isfile(path_or_content):
                raise FileNotFoundError("No file at given path: '%s'." % path_or_content)
            buffer, path = open(path_or_content, encoding=CONF.encoding), path_or_content
        else:
            buffer = io.StringIO(path_or_content, )

    # text io
    elif isinstance(path_or_content, io.TextIOBase):
        buffer = path_or_content

    # bytes
    elif isinstance(path_or_content, bytes):
        buffer = io.StringIO(path_or_content.decode(encoding=CONF.encoding))
    elif isinstance(path_or_content, io.BufferedIOBase):
        buffer = io.StringIO(path_or_content.read().decode(encoding=CONF.encoding))
    else:
        raise ValueError("path_or_content type could not be identified")

    return buffer, path


def multi_mode_write(buffer_writer, string_writer, buffer_or_path=None):
    # manage string mode
    if buffer_or_path is None:
        return string_writer()

    # manage buffer mode
    if isinstance(buffer_or_path, str):
        buffer = open(buffer_or_path, "w")
    else:
        buffer = buffer_or_path

    with buffer:
        buffer_writer(buffer)


def to_buffer(buffer_or_path):
    if isinstance(buffer_or_path, str):
        if not os.path.isfile(buffer_or_path):
            raise FileNotFoundError(f"no file found at given path: {buffer_or_path}")
        path = buffer_or_path
        buffer = open(buffer_or_path, encoding=CONF.encoding)
    else:
        path = None
        buffer = buffer_or_path
    return path, buffer
