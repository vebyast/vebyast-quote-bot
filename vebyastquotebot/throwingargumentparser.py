import argparse

# code from https://stackoverflow.com/a/14728477

# a subclass of argparse that throws an error when it encounters a problem
# instead of completely exiting. This makes it suitable for use internally
# instead of to drive the argument parsing of a CLI executable.

class ArgumentParserError(Exception):
    pass

class ArgumentParserExited(Exception):
    pass

class ThrowingArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, outfile, **kwargs):
        super().__init__(*args, **kwargs)
        self.__outfile = outfile

    def error(self, message):
        raise ArgumentParserError(message)

    def exit(self, status=0, message=None):
        raise ArgumentParserExited(message)

    def _print_message(self, message, file=None):
        if message:
            self.__outfile.write(message)
