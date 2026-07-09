# Connecting a Camera

Pentecostal Live has its own capture layer — no OBS or third-party encoder is
required. Any camera the operating system can see becomes a broadcast source
through the dashboard's **Camera** panel (the Capture Studio):

- **Webcams** — USB cameras, built-in laptop cameras.
- **HDMI cameras** — through an HDMI→USB capture device (Elgato Cam Link,
  generic UVC capture sticks). The OS presents these as cameras.
- **SDI cameras** — through an SDI→USB capture device (Magewell USB Capture
  SDI, Blackmagic UltraStudio Recorder in webcam mode). Same principle.

```
camera (webcam / HDMI→USB / SDI→USB)
   → dashboard Capture Studio (preview + encode in the browser)
   → media-server capture gateway (WebSocket → ffmpeg → H.264/AAC)
   → nginx-rtmp ingest
   → relay fan-out: YouTube / Facebook / TikTok / Instagram + website HLS
```

## Run the full stack

```bash
cp .env.example .env
docker compose -f infra/docker/docker-compose.yml up --build
```

That starts PostgreSQL, the API (:8000), the media-server (:8001), the
nginx-rtmp ingest (:1935, HLS on :8080), and the dashboard (:3000).

## Go live from the Studio

1. Plug the camera (or capture device) into the machine running the browser.
2. Open the dashboard at `http://localhost:3000`, sign in, and add your
   platform stream keys once under **Platform keys**.
3. Create a stream under **Streams** and press **Start**. This arms the
   pipeline and issues a fresh ingest key for this service.
4. In the **Studio** panel, build your production:
   - **Add camera** for each camera (your HDMI/SDI capture devices appear in
     the device list) and **Share screen** for slides, lyrics, or a class
     presentation.
   - Give each scene (main / sermon / worship / altar) a layout: full frame,
     side by side, or picture in picture, and choose which source plays each
     role. Layouts are remembered per scene.
5. Optional polish, all built in — no external plugins:
   - **Audio plugins**: 3-band EQ, compressor, and de-esser applied live to
     the microphone.
   - **Video plugins**: per-source brightness/contrast/saturation, and
     server-side image stabilization (ffmpeg deshake, applies at Go live).
6. Press **Go live**. The ON AIR badge confirms frames are flowing; switching
   the stream's scene buttons cuts the program between your layouts live —
   camera for the sermon, slides+teacher for a class, side-by-side for
   announcements. The **Live monitor** shows bitrate, uptime, dropped frames,
   and per-platform status.
7. When the service ends: **Stop broadcast**, then **Stop** the stream.

The website player can embed the HLS output at
`http://<host>:8080/hls/<stream_id>/index.m3u8`.

## Dedicated hardware encoders (optional)

A rack encoder (Teradek, LiveU, ATEM) can publish straight to the ingest
instead of using the Capture Studio. Expand *"Using a dedicated hardware
encoder instead?"* in the Camera panel and copy the **Server** and **Stream
key** into the encoder. The key is single-service: it changes on every stream
start, and the ingest rejects publishes with a stale or unknown key.

If the encoder is on another machine, set the public ingest address in `.env`
to the host's LAN IP before starting the stack:

```env
PENTECOSTAL_LIVE_RTMP_INGEST_BASE_URL=rtmp://192.168.1.50:1935/live
```

## Known limits

- PCIe capture cards that do not expose a webcam device (e.g. Blackmagic
  DeckLink in native mode) are not visible to browsers; they need the future
  native capture agent, or an SDI→USB converter in the meantime.
- The Capture Studio encodes in the browser (then the media-server transcodes
  to H.264). A recent Chrome/Edge on reasonably modern hardware handles
  1080p comfortably; close other heavy tabs on the broadcast machine.
- Keep the broadcast browser tab in the foreground or in its own window —
  aggressive tab throttling can starve the encoder.
