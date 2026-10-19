---
schema: postsmith.post/1
post_id: vieira_001
author:
  name: Tomas Vieira
  slug: tomas-vieira
  handle: '@tvieira_dev'
platform: linkedin
posted_at: '2026-02-22'
url: null
lang: en
source:
  kind: md
  ref: fixture_seed.md#vieira_001
  file: corpus/inbox/done/fixture_seed_2026-09-17.md
  ingested_at: '2026-09-17T09:30:00Z'
content_sha256: 37eda278e17c058473a6df6139c5f6990886ce74a7261e44d8bb45784b2b3026
split: train
crosspost_of: null
variant_of: null
engagement:
  likes: 1290
  comments: 164
  reposts: 52
  views: null
media: []
text_stats:
  chars: 700
  words: 124
  lines: 9
  blank_lines: 4
---
I spent Saturday replacing our 2,300-line retry module with 40 lines and a comment.

The module had exponential backoff, jitter, circuit breakers, a dashboard, and a config file with 61 keys. It was written in 2022 by someone who had just read a book about resilience. I know because the book is cited in the docstring.

The 40-line version retries three times, waits 2, 4 and 8 seconds, and gives up.

Production incidents caused by retries in the last 12 months: 3. All three were the old module retrying a request that had already succeeded, which is how we double-charged a customer in Lisbon for a €14 plan.

The comment says "do not add jitter, see incident 2025-11-04." The book was 380 pages.
