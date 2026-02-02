"""Track matching service for resolving provider track names to iRacing paths."""

import json
import logging
import re
from difflib import SequenceMatcher
from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TrackData(BaseModel):
    """Represents a track entry from tracks.json.

    Attributes:
        track_id: Unique identifier for the track
        track_name: Full track name (e.g., "Spa-Francorchamps")
        track_dirpath: iRacing directory path (e.g., "spa\\gp")
        config_name: Configuration name (e.g., "Grand Prix Pits")
        category: Track category (e.g., "road", "oval", "dirt_road")
        retired: Whether the track configuration is retired
        is_oval: Whether the track is an oval
        is_dirt: Whether the track is a dirt track
    """

    track_id: int
    track_name: str
    track_dirpath: str
    config_name: str = ""
    category: str = ""
    retired: bool = False
    is_oval: bool = False
    is_dirt: bool = False


class TrackMatchResult(BaseModel):
    """Result of a track matching operation.

    Attributes:
        track_dirpath: The matched iRacing directory path, or None if no match
        confidence: Confidence score from 0.0 to 1.0
        ambiguous: Whether multiple configs matched with similar confidence
        matched_track_name: The full track name that was matched
        matched_config: The configuration that was matched
    """

    track_dirpath: str | None = Field(default=None)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguous: bool = Field(default=False)
    matched_track_name: str | None = Field(default=None)
    matched_config: str | None = Field(default=None)


class TrackMatcher:
    """Service for matching provider track names to iRacing directory paths.

    Uses a tiered matching algorithm:
    1. Exact normalized match (highest confidence)
    2. Contains/substring match (high confidence)
    3. Fuzzy matching with SequenceMatcher (variable confidence)

    For tracks with multiple configurations, uses category hints to disambiguate
    (e.g., GT3 prefers road configs, NASCAR prefers oval configs).

    Also handles compound track names from providers like GoFast that combine
    track name and configuration (e.g., "DaytonaRoad" → Daytona + Road config).
    """

    # Default configs preferred when disambiguation fails
    DEFAULT_ROAD_CONFIGS = ["full", "gp", "grand prix"]
    DEFAULT_OVAL_CONFIGS = ["oval", "superspeedway"]

    # Category mapping from provider categories to track types
    ROAD_CATEGORIES = {"gt3", "gt4", "gte", "lmp2", "lmp3", "gtp", "imsa", "wec"}
    OVAL_CATEGORIES = {"nascar", "arca", "indycar oval", "cup", "xfinity", "truck"}

    # Config suffixes commonly appended to track names by providers
    # Maps suffix pattern to iRacing config name parts
    CONFIG_SUFFIXES = {
        "road": ["road"],
        "oval": ["oval"],
        "gp": ["gp", "grand prix"],
        "grandprix": ["gp", "grand prix"],
        "moto": ["moto", "motorcycle"],
        "full": ["full"],
        "fullcourse": ["full"],
        "short": ["short"],
        "outer": ["outer"],
        "inner": ["inner"],
        "north": ["north"],
        "south": ["south"],
        "east": ["east"],
        "west": ["west"],
        "combined": ["combined"],
        "national": ["national"],
        "club": ["club"],
        "endurance": ["endurance", "24h", "24hr"],
        "24h": ["24h", "24hr", "endurance"],
    }

    def __init__(self, tracks_data_path: Path | None = None) -> None:
        """Initialize the TrackMatcher.

        Args:
            tracks_data_path: Optional custom path to tracks.json.
                If None, uses the bundled package data.
        """
        self._tracks_data_path = tracks_data_path
        self._tracks: list[TrackData] = []
        self._name_index: dict[str, list[TrackData]] = {}
        self._loaded = False

    def load(self) -> None:
        """Load and index track data from JSON file.

        Raises:
            FileNotFoundError: If the tracks.json file cannot be found
            json.JSONDecodeError: If the JSON file is invalid
        """
        if self._loaded:
            return

        data_path = self._resolve_data_path()
        logger.info("Loading tracks data from %s", data_path)

        with open(data_path, encoding="utf-8") as f:
            raw_data = json.load(f)

        # Handle both direct list and wrapped format
        if isinstance(raw_data, dict) and "data" in raw_data:
            tracks_list = raw_data["data"]
        elif isinstance(raw_data, list):
            tracks_list = raw_data
        else:
            msg = f"Unexpected tracks.json format: {type(raw_data).__name__}"
            raise ValueError(msg)

        # Parse tracks
        for track_dict in tracks_list:
            try:
                track = TrackData(
                    track_id=track_dict.get("track_id", 0),
                    track_name=track_dict.get("track_name", ""),
                    track_dirpath=track_dict.get("track_dirpath", ""),
                    config_name=track_dict.get("config_name", ""),
                    category=track_dict.get("category", ""),
                    retired=track_dict.get("retired", False),
                    is_oval=track_dict.get("is_oval", False),
                    is_dirt=track_dict.get("is_dirt", False),
                )
                self._tracks.append(track)
            except Exception as e:
                logger.warning("Failed to parse track entry: %s", e)
                continue

        self._build_search_index()
        self._loaded = True
        logger.info("Loaded %d track configurations", len(self._tracks))

    def _resolve_data_path(self) -> Path:
        """Resolve the path to tracks.json.

        Returns:
            Path to the tracks.json file

        Raises:
            FileNotFoundError: If no tracks.json file can be found
        """
        if self._tracks_data_path:
            if self._tracks_data_path.exists():
                return self._tracks_data_path
            msg = f"Tracks data file not found: {self._tracks_data_path}"
            raise FileNotFoundError(msg)

        # Try to load from package data
        try:
            package_data = files("iracing_setup_downloader.data")
            tracks_file = package_data.joinpath("tracks.json")
            # Convert to Path for consistent handling
            return Path(str(tracks_file))
        except (ModuleNotFoundError, TypeError) as e:
            msg = f"Could not load bundled tracks.json: {e}"
            raise FileNotFoundError(msg) from e

    def _build_search_index(self) -> None:
        """Build O(1) lookup indices for fast searching."""
        self._name_index.clear()

        for track in self._tracks:
            # Index by normalized base track name (without config)
            base_name = self._extract_base_name(track.track_name)
            normalized = self._normalize_name(base_name)

            if normalized not in self._name_index:
                self._name_index[normalized] = []
            self._name_index[normalized].append(track)

            # Also index by full track name
            full_normalized = self._normalize_name(track.track_name)
            if full_normalized != normalized:
                if full_normalized not in self._name_index:
                    self._name_index[full_normalized] = []
                self._name_index[full_normalized].append(track)

            # Index by dirpath base name (e.g., "lemans" from "lemans\\full")
            # This catches common abbreviations used by providers
            dirpath = track.track_dirpath.replace("\\", "/")
            dirpath_parts = dirpath.split("/")
            if dirpath_parts:
                dirpath_base = dirpath_parts[0].lower()
                if dirpath_base and dirpath_base not in self._name_index:
                    self._name_index[dirpath_base] = []
                if dirpath_base and track not in self._name_index[dirpath_base]:
                    self._name_index[dirpath_base].append(track)

    def _normalize_name(self, name: str) -> str:
        """Normalize a track name for comparison.

        Removes special characters, normalizes whitespace, and converts to lowercase.

        Args:
            name: Track name to normalize

        Returns:
            Normalized track name
        """
        # Convert to lowercase
        normalized = name.lower()

        # Remove common prefixes like "[Retired]"
        normalized = re.sub(r"^\[.*?\]\s*", "", normalized)

        # Remove special characters except spaces
        normalized = re.sub(r"[^a-z0-9\s]", "", normalized)

        # Normalize whitespace
        normalized = " ".join(normalized.split())

        return normalized

    def _normalize_name_compact(self, name: str) -> str:
        """Normalize a track name to compact form (no spaces).

        Useful for matching names like "Le Mans" to "lemans".

        Args:
            name: Track name to normalize

        Returns:
            Normalized track name without spaces
        """
        normalized = self._normalize_name(name)
        return normalized.replace(" ", "")

    def _parse_compound_name(self, name: str) -> tuple[str, str | None]:
        """Parse a compound track name into base name and config hint.

        Handles provider naming conventions like "DaytonaRoad" → ("Daytona", "road")
        or "SpaGP" → ("Spa", "gp").

        Args:
            name: Compound track name (e.g., "DaytonaRoad", "AlgarveGP")

        Returns:
            Tuple of (base_track_name, config_hint) where config_hint may be None
        """
        # First normalize - remove special chars but keep as single word
        cleaned = re.sub(r"[^a-zA-Z0-9]", "", name).lower()

        # Try to find config suffix at the end
        for suffix, _ in sorted(
            self.CONFIG_SUFFIXES.items(), key=lambda x: len(x[0]), reverse=True
        ):
            if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
                # Re-add spaces using CamelCase detection on original
                base_spaced = self._add_spaces_to_name(name[: len(name) - len(suffix)])
                return (base_spaced, suffix)

        # No suffix found, try to split on common boundaries
        # Handle CamelCase like "LeMans" or "RoadAmerica"
        spaced = self._add_spaces_to_name(name)
        return (spaced, None)

    def _add_spaces_to_name(self, name: str) -> str:
        """Add spaces to a CamelCase name.

        Args:
            name: Name without spaces (e.g., "RoadAmerica")

        Returns:
            Name with spaces (e.g., "Road America")
        """
        if " " in name:
            return name

        # Add space before capital letters (but not consecutive ones like "GP")
        result = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)

        # Handle numbers following letters
        result = re.sub(r"(?<=[a-zA-Z])(?=\d)", " ", result)

        return result

    def _extract_base_name(self, track_name: str) -> str:
        """Extract the base track name without configuration suffix.

        Args:
            track_name: Full track name (e.g., "Spa-Francorchamps - Grand Prix")

        Returns:
            Base track name (e.g., "Spa-Francorchamps")
        """
        # Remove [Retired] prefix
        name = re.sub(r"^\[Retired\]\s*", "", track_name)

        # Split on " - " to separate track name from config
        if " - " in name:
            parts = name.split(" - ", 1)
            return parts[0].strip()

        return name.strip()

    def match(
        self, track_name: str, category_hint: str | None = None
    ) -> TrackMatchResult:
        """Match a provider track name to an iRacing directory path.

        Args:
            track_name: Track name from the provider (e.g., "Spa-Francorchamps")
            category_hint: Optional category hint for disambiguation (e.g., "GT3")

        Returns:
            TrackMatchResult with the matched path and confidence
        """
        if not self._loaded:
            logger.warning("TrackMatcher not loaded, call load() first")
            return TrackMatchResult()

        if not track_name:
            return TrackMatchResult()

        # First, try parsing as compound name (e.g., "DaytonaRoad" → "Daytona" + "road")
        base_name, config_hint = self._parse_compound_name(track_name)

        # Try matching with the original name first
        result = self._match_name(track_name, category_hint, config_hint)
        if result.track_dirpath:
            return result

        # If original failed and we extracted a different base name, try that
        if base_name.lower() != track_name.lower():
            result = self._match_name(base_name, category_hint, config_hint)
            if result.track_dirpath:
                return result

        logger.debug("No match found for track '%s'", track_name)
        return TrackMatchResult()

    def _match_name(
        self,
        track_name: str,
        category_hint: str | None,
        config_hint: str | None,
    ) -> TrackMatchResult:
        """Internal matching logic for a single track name.

        Args:
            track_name: Track name to match
            category_hint: Category hint (e.g., "GT3")
            config_hint: Config hint extracted from compound name (e.g., "road")

        Returns:
            TrackMatchResult with the matched path and confidence
        """
        normalized_query = self._normalize_name(track_name)
        compact_query = self._normalize_name_compact(track_name)

        # Tier 1: Exact normalized match (try both with and without spaces)
        if normalized_query in self._name_index:
            candidates = self._name_index[normalized_query]
            return self._select_best_config(
                candidates, category_hint, config_hint, confidence=1.0
            )

        if compact_query != normalized_query and compact_query in self._name_index:
            candidates = self._name_index[compact_query]
            return self._select_best_config(
                candidates, category_hint, config_hint, confidence=1.0
            )

        # Tier 2: Contains/substring match (try both forms)
        substring_matches: list[TrackData] = []
        for key, tracks in self._name_index.items():
            # Match with spaces
            if (
                normalized_query in key
                or key in normalized_query
                or compact_query in key
                or key in compact_query
            ):
                substring_matches.extend(tracks)

        if substring_matches:
            # Remove duplicates while preserving order
            seen_ids: set[int] = set()
            unique_matches: list[TrackData] = []
            for track in substring_matches:
                if track.track_id not in seen_ids:
                    seen_ids.add(track.track_id)
                    unique_matches.append(track)

            return self._select_best_config(
                unique_matches, category_hint, config_hint, confidence=0.8
            )

        # Tier 3: Fuzzy matching
        best_matches: list[tuple[float, TrackData]] = []
        for track in self._tracks:
            base_name = self._extract_base_name(track.track_name)
            normalized_track = self._normalize_name(base_name)
            compact_track = normalized_track.replace(" ", "")

            # Try matching with both forms and take the best score
            ratio1 = SequenceMatcher(None, normalized_query, normalized_track).ratio()
            ratio2 = SequenceMatcher(None, compact_query, compact_track).ratio()
            ratio = max(ratio1, ratio2)

            # Lower threshold to 0.5 to catch partial matches
            if ratio >= 0.5:
                best_matches.append((ratio, track))

        if best_matches:
            # Sort by ratio descending
            best_matches.sort(key=lambda x: x[0], reverse=True)

            # Get all matches with similar scores (within 0.1 of best)
            top_score = best_matches[0][0]
            similar_matches = [
                track for score, track in best_matches if score >= top_score - 0.1
            ]

            return self._select_best_config(
                similar_matches, category_hint, config_hint, confidence=top_score
            )

        return TrackMatchResult()

    def _select_best_config(
        self,
        candidates: list[TrackData],
        category_hint: str | None,
        config_hint: str | None,
        confidence: float,
    ) -> TrackMatchResult:
        """Select the best configuration from multiple candidates.

        Args:
            candidates: List of matching track configurations
            category_hint: Optional category hint for disambiguation (e.g., "GT3")
            config_hint: Optional config hint from compound name (e.g., "road", "gp")
            confidence: Base confidence score

        Returns:
            TrackMatchResult with the selected configuration
        """
        if not candidates:
            return TrackMatchResult()

        # Filter out retired configs if non-retired are available
        non_retired = [t for t in candidates if not t.retired]
        if non_retired:
            candidates = non_retired

        # If only one candidate, return it
        if len(candidates) == 1:
            track = candidates[0]
            return TrackMatchResult(
                track_dirpath=track.track_dirpath,
                confidence=confidence,
                ambiguous=False,
                matched_track_name=track.track_name,
                matched_config=track.config_name,
            )

        # Multiple candidates - use hints to disambiguate
        prefer_oval = self._should_prefer_oval(category_hint)

        # Get config keywords to match from config_hint
        config_keywords: list[str] = []
        if config_hint and config_hint in self.CONFIG_SUFFIXES:
            config_keywords = self.CONFIG_SUFFIXES[config_hint]

        # Score each candidate
        scored: list[tuple[float, TrackData]] = []
        for track in candidates:
            score = 0.0

            config_lower = track.config_name.lower()
            dirpath_lower = track.track_dirpath.lower()

            # Highest priority: config hint match (from compound name like "DaytonaRoad")
            if config_keywords:
                for keyword in config_keywords:
                    if keyword in config_lower or keyword in dirpath_lower:
                        score += 5.0
                        break

            # Prefer matching track type (road vs oval)
            if (prefer_oval and track.is_oval) or (
                not prefer_oval and not track.is_oval
            ):
                score += 2.0

            # Prefer default configs
            default_configs = (
                self.DEFAULT_OVAL_CONFIGS if prefer_oval else self.DEFAULT_ROAD_CONFIGS
            )
            for default in default_configs:
                if default in config_lower or default in dirpath_lower:
                    score += 1.0
                    break

            # Prefer non-dirt unless explicitly dirt category
            if not track.is_dirt:
                score += 0.5

            scored.append((score, track))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Check if top scores are similar (ambiguous)
        top_score = scored[0][0]
        similar_count = sum(1 for s, _ in scored if s >= top_score - 0.1)
        ambiguous = similar_count > 1

        best = scored[0][1]
        return TrackMatchResult(
            track_dirpath=best.track_dirpath,
            confidence=confidence * 0.9 if ambiguous else confidence,
            ambiguous=ambiguous,
            matched_track_name=best.track_name,
            matched_config=best.config_name,
        )

    def _should_prefer_oval(self, category_hint: str | None) -> bool:
        """Determine if oval configurations should be preferred.

        Args:
            category_hint: Category from the setup (e.g., "GT3", "NASCAR")

        Returns:
            True if oval configs should be preferred
        """
        if not category_hint:
            return False

        category_lower = category_hint.lower()

        # Check if it's an oval category
        for oval_cat in self.OVAL_CATEGORIES:
            if oval_cat in category_lower:
                return True

        # Check if it's explicitly a road category
        for road_cat in self.ROAD_CATEGORIES:
            if road_cat in category_lower:
                return False

        # Default to road
        return False
