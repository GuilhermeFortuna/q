"""User-facing errors: printed as one line, exit code 1."""


class QworkError(Exception):
    """A failure the user can act on."""
