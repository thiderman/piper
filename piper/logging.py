#!/usr/bin/env python
# coding: utf-8

import re
import os
import sys
import hashlib
import logbook
import blessings

from piper import utils

# TODO: Some of these only work on dark terminals. Investigate.
COLORS = (
    23, 24, 25, 26, 27, 29, 30, 31, 32, 33, 35, 36, 37, 38, 39, 41, 42, 43, 44,
    45, 47, 48, 49, 50, 51, 58, 59, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73,
    74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 94, 95, 96, 97,
    98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112,
    113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 130, 131, 132, 133,
    134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148,
    149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 162, 166, 167, 168,
    169, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184,
    185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 202, 205, 206, 207,
    208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222,
    223, 224, 225, 226, 227, 228
)
COLOR_LEN = len(COLORS)

# Any consecutive string containing a slash
# The end of "foo (x/y)"
COUNTER_RXP = re.compile(r'(\s*\(\d+/\d+\))$')

DEFAULT_FORMAT_STRING = (
    '{t.bold}{t.black}['
    '{t.normal}{t.cyan}{record.time:%Y-%m-%d %H:%M:%S.%f}'
    '{t.bold}{t.black}]{t.normal} '
    '{level_color}{record.level_name:>5} '
    '{t.bold}{colorized_channel}'
    '{t.bold}{t.black}:{t.normal} '
    '{record.message}'
)

DEFAULT_LOGFILE_FORMAT_STRING = (
    '[{record.time:%Y-%m-%d %H:%M:%S.%f}]'
    ' {record.level_name:>5} {record.channel}: {record.message}'
)

# This separator is used to split multiple channels to colorize each one.
# Dot was used at first, but that breaks command lines more than not.
SEPARATOR = ': '


class Colorizer:
    terminal = blessings.Terminal()

    def __init__(self, regexp, formatting, aborting=False, flags=0):
        self.regexp = re.compile(regexp, flags)
        self.formatting = formatting + '{t.normal}'
        self.aborting = aborting

    def colorize(self, message):
        """
        Recursively apply the color regexp on the message

        """

        try:
            match = self.regexp.search(message)
            if match:
                start, stop = match.span()
                before, after = match.string[:start], match.string[stop:]
                colored = self.formatting.format(
                    *match.groups(), t=self.terminal
                )

                # Colorize the remaining part as well; there might be matching
                # parts left in the part that was not colorized yet.
                done, after = self.colorize(after)
                message = before + colored + after
                if done:
                    return True, message

            return bool(match), message

        except TypeError:  # pragma: nocover
            # We were passed something we don't understand. Just pass down.
            return True, message


COLORIZERS = (
    # Colorize UUIDs
    Colorizer(
        r'(\w{8}-\w{4}-\w{4}-\w{4}-\w{12})',
        '{t.bold_magenta}{0}{t.normal}',
        True,
        re.I
    ),
    # Colorize error messages
    Colorizer(r'^(err(?:or)?)(.*)$', '{t.bold_red}{0}{1}', True, re.I),
    # Colorize warning messages
    Colorizer(r'^(warn(?:or)?)(.*)$', '{t.bold_yellow}{0}{1}', True, re.I),
    # Colorize paths based on if they contain slashes or not
    Colorizer(r'(\S*/[\S/]+)', '{t.bold_blue}{0}'),
    # Colorize environment variables
    Colorizer(r'([A-Z]+)(=)', '{t.bold_green}{0}{t.bold_black}{1}'),
    # Colorize PASSED
    Colorizer(r'(PASSED)', '{t.bold_green}{0}'),
    # Colorize FAILED
    Colorizer(r'(FAILED)', '{t.bold_red}{0}'),
)


class BlessingsStringFormatter(logbook.StringFormatter):
    """
    StringFormatter subclass that gives access to blessings.Terminal().

    This class adds the `t` object in the formatting string, which is an
    instance of blessings.Terminal(). It also provides helper functions to
    colorize the log level and log channel.

    """

    def __init__(self, format_string=None, colorizers=tuple()):
        self.colorizers = colorizers
        self.terminal = blessings.Terminal()
        self.md5_cache = {}

        if not format_string:
            format_string = DEFAULT_FORMAT_STRING

        format_string += '{t.normal}'
        super(BlessingsStringFormatter, self).__init__(format_string)

    def format_record(self, record, handler):
        record = self.prepare_record(record)
        kwargs = {
            'record': record,
            'handler': handler,
            't': self.terminal,
            'level_color': self.level_color(record),
            'colorized_channel': self.colorize_channel(record.channel),
        }

        try:
            return self._formatter.format(**kwargs)

        # These handlers are tested as a part of logbook, so let's not muck
        # around in trying to simulate those errors.
        except UnicodeEncodeError:  # pragma: nocover
            # self._formatter is a str, but some of the record items
            # are unicode
            fmt = self._formatter.decode('ascii', 'replace')
            return fmt.format(**kwargs)
        except UnicodeDecodeError:  # pragma: nocover
            # self._formatter is unicode, but some of the record items
            # are non-ascii str
            fmt = self._formatter.encode('ascii', 'replace')
            return fmt.format(**kwargs)

    def level_color(self, rc):  # pragma: nocover
        ret = ''
        if rc.level_name in ('ERROR', 'CRITICAL'):
            ret = self.terminal.red + self.terminal.bold
        if rc.level_name == 'WARNING':
            ret = self.terminal.yellow + self.terminal.bold
        if rc.level_name == 'DEBUG':
            ret = self.terminal.white
        return ret

    def colorize_channel(self, channel):
        # Split the channel on the seprator and colorize each one differently
        sep = self.terminal.black + SEPARATOR
        return sep.join(map(self.colorize, channel.split(SEPARATOR)))

    def colorize(self, string):
        """
        Colorize a string based on its hash.

        a color in the terminal colorspace is selected based on the integer
        value of md5sum of the channel name. Once calculated it is cached so
        that the digestion only happens once.

        """

        colorized = self.md5_cache.get(string)
        if not colorized:
            # Don't use the ' (x/y)' part when calculating colors. This makes
            # sure that the 'foo' step is always in one color regardless if it
            # is (1/12) or (33/100).
            target = COUNTER_RXP.sub('', string)

            md5 = hashlib.md5(target.encode()).hexdigest()
            index = self.get_color(md5)
            colorized = self.terminal.color(index) + string
            self.md5_cache.update({string: colorized})

        return colorized

    def get_color(self, md5):  # pragma: nocover
        return COLORS[int(md5, 16) % COLOR_LEN]

    def prepare_record(self, rc):
        """
        Manipulate the log message, adding colors using the set of Colorizer()
        instances.

        """

        for colorizer in self.colorizers:
            done, message = colorizer.colorize(rc.message)
            rc.message = message

            if done and colorizer.aborting is True:
                break

        return rc


def get_handlers(debug=False):  # pragma: nocover
    # Remove the default logbook.StderrHandler so that we can actually hide
    # debug output when debug is False. If we don't remove it, it will
    # always print to stderr anyway.
    try:
        logbook.default_handler.pop_application()
    except AssertionError:
        # The integration tests will try to pop it multiple times. This might
        # not be 100% super, but it's also something the application should not
        # have a problem with ever.
        pass

    level = logbook.INFO
    if debug:
        level = logbook.DEBUG

    stream = logbook.StreamHandler(sys.stdout, level=level, bubble=True)
    stream.formatter = BlessingsStringFormatter(colorizers=COLORIZERS)

    date = utils.now().strftime('%Y-%m-%dT%H:%M:%S')
    logfile = get_file_logger('logs/piper/session/{0}.log'.format(date), debug)

    return stream, logfile


def get_file_logger(filename, debug=False):  # pragma: nocover
    level = logbook.INFO
    if debug:
        level = logbook.DEBUG

    utils.mkdir(os.path.dirname(filename))

    return logbook.FileHandler(
        filename,
        format_string=DEFAULT_LOGFILE_FORMAT_STRING,
        level=level,
        bubble=True
    )
