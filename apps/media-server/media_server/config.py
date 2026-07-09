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
    # Main API base URL, used to validate Capture Studio ingest keys.
    api_url: str = Field("http://localhost:8000", alias="PENTECOSTAL_LIVE_API_URL")
    # RTMP base URL the capture gateway PUBLISHES to (the nginx-rtmp ingest).
    rtmp_publish_base_url: str = Field(
        "rtmp://localhost:1935/live",
        alias="PENTECOSTAL_LIVE_RTMP_PUBLISH_BASE_URL",
    )
    # Directory that HLS playlists/segments are written to (one subdir per stream).
    hls_root: str = Field("./data/hls", alias="PENTECOSTAL_LIVE_HLS_ROOT")
    # Directory broadcast recordings are archived to (one subdir per stream).
    recordings_root: str = Field("./data/recordings", alias="PENTECOSTAL_LIVE_RECORDINGS_ROOT")
    recording_enabled: bool = Field(True, alias="PENTECOSTAL_LIVE_RECORDING_ENABLED")


@lru_cache
def get_settings() -> Settings:
    return Settings()
