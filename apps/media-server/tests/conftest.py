import os
import sys
from pathlib import Path

# Environment must be set before media_server.config is imported anywhere.
os.environ.setdefault("PENTECOSTAL_LIVE_MEDIA_SERVER_TOKEN", "test-media-token")
os.environ.setdefault(
    "PENTECOSTAL_LIVE_HLS_ROOT",
    str(Path(__file__).resolve().parent / ".hls-test-output"),
)

# Allow running pytest from apps/media-server without installing the packages.
_REPO_ROOT = Path(__file__).resolve().parents[3]
for path in (
    str(Path(__file__).resolve().parents[1]),  # apps/media-server
    str(_REPO_ROOT / "services" / "ffmpeg"),
):
    if path not in sys.path:
        sys.path.insert(0, path)
