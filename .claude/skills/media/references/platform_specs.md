# Platform specs for media

verified_on: 2026-09-17. Every row carries a source URL and a status: **official** (fetched from the platform's
own page), **third-party** (data vendor or press), **unverified** (page blocked, or the page does not state the
number), **project choice** (a default this project picked inside the official range).

`config/postsmith.yaml` (`platforms.*`, `media.*`) mirrors the numbers `tools/media_check.py` enforces; this file
is the human-readable source with provenance. `/eval health` lists every fact whose `verified_on` is older than
`media.facts_stale_after_days` (90 days) as **unverified**: re-fetch the source, correct the number if it moved,
and update the date here and in config. A stale fact never blocks a run; it is printed so Deep knows what to
re-check.

## LinkedIn

| Item | Value | Status | Source |
|---|---|---|---|
| Image aspect ratio | 3:1 to 4:5 accepted; taller than 4:5 is centre-cropped; a single photo renders at most 4:5; recommended width 1080 px; 5 MB | official | https://www.linkedin.com/help/lms/answer/a527229 |
| Image default here | 4:5, 1080x1350 (maximum feed height) | project choice (`platforms.linkedin.image_aspect_default`) | same |
| Image alternative | 1:1, 1080x1080 | project choice (`image_aspects`) | same |
| Portrait vs landscape | portrait images about 32% ahead of landscape on reach | third-party (AuthoredUp, 3M posts) | https://authoredup.com/blog/best-performing-content-on-linkedin |
| Native video | aspect 1:2.4 to 2.4:1; 3 s (desktop) or 2 s (app) to 15 min; 5 GB; 256x144 to 4096x2304 | official (fetched 2026-09-17) | https://www.linkedin.com/help/linkedin/answer/a548372 |
| Video default here | 9:16 (from a Veo render) or 1:1 (centre-crop-safe from 9:16) | project choice (`video_aspects`) | same |
| Alt text | 120 characters (`platforms.linkedin.alt_text_max`); the official alt-text help page describes the flow but states no limit | unverified | https://www.linkedin.com/help/linkedin/answer/a519856 |
| Post text | 3,000 characters | official | https://www.linkedin.com/help/linkedin/answer/a528176 |
| Format reach and engagement | image 1.20x reach / 1.33x engagement; document 1.39x / 1.30x; text 1.07x / 0.78x; native video 0.86x / 0.93x | third-party (AuthoredUp) | https://authoredup.com/blog/best-performing-content-on-linkedin |
| Median engagement rate | carousel 21.77%, video 7.35%, image 6.52%, link 3.81%, text 3.18% | third-party (Buffer, 2025 data) | https://buffer.com/resources/state-of-social-media-engagement-2026/ |
| Infographics | 29% of top-1% posts; claim that LinkedIn detects generic AI imagery | third-party, methodology contested | https://www.linkedin.com/posts/richardvanderblom_rvdbcarousel-algorithm-insights-report-2026-activity-7455148601749729280-AwsY |

## X

| Item | Value | Status | Source |
|---|---|---|---|
| Image aspect ratios | 4:5 (1440x1800), 1:1 (1080x1080), 1.91:1, 16:9 (1920x1080); 1:1 renders square on every surface; 1:1 or 9:16 take more real estate than 16:9; 9:16 recommended for video | official (ads specs) | https://business.x.com/en/help/campaign-setup/creative-ad-specifications.html |
| Image default here | 1:1, 1080x1080; 16:9 1920x1080 only for screenshots and charts; 9:16 allowed | project choice (`platforms.x.image_aspects`) | same |
| Video default here | 9:16 (Veo native) or 1:1 (Runway image-to-video native) | project choice (`video_aspects`) | same |
| Media per post | 4 images, or 1 video, or 1 GIF | third-party | https://fmax.io/blog/twitter-character-limit-2026 ; https://publishq.com/twitter-limits |
| Alt text | 1,000 characters (`platforms.x.alt_text_max`) | third-party; help.x.com returned 403 on fetch 2026-09-17 | https://help.x.com/en/using-x/add-image-descriptions ; https://publishq.com/twitter-limits |
| Video upload limits | free 2:20 / 512 MB; Premium up to 4 h / 8 GB | third-party | https://www.nemovideo.com/blog/twitter-video-specs-guide-2026 |
| Minimum video duration | none applied by this project. `MinVideoDurationMs 10_000` exists in `param.rs` but feeds a video-quality-view signal weighted 0.0 in the 2026-09-17 snapshot; M2 keeps only "hook in the first second" | primary + project rule | https://github.com/xai-org/x-algorithm |
| Format engagement | text 3.56% > image 3.40% > video 2.96% > link 2.25% median ER | third-party (Buffer, 18.8M posts) | https://buffer.com/resources/state-of-social-media-engagement-2026/ |
| Post text | 280 characters (long posts also cut at about 280 in the timeline) | third-party | https://support.typefully.com/en/articles/8717699-twitter-x-posting-limitations |
| Text-as-image | bypasses 280 but is unsearchable and unreadable to screen readers; heavier compression on free accounts | third-party | https://postory.io/blog/social-media-character-image-limits-2026 |

## What each tool can output (drives `aspect_ratio`, `target_pixels`, `resolution_tier`)

| Tool | Ratios and sizes | Status | Source |
|---|---|---|---|
| gpt_image (ChatGPT Images 2.5) | presets 1024x1024, 1536x1024, 1024x1536; custom WxH (multiples of 16, ratio at most 3:1, edge at most 3840 px); 2K/4K presets 2048x2048, 3840x2160. ChatGPT UI exposes Horizontal / Square / Vertical only; an exact 4:5 from the UI is unverified, so use Vertical and crop, or the API | official + unverified (UI ratio) | https://developers.openai.com/api/reference/resources/images/methods/generate ; https://developers.openai.com/api/docs/guides/image-generation |
| nano_banana (2 / Pro) | 1:1, 3:2, 2:3, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9 (NB2 also 1:4, 4:1, 1:8, 8:1); 1K default, 2K, 4K; Gemini app downloads 2K on a paid plan; AI Studio exposes ratio and resolution controls | official | https://ai.google.dev/gemini-api/docs/image-generation |
| veo (3.1) | 16:9 or 9:16 only; 4, 6 or 8 s; 720p default, 1080p and 4K require 8 s | official | https://ai.google.dev/gemini-api/docs/veo |
| runway (Gen-4.5) | text-to-video 16:9 only (1280x720); image-to-video 16:9, 9:16, 1:1, 4:3, 3:4, 21:9; 2-10 s; 720p; 24/25 fps | official | https://help.runwayml.com/hc/en-us/articles/46974685288467-Creating-with-Gen-4-5 |

Consequences: LinkedIn video is 9:16 or 1:1, so Runway text-to-video (16:9 only) is never a LinkedIn option; use
image-to-video from a still. X screenshots and charts at 16:9 are images, not video. Veo landscape (16:9) is not
in either platform's video list in config; render 9:16.

## Config mirror
`platforms.linkedin`: `alt_text_max 120`, `image_aspect_default "4:5"`, `image_aspects ["4:5","1:1"]`,
`video_aspects ["9:16","1:1"]`. `platforms.x`: `alt_text_max 1000`, `image_aspect_default "1:1"`,
`image_aspects ["1:1","16:9","9:16"]`, `video_aspects ["9:16","1:1"]`. `media.<tool>.verified_on` and
`media.<tool>.source` carry the tool facts; `media.facts_stale_after_days: 90`.
