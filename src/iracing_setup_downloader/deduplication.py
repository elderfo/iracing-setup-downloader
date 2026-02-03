"""Binary duplicate detection for .sto setup files using SHA-256 hashing."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

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


@dataclass
class ExtractResult:
    """Result of a setup extraction operation.

    Contains both the successfully extracted files and information about
    any duplicates that were skipped during extraction.

    Attributes:
        extracted_files: List of paths to successfully extracted .sto files
        duplicates: List of DuplicateInfo for files skipped as duplicates
    """

    extracted_files: list[Path] = field(default_factory=list)
    duplicates: list[DuplicateInfo] = field(default_factory=list)

    @property
    def total_bytes_saved(self) -> int:
        """Calculate total bytes saved by skipping duplicates."""
        return sum(d.file_size for d in self.duplicates)


class FileHashCache:
    """Cache for SHA-256 file hashes with mtime/size validation and persistence.

    This cache stores file hashes and validates them based on file
    modification time and size to avoid expensive re-hashing of unchanged files.
    The cache can be persisted to disk to survive across sessions.

    Attributes:
        BUFFER_SIZE: Size of read buffer for hashing large files (64KB)
        CACHE_VERSION: Version of the cache file format for compatibility
        DEFAULT_CACHE_PATH: Default path for the cache file
    """

    BUFFER_SIZE = 65536  # 64KB read buffer
    CACHE_VERSION = 1
    DEFAULT_CACHE_PATH = Path.home() / ".iracing-setup-downloader" / "hash_cache.json"

    def __init__(
        self,
        cache_file: Path | None = None,
        auto_save: bool = False,
    ) -> None:
        """Initialize the hash cache.

        Args:
            cache_file: Path to the cache file. Defaults to
                ~/.iracing-setup-downloader/hash_cache.json
            auto_save: If True, automatically save after modifications
        """
        self._cache_file = (
            cache_file if cache_file is not None else self.DEFAULT_CACHE_PATH
        )
        self._auto_save = auto_save
        # Cache format: {path_str: (hash, mtime_ns, size)}
        self._cache: dict[str, tuple[str, int, int]] = {}
        self._loaded = False
        self._modified = False

    @property
    def cache_file(self) -> Path:
        """Get the path to the cache file.

        Returns:
            Path to the cache file
        """
        return self._cache_file

    @property
    def is_loaded(self) -> bool:
        """Check if the cache has been loaded from disk.

        Returns:
            True if load() has been called, False otherwise
        """
        return self._loaded

    def load(self) -> None:
        """Load cache from disk.

        Creates an empty cache if the file doesn't exist.
        Skips entries with invalid data without failing the entire load.

        Raises:
            json.JSONDecodeError: If the cache file contains invalid JSON
            OSError: If there are file system errors reading the file
        """
        try:
            if self._cache_file.exists():
                logger.info("Loading hash cache from %s", self._cache_file)
                data = json.loads(self._cache_file.read_text(encoding="utf-8"))

                # Check version for compatibility
                version = data.get("version", 1)
                if version > self.CACHE_VERSION:
                    logger.warning(
                        "Cache file version %d is newer than supported version %d, "
                        "starting with empty cache",
                        version,
                        self.CACHE_VERSION,
                    )
                    self._cache = {}
                    self._loaded = True
                    return

                # Load entries, skipping invalid ones
                loaded_count = 0
                skipped_count = 0
                for path_str, entry in data.items():
                    if path_str == "version":
                        continue
                    try:
                        # Validate entry structure
                        if not isinstance(entry, dict):
                            skipped_count += 1
                            continue
                        file_hash = entry.get("hash")
                        mtime_ns = entry.get("mtime_ns")
                        size = entry.get("size")

                        if not all(
                            [
                                isinstance(file_hash, str),
                                isinstance(mtime_ns, int),
                                isinstance(size, int),
                            ]
                        ):
                            skipped_count += 1
                            continue

                        self._cache[path_str] = (file_hash, mtime_ns, size)
                        loaded_count += 1
                    except (KeyError, TypeError, ValueError):
                        logger.debug("Skipping invalid cache entry: %s", path_str)
                        skipped_count += 1
                        continue

                logger.info(
                    "Loaded %d cache entries%s",
                    loaded_count,
                    f" (skipped {skipped_count} invalid)" if skipped_count else "",
                )
            else:
                logger.info("Hash cache file doesn't exist, starting with empty cache")
                self._cache = {}

            self._loaded = True
            self._modified = False

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in cache file %s: %s", self._cache_file, e)
            raise
        except OSError as e:
            logger.error("Error reading cache file %s: %s", self._cache_file, e)
            raise

    def save(self) -> None:
        """Save cache to disk.

        Creates parent directories if they don't exist.
        Only saves if cache has been loaded and modified.

        Raises:
            OSError: If there are file system errors writing the file
        """
        if not self._loaded:
            logger.warning("Attempted to save unloaded cache, skipping")
            return

        if not self._modified:
            logger.debug("Cache not modified, skipping save")
            return

        try:
            # Create parent directory if it doesn't exist
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)

            # Build serializable structure
            serializable: dict[str, Any] = {"version": self.CACHE_VERSION}
            for path_str, (file_hash, mtime_ns, size) in self._cache.items():
                serializable[path_str] = {
                    "hash": file_hash,
                    "mtime_ns": mtime_ns,
                    "size": size,
                }

            # Write with pretty formatting
            self._cache_file.write_text(
                json.dumps(serializable, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self._modified = False
            logger.info(
                "Saved %d cache entries to %s", len(self._cache), self._cache_file
            )

        except OSError as e:
            logger.error("Error writing cache file %s: %s", self._cache_file, e)
            raise

    def cleanup_stale(self) -> int:
        """Remove entries for files that no longer exist.

        Returns:
            Number of stale entries removed
        """
        stale_paths = []
        for path_str in self._cache:
            if not Path(path_str).exists():
                stale_paths.append(path_str)

        for path_str in stale_paths:
            del self._cache[path_str]

        if stale_paths:
            self._modified = True
            logger.info("Removed %d stale cache entries", len(stale_paths))

        return len(stale_paths)

    def __enter__(self) -> FileHashCache:
        """Enter context manager, loading cache.

        Returns:
            Self for use in with statement
        """
        self.load()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager, saving cache.

        Args:
            exc_type: Exception type if an error occurred
            exc_val: Exception value if an error occurred
            exc_tb: Exception traceback if an error occurred
        """
        if exc_type is None:
            # Only save if no exception occurred
            self.save()

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
        self._modified = True
        logger.debug("Computed hash for %s: %s", file_path.name, file_hash[:16])

        # Auto-save if enabled
        if self._auto_save and self._loaded:
            self.save()

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
        self,
        directory: Path,
        pattern: str = "*.sto",
        show_progress: bool = True,
    ) -> dict[str, list[Path]]:
        """Pre-hash all matching files in a directory.

        Builds a mapping from hash to list of file paths, useful for
        detecting which files are duplicates of each other.

        Args:
            directory: Directory to scan
            pattern: Glob pattern for files to hash (default: "*.sto")
            show_progress: Whether to show a progress bar (default: True)

        Returns:
            Dictionary mapping hash to list of file paths with that hash
        """
        hash_to_paths: dict[str, list[Path]] = {}

        if not directory.exists():
            logger.debug("Directory does not exist for preload: %s", directory)
            return hash_to_paths

        files = list(directory.rglob(pattern))
        total_files = len(files)
        logger.info("Pre-hashing %d files in %s", total_files, directory)

        if total_files == 0:
            return hash_to_paths

        if show_progress and total_files > 0:
            hash_to_paths = self._preload_with_progress(files)
        else:
            hash_to_paths = self._preload_without_progress(files)

        # Log duplicates found during preload
        duplicates = {h: paths for h, paths in hash_to_paths.items() if len(paths) > 1}
        if duplicates:
            logger.info(
                "Found %d duplicate groups (%d total duplicate files)",
                len(duplicates),
                sum(len(paths) - 1 for paths in duplicates.values()),
            )

        return hash_to_paths

    def _preload_with_progress(self, files: list[Path]) -> dict[str, list[Path]]:
        """Pre-hash files with a progress bar.

        Args:
            files: List of files to hash

        Returns:
            Dictionary mapping hash to list of file paths
        """
        hash_to_paths: dict[str, list[Path]] = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            transient=False,
        ) as progress:
            task_id = progress.add_task("Building file index", total=len(files))

            for file_path in files:
                try:
                    file_hash = self.get_hash(file_path)
                    if file_hash not in hash_to_paths:
                        hash_to_paths[file_hash] = []
                    hash_to_paths[file_hash].append(file_path)
                except OSError as e:
                    logger.warning("Failed to hash %s: %s", file_path, e)
                finally:
                    progress.update(task_id, advance=1)

        return hash_to_paths

    def _preload_without_progress(self, files: list[Path]) -> dict[str, list[Path]]:
        """Pre-hash files without a progress bar.

        Args:
            files: List of files to hash

        Returns:
            Dictionary mapping hash to list of file paths
        """
        hash_to_paths: dict[str, list[Path]] = {}

        for file_path in files:
            try:
                file_hash = self.get_hash(file_path)
                if file_hash not in hash_to_paths:
                    hash_to_paths[file_hash] = []
                hash_to_paths[file_hash].append(file_path)
            except OSError as e:
                logger.warning("Failed to hash %s: %s", file_path, e)

        return hash_to_paths

    def invalidate(self, file_path: Path) -> None:
        """Remove a file from the cache.

        Args:
            file_path: Path to invalidate
        """
        path_str = str(file_path.resolve())
        if path_str in self._cache:
            del self._cache[path_str]
            self._modified = True

    def clear(self) -> None:
        """Clear the entire cache."""
        if self._cache:
            self._modified = True
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

    def build_index(self, target_directory: Path, show_progress: bool = True) -> int:
        """Build/rebuild the hash index for a target directory.

        Pre-computes hashes for all .sto files in the target directory.
        This should be called before checking for duplicates.

        Args:
            target_directory: Directory to index
            show_progress: Whether to show a progress bar (default: True)

        Returns:
            Number of files indexed
        """
        self._hash_index.clear()
        self._indexed_directory = target_directory.resolve()

        if not target_directory.exists():
            logger.debug("Target directory does not exist: %s", target_directory)
            return 0

        hash_to_paths = self.hash_cache.preload_directory(
            target_directory, show_progress=show_progress
        )

        # Build index: for duplicate hashes, keep the first path found
        for file_hash, paths in hash_to_paths.items():
            # Sort paths for deterministic behavior
            sorted_paths = sorted(paths, key=str)
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
