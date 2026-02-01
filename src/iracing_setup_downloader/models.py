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
        pattern = r"^IR\s*-\s*V\d+\s*-\s*(.+?)\s*-\s*(.+)$"
        match = re.match(pattern, self.download_name.strip())
        if match:
            return match.group(1).strip()

        # Fallback: try simpler parsing if format is different
        parts = [p.strip() for p in self.download_name.split("-")]
        if len(parts) >= 4:
            # Remove "IR" and "V1" (or similar version), get the car name
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
        pattern = r"^IR\s*-\s*V\d+\s*-\s*(.+?)\s*-\s*(.+)$"
        match = re.match(pattern, self.download_name.strip())
        if match:
            return match.group(2).strip()

        # Fallback: try simpler parsing if format is different
        parts = [p.strip() for p in self.download_name.split("-")]
        if len(parts) >= 4:
            # Get everything after the car name
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
