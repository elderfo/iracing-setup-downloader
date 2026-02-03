"""Shared utility functions for the iRacing setup downloader."""


def sanitize_filename(filename: str) -> tuple[str, bool]:
    """Sanitize a filename by replacing spaces with underscores.

    Args:
        filename: The filename to sanitize

    Returns:
        Tuple of (sanitized filename, whether the filename was changed)
    """
    # Avoid unnecessary string allocation when no spaces are present
    if " " not in filename:
        return filename, False

    return filename.replace(" ", "_"), True
