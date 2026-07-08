from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Shared secret; the main API sends it in the X-Media-Server-Token header.
    media_server_token: str = Field(
        "change_me_media_server_token",
        alias="PENTECOSTAL_LIVE_MEDIA_SERVER_TOKEN",
    )
    ffmpeg_binary: str = Field("ffmpeg", alias="PENTECOSTAL_LIVE_FFMPEG_BINARY")
    # Directory that HLS playlists/segments are written to (one subdir per stream).
    hls_root: str = Field("./data/hls", alias="PENTECOSTAL_LIVE_HLS_ROOT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
