from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

VisionText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]


class ColorFinding(BaseModel):
    """A visible color and its optional six-digit RGB value."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: VisionText = Field(description="Common name of the visible color.")
    hex_code: HexColor | None = Field(
        default=None,
        description="Optional RGB hex value inferred from the image, including '#'.",
    )


class VisionSchema(BaseModel):
    """Structured, evidence-grounded observations from image analysis."""

    model_config = ConfigDict(extra="forbid", strict=True)

    confidence_level: float = Field(
        ge=0,
        le=100,
        description="Overall confidence in the extracted findings, from 0 to 100.",
    )
    items_found: list[VisionText] = Field(
        default_factory=list,
        max_length=100,
        description="Distinct visible objects or items, using short noun phrases.",
    )
    colors: list[ColorFinding] = Field(
        default_factory=list,
        max_length=50,
        description="Colors visibly present in the image.",
    )
    names: list[VisionText] = Field(
        default_factory=list,
        max_length=100,
        description="Names or named entities transcribed exactly as visible.",
    )
    dates: list[VisionText] = Field(
        default_factory=list,
        max_length=100,
        description="Dates transcribed exactly as visible, without guessing a format.",
    )
