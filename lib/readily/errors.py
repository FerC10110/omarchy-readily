"""The one exception every command raises, carrying the exit code to use."""

GENERAL = 1
USAGE = 2
CHANGED = 3
NO_FOLDER = 4


class ReadilyError(Exception):
    def __init__(self, message, code=GENERAL):
        super().__init__(message)
        self.code = code
