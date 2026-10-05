from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class __Config(BaseSettings):

    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().with_name(".env"), extra="allow")

    LOGFIRE_WRITE_TOKEN: str = Field(...)
    OPENAI_API_KEY:      str = Field(...)
    OPENAI_MODEL:        str = Field(...)
    API_VERSION:         str = Field(...)


Config = __Config()
