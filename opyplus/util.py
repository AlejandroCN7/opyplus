"""Utilities functions for opyplus."""

import datetime as dt
import logging
import subprocess
import os
import io
import sys
import threading
import contextlib
import textwrap

import cchardet as chardet
import pandas as pd


from opyplus import __version__, CONF

logger = logging.getLogger(__name__)


def sort_df(df):
    """
    Sort DataFrame using the correct method depending on pandas version.

    Parameters
    ----------
    df: pandas.DataFrame

    Returns
    -------
    pandas.DataFrame
    """
    version = tuple([int(x) for x in pd.__version__.split(".")])
    if version < (0, 20, 0):
        return df.sort()
    else:
        return df.sort_index()


def get_multi_line_copyright_message(prefix="! "):
    """
    Get opyplus multi-line copyright message.

    Parameters
    ----------
    prefix: str
        Comment prefix

    Returns
    -------
    str
    """
    return textwrap.indent(
        "-"*45 + f"""\nGenerated by opyplus version {__version__}
Copyright (c) {dt.datetime.now().year}, Openergy development team
http://www.openergy.fr
https://github.com/openergy/opyplus\n""" + "-"*45,
        prefix,
        lambda line: True
    ) + "\n\n"


def get_mono_line_copyright_message():
    """
    Get opyplus single line copyright message.

    Returns
    -------
    str
    """
    return "opyplus version %s - copyright (c) %s - Openergy development team" % (__version__, dt.datetime.now().year)


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
    """
    Redirect text from stream src to stream dst.

    Parameters
    ----------
    src: typing.StringIO
    dst: typing.StringIO
    freq: float
    """
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
    """
    'Stream' that allows to write to a logger.

    Parameters
    ----------
    logger_name: str
        Name of the logger
    level: int
        Logging level
    """

    def __init__(self, logger_name, level):
        self._logger = logging.getLogger(logger_name)
        self._level = level

    def write(self, message):
        """
        Write to stream.

        Parameters
        ----------
        message: str
        """
        message = message.strip()
        if message != "":
            self._logger.log(self._level, message)


class PrintFunctionStreamWriter:
    """
    'Stream' that allows to write to a print_function.

    Parameters
    ----------
    print_function: typing.Callable
    """

    def __init__(self, print_function):
        self._print_function = print_function

    def write(self, message):
        """
        Write to stream.

        Parameters
        ----------
        message: str
        """
        message = message.strip()
        if message != "":
            self._print_function(message)


def run_subprocess(
        command,
        cwd=None,
        stdout=None,
        stderr=None,
        shell=False,
        beat_freq=None,
        message="subprocess is still running\n"
):
    """
    Run a subprocess and manage its stdout/stderr streams.

    Parameters
    ----------
    command: command
    cwd: current working directory
    stdout: output info stream (must have 'write' method)
    stderr: output error stream (must have 'write' method)
    shell: see subprocess.Popen
    beat_freq: if not none, stdout will be used at least every beat_freq (in seconds)
    message: message to display in stdout at every beat
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
                    stdout.write(message)
                    if hasattr(sys.stdout, "flush"):
                        sys.stdout.flush()
        return sub_p.returncode


def get_string_buffer(path_or_content, expected_extension):
    """
    Get string buffer from different types of inputs.

    path_or_content: str or bytes or typing.StringIO or typing.BytesIO
        Path or content as string, bytes or buffer

    Returns
    -------
    typing.StringIO, str
        String buffer and path.

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
    """
    Get a StringIO from different type of inputs.

    Parameters
    ----------
    buffer_writer
    string_writer
    buffer_or_path

    Returns
    -------
    typing.StringIO
    """
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
    """
    Get a buffer from a buffer or a path.

    Parameters
    ----------
    buffer_or_path: typing.StringIO or str

    Returns
    -------
    typing.StringIO
    """
    if isinstance(buffer_or_path, str):
        if not os.path.isfile(buffer_or_path):
            raise FileNotFoundError(f"no file found at given path: {buffer_or_path}")
        path = buffer_or_path
        with open(buffer_or_path, "rb") as f:
            encoding = chardet.detect(f.read())
        buffer = open(buffer_or_path, encoding=encoding["encoding"], errors="ignore")
    else:
        path = None
        buffer = buffer_or_path
    return path, buffer


def version_str_to_version(version_str):
    """
    Version str to tuple.

    Parameters
    ----------
    version_str: str
        x.x or x.x.x or x.x.x.x

    Returns
    -------
    int, int, int
        Version as a tuple of 3 int
    """
    raw_version = [int(v) for v in version_str.split(".")] + [0]

    if len(raw_version) < 3:
        raise ValueError(f"incorrect format: {version_str}")

    return tuple(raw_version[:3])
