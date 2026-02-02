"""Binary duplicate detection for .sto setup files using SHA-256 hashing."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DuplicateInfo:
    """Information about a detected duplicate file.

    Attributes:
        source_path: Path to the file being checked (new file)
        existing_path: Path to the existing duplicate file
        file_hash: SHA-256 hash of the file content
        file_size: Size of the file in bytes
    """

    source_path: Path
    existing_path: Path
    file_hash: str
    file_size: int


class FileHashCache:
    """Cache for SHA-256 file hashes with mtime/size validation.

    This cache stores file hashes and validates them based on file
    modification time and size to avoid expensive re-hashing of unchanged files.

    Attributes:
        BUFFER_SIZE: Size of read buffer for hashing large files (64KB)
    """

    BUFFER_SIZE = 65536  # 64KB read buffer

    def __init__(self) -> None:
        """Initialize the hash cache."""
        # Cache format: {path_str: (hash, mtime_ns, size)}
        self._cache: dict[str, tuple[str, int, int]] = {}

    def get_hash(self, file_path: Path) -> str:
        """Get the SHA-256 hash of a file, using cache if valid.

        Args:
            file_path: Path to the file to hash

        Returns:
            SHA-256 hash as a lowercase hex string

        Raises:
            FileNotFoundError: If the file doesn't exist
            OSError: If the file can't be read
        """
        file_path = file_path.resolve()
        path_str = str(file_path)

        # Get current file stats
        stat = file_path.stat()
        current_mtime = stat.st_mtime_ns
        current_size = stat.st_size

        # Check cache validity
        if path_str in self._cache:
            cached_hash, cached_mtime, cached_size = self._cache[path_str]
            if cached_mtime == current_mtime and cached_size == current_size:
                logger.debug("Cache hit for %s", file_path.name)
                return cached_hash

        # Calculate hash
        file_hash = self._compute_hash(file_path)

        # Update cache
        self._cache[path_str] = (file_hash, current_mtime, current_size)
        logger.debug("Computed hash for %s: %s", file_path.name, file_hash[:16])

        return file_hash

    def _compute_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of file content.

        Args:
            file_path: Path to the file to hash

        Returns:
            SHA-256 hash as a lowercase hex string
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(self.BUFFER_SIZE):
                sha256.update(chunk)
        return sha256.hexdigest()

    def compute_hash_from_bytes(self, content: bytes) -> str:
        """Compute SHA-256 hash of byte content.

        Useful for hashing ZIP file content before writing to disk.

        Args:
            content: Bytes to hash

        Returns:
            SHA-256 hash as a lowercase hex string
        """
        return hashlib.sha256(content).hexdigest()

    def preload_directory(
        self, directory: Path, pattern: str = "*.sto"
    ) -> dict[str, list[Path]]:
        """Pre-hash all matching files in a directory.

        Builds a mapping from hash to list of file paths, useful for
        detecting which files are duplicates of each other.

        Args:
            directory: Directory to scan
            pattern: Glob pattern for files to hash (default: "*.sto")

        Returns:
            Dictionary mapping hash to list of file paths with that hash
        """
        hash_to_paths: dict[str, list[Path]] = {}

        if not directory.exists():
            logger.debug("Directory does not exist for preload: %s", directory)
            return hash_to_paths

        files = list(directory.rglob(pattern))
        logger.info("Pre-hashing %d files in %s", len(files), directory)

        for file_path in files:
            try:
                file_hash = self.get_hash(file_path)
                if file_hash not in hash_to_paths:
                    hash_to_paths[file_hash] = []
                hash_to_paths[file_hash].append(file_path)
            except OSError as e:
                logger.warning("Failed to hash %s: %s", file_path, e)

        # Log duplicates found during preload
        duplicates = {h: paths for h, paths in hash_to_paths.items() if len(paths) > 1}
        if duplicates:
            logger.info(
                "Found %d duplicate groups (%d total duplicate files)",
                len(duplicates),
                sum(len(paths) - 1 for paths in duplicates.values()),
            )

        return hash_to_paths

    def invalidate(self, file_path: Path) -> None:
        """Remove a file from the cache.

        Args:
            file_path: Path to invalidate
        """
        path_str = str(file_path.resolve())
        self._cache.pop(path_str, None)

    def clear(self) -> None:
        """Clear the entire cache."""
        self._cache.clear()


@dataclass
class DuplicateDetector:
    """Detects binary duplicate .sto files using SHA-256 hashing.

    This class maintains an index of file hashes in the target directory
    and can efficiently check if a new file is a duplicate of an existing one.

    Attributes:
        hash_cache: FileHashCache instance for caching hashes
    """

    hash_cache: FileHashCache = field(default_factory=FileHashCache)
    _hash_index: dict[str, Path] = field(default_factory=dict, repr=False)
    _indexed_directory: Path | None = field(default=None, repr=False)

    def build_index(self, target_directory: Path) -> int:
        """Build/rebuild the hash index for a target directory.

        Pre-computes hashes for all .sto files in the target directory.
        This should be called before checking for duplicates.

        Args:
            target_directory: Directory to index

        Returns:
            Number of files indexed
        """
        self._hash_index.clear()
        self._indexed_directory = target_directory.resolve()

        if not target_directory.exists():
            logger.debug("Target directory does not exist: %s", target_directory)
            return 0

        hash_to_paths = self.hash_cache.preload_directory(target_directory)

        # Build index: for duplicate hashes, keep the first path found
        for file_hash, paths in hash_to_paths.items():
            # Sort paths for deterministic behavior
            sorted_paths = sorted(paths, key=lambda p: str(p))
            self._hash_index[file_hash] = sorted_paths[0]

        logger.info(
            "Built index with %d unique hashes in %s",
            len(self._hash_index),
            target_directory,
        )
        return len(self._hash_index)

    def find_duplicate(self, source_path: Path) -> DuplicateInfo | None:
        """Find if a file has a duplicate in the indexed directory.

        Args:
            source_path: Path to the file to check

        Returns:
            DuplicateInfo if a duplicate exists, None otherwise
        """
        try:
            file_hash = self.hash_cache.get_hash(source_path)
            file_size = source_path.stat().st_size
        except OSError as e:
            logger.warning("Could not hash file %s: %s", source_path, e)
            return None

        if file_hash in self._hash_index:
            existing_path = self._hash_index[file_hash]
            # Don't report as duplicate if it's the same file
            if source_path.resolve() == existing_path.resolve():
                return None

            logger.debug(
                "Found duplicate: %s matches %s",
                source_path.name,
                existing_path.name,
            )
            return DuplicateInfo(
                source_path=source_path,
                existing_path=existing_path,
                file_hash=file_hash,
                file_size=file_size,
            )

        return None

    def find_duplicate_by_hash(
        self,
        file_hash: str,
        file_size: int,  # noqa: ARG002 - kept for API consistency
        source_description: str = "",
    ) -> Path | None:
        """Find if a hash has a duplicate in the indexed directory.

        Useful when checking content before writing to disk.

        Args:
            file_hash: SHA-256 hash of the content
            file_size: Size of the content in bytes (reserved for future use)
            source_description: Description of the source for logging

        Returns:
            Path to existing duplicate if found, None otherwise
        """
        if file_hash in self._hash_index:
            existing_path = self._hash_index[file_hash]
            logger.debug(
                "Found duplicate by hash%s: matches %s",
                f" for {source_description}" if source_description else "",
                existing_path.name,
            )
            return existing_path
        return None

    def is_duplicate(self, source: Path, target: Path) -> bool:
        """Compare two specific files for binary equality.

        This is a direct comparison, not using the index.

        Args:
            source: First file to compare
            target: Second file to compare

        Returns:
            True if files have identical content, False otherwise
        """
        try:
            source_hash = self.hash_cache.get_hash(source)
            target_hash = self.hash_cache.get_hash(target)
            return source_hash == target_hash
        except OSError as e:
            logger.warning("Could not compare files: %s", e)
            return False

    def add_to_index(self, file_path: Path) -> str:
        """Add a newly written file to the index.

        Should be called after writing a new file to keep the index current.

        Args:
            file_path: Path to the file to add

        Returns:
            The SHA-256 hash of the file
        """
        file_hash = self.hash_cache.get_hash(file_path)
        resolved = file_path.resolve()

        # Only add if not already indexed
        if file_hash not in self._hash_index:
            self._hash_index[file_hash] = resolved
            logger.debug("Added to index: %s", file_path.name)

        return file_hash

    def remove_from_index(self, file_path: Path) -> None:
        """Remove a file from the index.

        Should be called when a file is deleted to keep the index current.

        Args:
            file_path: Path to the file to remove
        """
        resolved = file_path.resolve()
        # Find and remove the hash entry if it points to this file
        hash_to_remove = None
        for file_hash, indexed_path in self._hash_index.items():
            if indexed_path == resolved:
                hash_to_remove = file_hash
                break

        if hash_to_remove:
            del self._hash_index[hash_to_remove]
            self.hash_cache.invalidate(file_path)
            logger.debug("Removed from index: %s", file_path.name)

    @property
    def indexed_count(self) -> int:
        """Return the number of files currently indexed."""
        return len(self._hash_index)

    @property
    def indexed_directory(self) -> Path | None:
        """Return the currently indexed directory."""
        return self._indexed_directory
