"""Shared utility functions for the iRacing setup downloader."""


def sanitize_filename(filename: str) -> tuple[str, bool]:
    """Sanitize a filename by replacing spaces and path separators with underscores.

    Replaces characters that are unsafe in filenames:
    - Spaces → underscores
    - Forward slashes (/) → underscores
    - Backslashes (\\) → underscores

    Args:
        filename: The filename to sanitize

    Returns:
        Tuple of (sanitized filename, whether the filename was changed)
    """
    sanitized = filename.replace("/", "_").replace("\\", "_").replace(" ", "_")
    return sanitized, sanitized != filename
