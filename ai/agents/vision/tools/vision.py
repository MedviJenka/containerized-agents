import io
import base64
from pathlib import Path
from typing import Optional, Union, Type, List, Any
from dataclasses import dataclass
from PIL import Image
from crewai import LLM
from crewai.tools import BaseTool
from pydantic import BaseModel, Field, field_validator
# from functions.log import Logger


# log = Logger(name="vision-tool")

MAX_IMAGE_RESOLUTION = 2048

LLMMessage = dict[str, Any]


# ------------------------------ #
#        Utility Functions       #
# ------------------------------ #

def is_base64(value: str) -> bool:
    """Return True if value is raw base64 or a data URI, not a file path."""
    return value.startswith("data:image/") or not Path(value).exists()


def resolve_path(path: str) -> str:
    """Resolve and validate file path."""
    resolved = Path(path).resolve()
    if not resolved.exists():
        # log.fire(f"Image file does not exist: {resolved}", level='debug')
        raise ValueError(f"Image file not found: {resolved}")
    return str(resolved)


def normalize_paths(value: Optional[Union[str, List[str]]]) -> Optional[List[str]]:
    """Normalize optional image paths/base64 values to list."""
    if value is None:
        return None
    paths = [value] if isinstance(value, str) else value
    for p in paths:
        if not is_base64(p):
            resolve_path(p)
    return paths


def _pil_to_jpeg_b64(img: "Image.Image") -> str:
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")
    if max(img.size) > MAX_IMAGE_RESOLUTION:
        img.thumbnail((MAX_IMAGE_RESOLUTION, MAX_IMAGE_RESOLUTION), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95, subsampling=0)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"


def encode_image(path_or_b64: str) -> str:
    """Encode image as base64 data URI. Accepts a file path, raw base64, or data URI."""
    if path_or_b64.startswith("data:image/"):
        raw = base64.b64decode(path_or_b64.split(",", 1)[1])
    elif is_base64(path_or_b64):
        raw = base64.b64decode(path_or_b64)
    else:
        try:
            img = Image.open(resolve_path(path_or_b64))
            return _pil_to_jpeg_b64(img)
        except Exception as e:
            raise ValueError(f"Cannot open image '{path_or_b64}': {e}") from e

    try:
        img = Image.open(io.BytesIO(raw))
        return _pil_to_jpeg_b64(img)
    except Exception as e:
        raise ValueError(f"Failed to process image data: {e}") from e


# ------------------------------ #
#         Pydantic Schema        #
# ------------------------------ #

class ImagePromptSchema(BaseModel):

    image_path:        str                        = Field(...,          description="Primary image path")
    sample_image: Optional[Union[str, List[str]]] = Field(default=None, description="Optional comparison image path(s)")
    prompt:       str                             = Field(...,          description="Prompt describing what to analyze in the image")

    @classmethod
    @field_validator("image_path")
    def validate_image(cls, v: str) -> str:
        return v if is_base64(v) else resolve_path(v)

    @classmethod
    @field_validator("sample_image")
    def validate_sample_images(cls, v):
        return normalize_paths(v)

    def get_all_images(self) -> List[str]:
        """Return all image paths used in the request."""
        images = [self.image_path]

        if self.sample_image:
            images.extend(self.sample_image)

        # log.fire(f"Vision images used: {images}", level='debug')

        return images


# ------------------------------ #
#          Tool Runtime          #
# ------------------------------ #

@dataclass
class VisionMessageBuilder:

    schema: ImagePromptSchema

    def build(self) -> List[LLMMessage]:
        images = [
            {
                "type": "image_url",
                "image_url": {"url": encode_image(path)},
            }
            for path in self.schema.get_all_images()
        ]

        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": self.schema.prompt},
                    *images
                ],
            }
        ]


# ------------------------------ #
#        Vision Tool Class       #
# ------------------------------ #

class VisionTool(BaseTool):

    name: str = "Bini Vision Tool"
    description: str = "Analyzes one or more images using a vision-capable LLM"
    args_schema: Type[BaseModel] = ImagePromptSchema

    def __init__(self, llm: LLM) -> None:
        super().__init__()

        if llm is None:
            raise ValueError("BiniVisionTool requires a valid LLM instance")

        self._llm = llm

    @staticmethod
    def _build_messages(schema: ImagePromptSchema) -> List[LLMMessage]:
        """Construct messages for the vision model."""
        builder = VisionMessageBuilder(schema=schema)
        return builder.build()

    def _run(self, **kwargs: Any) -> str:
        schema = ImagePromptSchema(**kwargs)
        messages = self._build_messages(schema)
        return self._llm.call(messages=messages)
