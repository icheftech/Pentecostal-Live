export const supportedPlatforms = [
  { id: "youtube", label: "YouTube", rtmpUrl: "rtmp://a.rtmp.youtube.com/live2" },
  { id: "facebook", label: "Facebook", rtmpUrl: "rtmps://live-api-s.facebook.com:443/rtmp" },
  { id: "tiktok", label: "TikTok", rtmpUrl: "rtmp://push.tiktokcdn.com/live" },
  { id: "instagram", label: "Instagram", rtmpUrl: "rtmps://live-upload.instagram.com:443/rtmp" },
  { id: "pmbc", label: "PMBC Website", rtmpUrl: "rtmp://media-server/live" }
] as const;

export type PlatformId = (typeof supportedPlatforms)[number]["id"];

