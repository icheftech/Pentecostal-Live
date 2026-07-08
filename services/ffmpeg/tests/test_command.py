import pytest

from pentecostal_ffmpeg import (
    PLATFORM_RTMP_URLS,
    Destination,
    HlsSettings,
    build_destination_url,
    build_relay_command,
    resolve_rtmp_url,
)
from pentecostal_ffmpeg.command import _tee_escape


INGEST = "rtmp://localhost:1935/live/abc123"


def tee_arg(argv: list[str]) -> str:
    """The tee output spec is always the final argv element."""
    return argv[-1]


def test_single_destination_command_shape():
    argv = build_relay_command(
        INGEST,
        [Destination(platform="youtube", url="rtmp://a.rtmp.youtube.com/live2/key-1")],
    )
    assert argv[0] == "ffmpeg"
    # Input follows -i
    assert argv[argv.index("-i") + 1] == INGEST
    # Stream copy, no transcode
    assert argv[argv.index("-c") + 1] == "copy"
    # Machine-readable progress on stdout
    assert argv[argv.index("-progress") + 1] == "pipe:1"
    # Tee muxer selected
    assert argv[argv.index("-f") + 1] == "tee"
    assert tee_arg(argv) == "[f=flv:onfail=ignore]rtmp://a.rtmp.youtube.com/live2/key-1"


def test_multiple_destinations_are_pipe_joined_in_order():
    argv = build_relay_command(
        INGEST,
        [
            Destination(platform="youtube", url="rtmp://yt/live2/key-yt"),
            Destination(platform="facebook", url="rtmps://fb:443/rtmp/key-fb"),
        ],
    )
    assert tee_arg(argv) == (
        "[f=flv:onfail=ignore]rtmp://yt/live2/key-yt"
        "|[f=flv:onfail=ignore]rtmps://fb:443/rtmp/key-fb"
    )


def test_hls_output_appended_last():
    argv = build_relay_command(
        INGEST,
        [Destination(platform="youtube", url="rtmp://yt/live2/key")],
        hls=HlsSettings(output_path="/data/hls/stream-1/index.m3u8"),
    )
    assert tee_arg(argv).endswith(
        "|[f=hls:hls_time=4:hls_list_size=6:hls_flags=delete_segments]"
        "/data/hls/stream-1/index.m3u8"
    )


def test_hls_only_relay_is_allowed():
    argv = build_relay_command(
        INGEST,
        [],
        hls=HlsSettings(output_path="/data/hls/s/index.m3u8", segment_seconds=2, playlist_size=10),
    )
    assert tee_arg(argv) == "[f=hls:hls_time=2:hls_list_size=10:hls_flags=delete_segments]/data/hls/s/index.m3u8"


def test_hls_without_delete_segments_flag():
    argv = build_relay_command(
        INGEST,
        [],
        hls=HlsSettings(output_path="/data/hls/s/index.m3u8", delete_segments=False),
    )
    assert "hls_flags" not in tee_arg(argv)


def test_no_outputs_raises():
    with pytest.raises(ValueError):
        build_relay_command(INGEST, [])


def test_empty_ingest_raises():
    with pytest.raises(ValueError):
        build_relay_command("", [Destination(platform="youtube", url="rtmp://yt/live2/k")])


def test_custom_ffmpeg_binary():
    argv = build_relay_command(
        INGEST,
        [Destination(platform="youtube", url="rtmp://yt/live2/k")],
        ffmpeg_binary="/usr/local/bin/ffmpeg",
    )
    assert argv[0] == "/usr/local/bin/ffmpeg"


def test_maps_video_and_audio_optionally():
    argv = build_relay_command(INGEST, [Destination(platform="youtube", url="rtmp://yt/l/k")])
    map_values = [argv[i + 1] for i, token in enumerate(argv) if token == "-map"]
    assert map_values == ["0:v?", "0:a?"]


def test_fifo_recovery_options_present():
    argv = build_relay_command(INGEST, [Destination(platform="youtube", url="rtmp://yt/l/k")])
    assert argv[argv.index("-use_fifo") + 1] == "1"
    assert argv[argv.index("-fifo_options") + 1] == "attempt_recovery=1:drop_pkts_on_overflow=1"


def test_tee_escaping_of_special_characters_in_stream_key():
    argv = build_relay_command(
        INGEST,
        [Destination(platform="youtube", url="rtmp://yt/live2/we|ird[key]")],
    )
    assert tee_arg(argv) == "[f=flv:onfail=ignore]rtmp://yt/live2/we\\|ird\\[key\\]"


def test_tee_escape_handles_backslash_first():
    assert _tee_escape("a\\b|c") == "a\\\\b\\|c"


def test_argv_contains_no_shell_metacharacter_concatenation():
    """argv must be a flat list of strings (never joined for a shell)."""
    argv = build_relay_command(INGEST, [Destination(platform="youtube", url="rtmp://yt/l/k")])
    assert all(isinstance(part, str) for part in argv)


# ---------------------------------------------------------------------------
# Platform constants
# ---------------------------------------------------------------------------

def test_platform_urls_match_packages_config():
    # Mirrors packages/config/src/index.ts
    assert PLATFORM_RTMP_URLS["youtube"] == "rtmp://a.rtmp.youtube.com/live2"
    assert PLATFORM_RTMP_URLS["facebook"] == "rtmps://live-api-s.facebook.com:443/rtmp"
    assert PLATFORM_RTMP_URLS["tiktok"] == "rtmp://push.tiktokcdn.com/live"
    assert PLATFORM_RTMP_URLS["instagram"] == "rtmps://live-upload.instagram.com:443/rtmp"
    assert PLATFORM_RTMP_URLS["pmbc"] == "rtmp://media-server/live"


def test_resolve_rtmp_url_is_case_insensitive_and_none_for_unknown():
    assert resolve_rtmp_url("YouTube") == "rtmp://a.rtmp.youtube.com/live2"
    assert resolve_rtmp_url("twitch") is None


def test_build_destination_url_joins_cleanly():
    assert (
        build_destination_url("rtmp://a.rtmp.youtube.com/live2/", "abcd-1234")
        == "rtmp://a.rtmp.youtube.com/live2/abcd-1234"
    )
    assert (
        build_destination_url("rtmp://a.rtmp.youtube.com/live2", "abcd-1234")
        == "rtmp://a.rtmp.youtube.com/live2/abcd-1234"
    )
