import argparse
import textwrap as _textwrap


class QuotebotHelpFormatter(argparse.HelpFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, max_help_position=0, width=1000000, **kwargs)

    def _split_lines(self, text, width):
        text = self._whitespace_matcher.sub(' ', text).strip()
        return _textwrap.wrap(text, width) + ["\n"]
