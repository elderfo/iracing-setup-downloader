"""Data models for iRacing Setup Downloader."""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class Setup(BaseModel):
    """Represents an iRacing setup file."""

    id: str = Field(..., description="Unique identifier for the setup")
    filename: str = Field(..., description="Setup filename")
    car: str = Field(..., description="Car name/ID")
    track: str = Field(..., description="Track name/ID")
    provider: str = Field(..., description="Provider name")
    created_at: datetime | None = Field(
        default=None, description="When the setup was created"
    )
    updated_at: datetime | None = Field(
        default=None, description="When the setup was last updated"
    )
    metadata: dict = Field(default_factory=dict, description="Additional metadata")

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.car}/{self.track}/{self.filename}"


class SetupRecord(BaseModel):
    """Represents a setup record from GoFast API.

    Attributes:
        id: Unique identifier for the setup record
        download_name: Full download name (format: "IR - V1 - <Car Name> - <Track Name>")
        download_url: URL to download the setup file
        creation_date: When the setup was created
        updated_date: When the setup was last updated
        ver: Season version (e.g., "26 S1 W8")
        setup_ver: Setup version identifier
        changelog: Description of changes
        cat: Category (e.g., "GT3")
        series: Series name (e.g., "IMSA")
    """

    id: int = Field(..., description="Unique identifier for the setup record")
    download_name: str = Field(
        ..., description="Full download name with car and track info"
    )
    download_url: str = Field(..., description="URL to download the setup file")
    creation_date: datetime = Field(..., description="When the setup was created")
    updated_date: datetime = Field(..., description="When the setup was last updated")
    ver: str = Field(..., description="Season version (e.g., '26 S1 W8')")
    setup_ver: str = Field(..., description="Setup version identifier")
    changelog: str = Field(..., description="Description of changes")
    cat: str = Field(..., description="Category (e.g., 'GT3')")
    series: str = Field(..., description="Series name (e.g., 'IMSA')")

    @field_validator("download_name")
    @classmethod
    def validate_download_name(cls, v: str) -> str:
        """Validate download_name format.

        Args:
            v: The download_name value to validate

        Returns:
            The validated download_name

        Raises:
            ValueError: If download_name format is invalid
        """
        if not v.strip():
            msg = "download_name cannot be empty"
            raise ValueError(msg)
        return v

    @property
    def car(self) -> str:
        """Extract car name from download_name.

        Parses the download_name format: "IR - V1 - <Car Name> - <Track Name>"
        and extracts the car name component.

        Returns:
            The car name, or empty string if parsing fails
        """
        # Pattern: "IR - V1 - <Car Name> - <Track Name>"
        # We want to extract <Car Name>
        # Use \s+ (not \s*) to require spaces around separator dashes,
        # so hyphens within names (e.g., "MX-5") are not treated as separators.
        pattern = r"^IR\s+-\s+V\d+\s+-\s+(.+?)\s+-\s+(.+)$"
        match = re.match(pattern, self.download_name.strip())
        if match:
            return match.group(1).strip()

        # Fallback: try splitting on " - " first, then bare "-"
        parts = [p.strip() for p in self.download_name.split(" - ")]
        if len(parts) >= 4:
            return parts[2]
        parts = [p.strip() for p in self.download_name.split("-")]
        if len(parts) >= 4:
            return parts[2]

        # If all parsing fails, return empty string
        return ""

    @property
    def track(self) -> str:
        """Extract track name from download_name.

        Parses the download_name format: "IR - V1 - <Car Name> - <Track Name>"
        and extracts the track name component.

        Returns:
            The track name, or empty string if parsing fails
        """
        # Pattern: "IR - V1 - <Car Name> - <Track Name>"
        # We want to extract <Track Name>
        # Use \s+ (not \s*) to require spaces around separator dashes,
        # so hyphens within names (e.g., "Spa-Francorchamps") are not treated as separators.
        pattern = r"^IR\s+-\s+V\d+\s+-\s+(.+?)\s+-\s+(.+)$"
        match = re.match(pattern, self.download_name.strip())
        if match:
            return match.group(2).strip()

        # Fallback: try splitting on " - " first, then bare "-"
        parts = [p.strip() for p in self.download_name.split(" - ")]
        if len(parts) >= 4:
            return " - ".join(parts[3:])
        parts = [p.strip() for p in self.download_name.split("-")]
        if len(parts) >= 4:
            return "-".join(parts[3:])

        # If all parsing fails, return empty string
        return ""

    @property
    def season(self) -> str:
        """Extract season identifier from ver field.

        Converts version format (e.g., "26 S1 W8") to season format (e.g., "26S1W8")
        by removing all spaces.

        Returns:
            The season identifier with spaces removed
        """
        return self.ver.replace(" ", "")


class CDASetupInfo(BaseModel):
    """CDA-specific setup metadata.

    This model holds the structured data from CDA's catalog API that is
    needed to identify and download setups.

    Attributes:
        series_id: Numeric series identifier (e.g., 160 for IMSA)
        series_name: Human-readable series name (e.g., "25S4 IMSA Racing Series")
        bundle_id: Bundle identifier for the setup package
        week_number: Race week number (1-indexed)
        car_slug: URL-safe car identifier (e.g., "porsche-911-gt3-r-992")
        track_slug: URL-safe track identifier (e.g., "watkins-glen-international")
        track_name: Human-readable track name (e.g., "Watkins Glen International")
        laptime: Optional laptime info (e.g., "Dry: 1:49.884")
    """

    series_id: int = Field(..., description="Numeric series identifier")
    series_name: str = Field(..., description="Human-readable series name")
    bundle_id: int = Field(..., description="Bundle identifier for the setup package")
    week_number: int = Field(..., ge=1, description="Race week number (1-indexed)")
    car_slug: str = Field(..., description="URL-safe car identifier")
    track_slug: str = Field(..., description="URL-safe track identifier")
    track_name: str = Field(..., description="Human-readable track name")
    laptime: str | None = Field(default=None, description="Optional laptime info")

    @property
    def unique_id(self) -> str:
        """Generate a unique identifier for state tracking.

        Returns:
            Compound key in format {series_id}_{bundle_id}_{week_number}
        """
        return f"{self.series_id}_{self.bundle_id}_{self.week_number}"


class TracKTitanSetupInfo(BaseModel):
    """Track Titan-specific setup metadata.

    This model holds the structured data from Track Titan's API that is
    needed to identify and download setups.

    Attributes:
        setup_uuid: The Track Titan UUID for this setup
        car_id: Track Titan car identifier (e.g., "mx-5_cup")
        track_id: Track Titan track identifier (e.g., "bathurst")
        car_name: Human-readable car name
        track_name: Human-readable track name
        car_shorthand: iRacing car folder names (e.g., "mx5 mx52016")
        series_name: Series name (e.g., "Production Car Challenge")
        driver_name: Setup creator driver name
        season: Season number string (e.g., "1")
        week: Week number string (e.g., "8")
        year: Year number (e.g., 2026)
        has_wet_setup: Whether the setup includes wet variants
        is_bundle: Whether this is a bundle of multiple setups
    """

    setup_uuid: str = Field(..., description="Track Titan UUID for this setup")
    car_id: str = Field(..., description="Track Titan car identifier")
    track_id: str = Field(..., description="Track Titan track identifier")
    car_name: str = Field(..., description="Human-readable car name")
    track_name: str = Field(..., description="Human-readable track name")
    car_shorthand: str = Field(default="", description="iRacing car folder names")
    series_name: str = Field(default="", description="Series name")
    driver_name: str = Field(default="", description="Setup creator driver name")
    season: int | str | None = Field(default=None, description="Season number")
    week: int | str | None = Field(default=None, description="Week number")
    year: int | str | None = Field(default=None, description="Year")
    has_wet_setup: bool = Field(default=False, description="Has wet setup variants")
    is_bundle: bool = Field(default=False, description="Is a bundle")

    @property
    def unique_id(self) -> str:
        """Generate a unique identifier for state tracking.

        Returns:
            Compound key based on setup UUID
        """
        return self.setup_uuid
