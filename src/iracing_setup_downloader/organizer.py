"""Setup file organizer for reorganizing existing .sto files."""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iracing_setup_downloader.deduplication import DuplicateDetector
    from iracing_setup_downloader.track_matcher import TrackMatcher

logger = logging.getLogger(__name__)


@dataclass
class OrganizeAction:
    """Represents a file organization action.

    Attributes:
        source: Original file path
        destination: Target file path after organization
        track_name: Extracted or inferred track name
        car_folder: Car folder name
        track_dirpath: Matched iRacing track directory path
        confidence: Confidence of track match (0.0-1.0)
        skipped: Whether this file was skipped
        skip_reason: Reason for skipping if skipped
        error: Error message if action failed
        is_duplicate: Whether this file is a binary duplicate of an existing file
        duplicate_of: Path to the existing file if is_duplicate is True
        duplicate_deleted: Whether the duplicate source file was deleted
        companion_files_moved: Number of companion files moved/copied with this file
    """

    source: Path
    destination: Path | None = None
    track_name: str = ""
    car_folder: str = ""
    track_dirpath: str = ""
    confidence: float = 0.0
    skipped: bool = False
    skip_reason: str = ""
    error: str = ""
    is_duplicate: bool = False
    duplicate_of: Path | None = None
    duplicate_deleted: bool = False
    companion_files_moved: int = 0

    @property
    def will_move(self) -> bool:
        """Check if this action will result in a file move."""
        return (
            not self.skipped
            and self.destination is not None
            and self.source != self.destination
        )


@dataclass
class OrganizeResult:
    """Result of an organize operation.

    Attributes:
        total_files: Total number of .sto files found
        organized: Number of files successfully organized
        skipped: Number of files skipped
        failed: Number of files that failed to organize
        actions: List of all actions taken or planned
        duplicates_found: Number of duplicate files detected
        duplicates_deleted: Number of duplicate source files deleted
        bytes_saved: Total bytes saved by deleting duplicates
        companion_files_moved: Total number of companion files moved/copied
    """

    total_files: int = 0
    organized: int = 0
    skipped: int = 0
    failed: int = 0
    actions: list[OrganizeAction] = field(default_factory=list)
    duplicates_found: int = 0
    duplicates_deleted: int = 0
    bytes_saved: int = 0
    companion_files_moved: int = 0

    def __str__(self) -> str:
        """Return string representation of results."""
        base = (
            f"Total: {self.total_files}, Organized: {self.organized}, "
            f"Skipped: {self.skipped}, Failed: {self.failed}"
        )
        if self.duplicates_found > 0:
            base += f", Duplicates: {self.duplicates_found}"
        if self.companion_files_moved > 0:
            base += f", Companion files: {self.companion_files_moved}"
        return base


class SetupOrganizer:
    """Organizes existing setup files into iRacing's track folder structure.

    The organizer scans a directory for .sto files, extracts track information
    from filenames and folder paths, and reorganizes files into the correct
    iRacing folder structure using TrackMatcher.

    Attributes:
        track_matcher: TrackMatcher instance for resolving track paths
    """

    # GoFast filename pattern: GoFast_<series>_<season>_<track>_<setup_type>.sto
    # Note: series can contain spaces, so we match everything up to season pattern
    GOFAST_PATTERN = re.compile(
        r"^GoFast_(?P<series>.+?)_(?P<season>\d+S\d+W?\d*)_(?P<track>[^_]+)_(?P<type>[^_]+)\.sto$",
        re.IGNORECASE,
    )

    # Suspicious folder names that are likely container folders, not car folders
    SUSPICIOUS_FOLDERS = {
        "setups",
        "setup",
        "downloads",
        "download",
        "backup",
        "backups",
        "old",
        "new",
        "temp",
        "tmp",
    }

    # Alternative pattern with track in filename: <anything>_<track>_<type>.sto
    TRACK_PATTERN = re.compile(
        r"^.*?_(?P<track>[A-Za-z][A-Za-z0-9\-]+)_(?P<type>[^_]+)\.sto$",
        re.IGNORECASE,
    )

    # Common setup type suffixes
    SETUP_TYPES = {
        "race",
        "qualifying",
        "qual",
        "q",
        "practice",
        "wet",
        "swet",
        "er",
        "sr",
        "sq",
        "eq",
    }

    # Companion file extensions that should be moved/copied with .sto files
    # These are telemetry, lap data, and replay files associated with setups
    COMPANION_EXTENSIONS = {".ld", ".ldx", ".olap", ".blap", ".rpy"}

    def __init__(
        self,
        track_matcher: TrackMatcher,
        duplicate_detector: DuplicateDetector | None = None,
    ) -> None:
        """Initialize the organizer.

        Args:
            track_matcher: TrackMatcher instance for resolving track paths.
                Must be loaded before use.
            duplicate_detector: Optional DuplicateDetector for binary duplicate
                detection. If provided, duplicates will be detected and optionally
                deleted during organization.
        """
        self._track_matcher = track_matcher
        self._duplicate_detector = duplicate_detector

    def organize(
        self,
        source_path: Path,
        output_path: Path | None = None,
        dry_run: bool = False,
        copy: bool = False,
        category_hint: str | None = None,
        detect_duplicates: bool = True,
    ) -> OrganizeResult:
        """Organize setup files in a directory.

        Scans the source directory recursively for .sto files and organizes
        them into the proper iRacing folder structure.

        Args:
            source_path: Directory containing setup files to organize
            output_path: Optional output directory. If None, organizes in place.
            dry_run: If True, don't actually move/copy files, just report actions
            copy: If True, copy files instead of moving them
            category_hint: Optional category hint for track disambiguation (e.g., "GT3")
            detect_duplicates: If True and duplicate_detector is set, detect and
                handle binary duplicates (default: True)

        Returns:
            OrganizeResult with details of all actions taken

        Raises:
            FileNotFoundError: If source_path doesn't exist
            NotADirectoryError: If source_path is not a directory
        """
        if not source_path.exists():
            raise FileNotFoundError(f"Source path not found: {source_path}")

        if not source_path.is_dir():
            raise NotADirectoryError(f"Source path is not a directory: {source_path}")

        # Use source as output if not specified
        effective_output = output_path if output_path else source_path

        result = OrganizeResult()

        # Build duplicate index if detector is available
        if detect_duplicates and self._duplicate_detector:
            logger.info("Building duplicate detection index for %s", effective_output)
            self._duplicate_detector.build_index(effective_output)

        # Find all .sto files
        sto_files = list(source_path.rglob("*.sto"))
        result.total_files = len(sto_files)

        logger.info("Found %d .sto files in %s", len(sto_files), source_path)

        for sto_file in sto_files:
            action = self._process_file(
                sto_file,
                source_path,
                effective_output,
                category_hint,
                detect_duplicates=detect_duplicates,
            )
            result.actions.append(action)

            # Track duplicate statistics
            if action.is_duplicate:
                result.duplicates_found += 1

            if action.skipped:
                result.skipped += 1
                # Handle duplicate deletion for skipped files (when moving, not copying)
                if (
                    action.is_duplicate
                    and not dry_run
                    and not copy
                    and action.duplicate_of
                ):
                    try:
                        file_size = sto_file.stat().st_size
                        # Find and delete companion files first
                        companion_files = self._find_companion_files(sto_file)
                        for companion in companion_files:
                            try:
                                companion_size = companion.stat().st_size
                                companion.unlink()
                                result.bytes_saved += companion_size
                                logger.info(
                                    "Deleted duplicate companion: %s", companion.name
                                )
                            except OSError as e:
                                logger.warning(
                                    "Failed to delete companion %s: %s", companion, e
                                )

                        sto_file.unlink()
                        action.duplicate_deleted = True
                        result.duplicates_deleted += 1
                        result.bytes_saved += file_size
                        logger.info(
                            "Deleted duplicate: %s (identical to %s)",
                            sto_file,
                            action.duplicate_of,
                        )
                        # Remove deleted file from index to prevent stale matches
                        if self._duplicate_detector:
                            self._duplicate_detector.remove_from_index(sto_file)
                        # Clean up empty directories
                        self._cleanup_empty_dirs(sto_file.parent)
                    except OSError as e:
                        logger.warning("Failed to delete duplicate %s: %s", sto_file, e)
                continue

            if action.error:
                result.failed += 1
                continue

            # Execute the action unless dry run
            if not dry_run and action.will_move:
                try:
                    companion_count = self._execute_action(action, copy=copy)
                    action.companion_files_moved = companion_count
                    result.companion_files_moved += companion_count
                    result.organized += 1
                    # Add newly written file to index
                    if self._duplicate_detector and action.destination:
                        self._duplicate_detector.add_to_index(action.destination)
                except Exception as e:
                    action.error = str(e)
                    result.failed += 1
                    logger.error("Failed to organize %s: %s", sto_file, e)
            elif action.will_move:
                # In dry run, count potential companion files
                companion_files = self._find_companion_files(sto_file)
                action.companion_files_moved = len(companion_files)
                result.companion_files_moved += len(companion_files)
                result.organized += 1  # Count as would-be-organized in dry run

        return result

    def _process_file(
        self,
        file_path: Path,
        source_root: Path,
        output_root: Path,
        category_hint: str | None,
        detect_duplicates: bool = True,
    ) -> OrganizeAction:
        """Process a single .sto file and determine its organization.

        Args:
            file_path: Path to the .sto file
            source_root: Root of the source directory
            output_root: Root of the output directory
            category_hint: Optional category for disambiguation
            detect_duplicates: Whether to check for binary duplicates

        Returns:
            OrganizeAction describing what should happen to this file
        """
        action = OrganizeAction(source=file_path)

        # Extract car folder from path (first directory under source_root)
        try:
            relative = file_path.relative_to(source_root)
            parts = relative.parts
            if len(parts) >= 2:
                action.car_folder = parts[0]
                # Warn if car folder looks suspicious (likely a container folder)
                if action.car_folder.lower() in self.SUSPICIOUS_FOLDERS:
                    logger.warning(
                        "Detected '%s' as car folder for %s - this may be incorrect. "
                        "Expected iRacing car folder like 'dalloradw12' or 'ferrari296gt3'. "
                        "Try running organize on the parent directory.",
                        action.car_folder,
                        file_path.name,
                    )
            else:
                # File is directly in root, try to infer car from filename
                action.car_folder = ""
        except ValueError:
            # File not under source_root
            action.skipped = True
            action.skip_reason = "File not under source directory"
            return action

        # Try to extract track name from filename
        track_name = self._extract_track_from_filename(file_path.name)

        # If not found in filename, try from folder structure
        if not track_name and len(parts) >= 2:
            track_name = self._extract_track_from_path(parts)

        if not track_name:
            action.skipped = True
            action.skip_reason = "Could not determine track name"
            logger.debug("Could not extract track from %s", file_path)
            return action

        action.track_name = track_name

        # Match track to iRacing path
        match_result = self._track_matcher.match(
            track_name, category_hint=category_hint
        )

        if not match_result.track_dirpath:
            action.skipped = True
            action.skip_reason = f"Could not match track '{track_name}' to iRacing path"
            logger.debug("No match for track '%s' from %s", track_name, file_path)
            return action

        action.track_dirpath = match_result.track_dirpath
        action.confidence = match_result.confidence

        # Build destination path
        if not action.car_folder:
            # Try to use a default or skip
            action.skipped = True
            action.skip_reason = "Could not determine car folder"
            return action

        # Convert track_dirpath to OS-native path separators
        track_subdir = match_result.track_dirpath.replace("\\", "/")

        destination = output_root / action.car_folder / track_subdir / file_path.name
        action.destination = destination

        # Check if already in correct location
        if file_path == destination:
            action.skipped = True
            action.skip_reason = "Already in correct location"
            return action

        # Check if destination already exists
        if destination.exists() and destination != file_path:
            # Check if it's a binary duplicate of the existing file
            if (
                detect_duplicates
                and self._duplicate_detector
                and self._duplicate_detector.is_duplicate(file_path, destination)
            ):
                action.is_duplicate = True
                action.duplicate_of = destination
                action.skipped = True
                action.skip_reason = f"Binary duplicate of existing: {destination.name}"
                logger.debug(
                    "File %s is binary duplicate of %s",
                    file_path.name,
                    destination.name,
                )
                return action
            action.skipped = True
            action.skip_reason = f"Destination already exists: {destination}"
            return action

        # Check if file is a duplicate of another file elsewhere in target
        if detect_duplicates and self._duplicate_detector:
            dup_info = self._duplicate_detector.find_duplicate(file_path)
            if dup_info:
                action.is_duplicate = True
                action.duplicate_of = dup_info.existing_path
                action.skipped = True
                action.skip_reason = (
                    f"Binary duplicate of existing: {dup_info.existing_path.name}"
                )
                logger.debug(
                    "File %s is binary duplicate of %s",
                    file_path.name,
                    dup_info.existing_path.name,
                )
                return action

        return action

    def _extract_track_from_filename(self, filename: str) -> str:
        """Extract track name from filename.

        Tries multiple patterns to extract the track name.

        Args:
            filename: Name of the .sto file

        Returns:
            Extracted track name, or empty string if not found
        """
        # Try GoFast pattern first
        match = self.GOFAST_PATTERN.match(filename)
        if match:
            track = match.group("track")
            # Re-add spaces to track name (they were removed during naming)
            return self._add_spaces_to_track_name(track)

        # Try generic track pattern
        match = self.TRACK_PATTERN.match(filename)
        if match:
            track = match.group("track")
            setup_type = match.group("type").lower()
            # Verify the type looks like a setup type, not part of track name
            if setup_type in self.SETUP_TYPES or len(setup_type) <= 3:
                return self._add_spaces_to_track_name(track)

        # Try to find any recognizable track name in the filename
        # Remove extension and split on underscores
        stem = Path(filename).stem
        parts = stem.replace("-", "_").split("_")

        for part in parts:
            # Skip very short parts and known prefixes
            if len(part) < 3:
                continue
            if part.lower() in {"go", "fast", "gofast", "ir", "sto"}:
                continue
            # Skip season patterns like 26S1W8
            if re.match(r"^\d+S\d+", part, re.IGNORECASE):
                continue
            # Skip setup types
            if part.lower() in self.SETUP_TYPES:
                continue

            # This might be a track name - try to match it
            test_result = self._track_matcher.match(part)
            if test_result.track_dirpath and test_result.confidence >= 0.7:
                return part

        return ""

    def _extract_track_from_path(self, path_parts: tuple[str, ...]) -> str:
        """Extract track name from path components.

        Looks for track names in the folder structure between car and filename.

        Args:
            path_parts: Tuple of path components (car, ..., filename)

        Returns:
            Track name if found, empty string otherwise
        """
        # Skip car folder (first) and filename (last)
        if len(path_parts) <= 2:
            return ""

        middle_parts = path_parts[1:-1]

        # Try each middle part as a potential track name
        for part in middle_parts:
            # Clean up the part
            cleaned = part.replace("-", " ").replace("_", " ")

            # Try to match it
            result = self._track_matcher.match(cleaned)
            if result.track_dirpath and result.confidence >= 0.6:
                return cleaned

        # If no match, return the first middle part as-is
        # (it might be a track name we just can't match)
        return middle_parts[0] if middle_parts else ""

    def _add_spaces_to_track_name(self, track: str) -> str:
        """Add spaces to a track name that had them removed.

        Handles CamelCase and attempts to restore natural spacing.

        Args:
            track: Track name without spaces (e.g., "SpaFrancorchamps")

        Returns:
            Track name with spaces restored (e.g., "Spa Francorchamps")
        """
        # First try: just return as-is if it already has spaces
        if " " in track:
            return track

        # Add space before capital letters (but not consecutive ones)
        result = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", track)

        # Handle numbers following letters
        result = re.sub(r"(?<=[a-zA-Z])(?=\d)", " ", result)

        return result

    def _find_companion_files(self, sto_file: Path) -> list[Path]:
        """Find companion files for a .sto file.

        Companion files have the same base name but different extensions
        (e.g., .ld, .ldx, .olap, .blap, .rpy).

        Args:
            sto_file: Path to the .sto file

        Returns:
            List of companion file paths that exist
        """
        companions = []
        stem = sto_file.stem
        parent = sto_file.parent

        for ext in self.COMPANION_EXTENSIONS:
            companion = parent / f"{stem}{ext}"
            if companion.exists():
                companions.append(companion)

        return companions

    def _execute_action(self, action: OrganizeAction, copy: bool = False) -> int:
        """Execute a file organization action.

        Args:
            action: The action to execute
            copy: If True, copy instead of move

        Returns:
            Number of companion files moved/copied

        Raises:
            OSError: If the file operation fails
        """
        if not action.destination:
            return 0

        # Create destination directory
        action.destination.parent.mkdir(parents=True, exist_ok=True)

        # Find companion files before moving the main file
        companion_files = self._find_companion_files(action.source)

        if copy:
            shutil.copy2(action.source, action.destination)
            logger.info("Copied: %s -> %s", action.source, action.destination)
        else:
            shutil.move(str(action.source), str(action.destination))
            logger.info("Moved: %s -> %s", action.source, action.destination)

        # Move/copy companion files
        companion_count = 0
        for companion in companion_files:
            companion_dest = action.destination.parent / companion.name
            try:
                # Skip if companion already exists at destination
                if companion_dest.exists():
                    logger.warning(
                        "Skipping companion file %s: already exists at destination",
                        companion.name,
                    )
                    continue

                if copy:
                    shutil.copy2(companion, companion_dest)
                    logger.info(
                        "Copied companion: %s -> %s", companion.name, companion_dest
                    )
                else:
                    shutil.move(str(companion), str(companion_dest))
                    logger.info(
                        "Moved companion: %s -> %s", companion.name, companion_dest
                    )
                companion_count += 1
            except OSError as e:
                logger.warning("Failed to move companion file %s: %s", companion, e)

        if not copy:
            # Try to clean up empty directories
            self._cleanup_empty_dirs(action.source.parent)

        return companion_count

    def _cleanup_empty_dirs(self, directory: Path) -> None:
        """Remove empty directories up the tree.

        Args:
            directory: Starting directory to check
        """
        try:
            while directory.exists() and directory.is_dir():
                if any(directory.iterdir()):
                    break  # Not empty
                directory.rmdir()
                logger.debug("Removed empty directory: %s", directory)
                directory = directory.parent
        except OSError:
            pass  # Ignore errors during cleanup
