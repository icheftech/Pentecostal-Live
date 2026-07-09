from pydantic import BaseModel, Field


class DestinationIn(BaseModel):
    platform: str = Field(min_length=2, max_length=80)
    # Optional: when omitted, the media-server resolves the standard base URL
    # for the platform from pentecostal_ffmpeg.PLATFORM_RTMP_URLS.
    rtmp_url: str | None = None
    stream_key: str = Field(min_length=1)


class RelayStartRequest(BaseModel):
    ingest_url: str = Field(min_length=1)
    destinations: list[DestinationIn] = Field(default_factory=list)
    hls: bool = True
    record: bool = True


class RelayStartResponse(BaseModel):
    stream_id: str
    status: str
    destinations: list[dict]
    hls: bool
    restarted: bool = False
    recording_file: str | None = None


class RecordingFile(BaseModel):
    filename: str
    size_bytes: int
    modified_at: str


class RelayStopResponse(BaseModel):
    stream_id: str
    status: str
    was_running: bool


class DestinationStats(BaseModel):
    platform: str
    status: str  # "connected" | "offline"


class StreamStats(BaseModel):
    """Contract consumed by the main API — keep this shape stable."""

    stream_id: str
    status: str  # "live" | "offline"
    bitrate_kbps: int
    uptime_seconds: int
    dropped_frames: int
    destinations: list[DestinationStats]
