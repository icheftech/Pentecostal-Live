# pentecostal-ffmpeg

Pure-function FFmpeg command builder for the Pentecostal Live media pipeline.

- `pentecostal_ffmpeg.build_relay_command(ingest_url, destinations, hls=None, ffmpeg_binary="ffmpeg")`
  returns the argv list for a single FFmpeg process that stream-copies the
  ingest and fans it out via the `tee` muxer to every platform RTMP URL plus
  an optional HLS output. Each RTMP slave uses `onfail=ignore` so one platform
  failing does not kill the others.
- `pentecostal_ffmpeg.PLATFORM_RTMP_URLS` — canonical RTMP base URLs per
  platform (mirrors `packages/config/src/index.ts`).

No subprocess handling here; the media-server (`apps/media-server`) owns
process lifecycle and installs this package (`pip install ./services/ffmpeg`).

Test without ffmpeg installed:

```bash
pip install -e services/ffmpeg pytest
pytest services/ffmpeg/tests
```
