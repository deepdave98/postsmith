# Accepted source formats for /ingest

Everything goes through `uv run tools/ingest_normalize.py <source> --kind auto|csv|json|md --json`, which maps
whatever it finds onto one row shape: `{author_name, author_slug, platform, text, posted_at, url, engagement,
media: [{path_or_url, description}], transcript, source_ref}`. The rules below say what it can map on its own and
what triggers a question.

## 1. Canonical columns and accepted header synonyms
Matching is case-insensitive; spaces, underscores and hyphens are equivalent.

| Canonical | Accepted headers | Required | Notes |
|---|---|---|---|
| author | name, poster, author, creator, handle | yes, unless `--author X` | a handle like `@laraacosta` is kept as handle; the slug is derived from the name |
| text | content, post, text, body, caption | yes | verbatim; line breaks preserved (quote multi-line cells in CSV) |
| platform | platform, network, channel | no | `linkedin` or `x` (also accepts `li`, `twitter`); else inferred (section 5) |
| media | media, image, picture, video, attachment, file | no | local path relative to the source file, absolute path, direct file URL, or a Drive share link; several in one cell separated by `;` |
| media_description | description, alt, media_notes | no | the sheet author's note about the media; a hint for the annotator, never a substitute for looking |
| transcript | transcript | no | text of a video's speech, if you have it (whisper is not installed) |
| posted_at | date, posted, published | no | any parseable date; ISO preferred |
| url | url, link, permalink | no | stored only; never fetched |
| likes | likes, reactions | no | integers; `1.2k` accepted |
| comments | comments, replies | no | |
| reposts | reposts, shares, retweets | no | |
| views | views, impressions | no | |

Unmapped columns are listed in the ingest report and otherwise ignored. If `text` or `author` cannot be mapped, the
tool returns `needs` and /ingest asks one question; answer with the column names or pass `--author` / `--mapping`.

## 2. CSV
UTF-8 or UTF-8 with BOM; delimiter sniffed (`,` `;` `\t`); header on the first row; multi-line cells quoted.

```csv
name,platform,date,content,media,likes,comments
Lara Acosta,linkedin,2026-05-01,"We killed our AI strategy last week.

Nobody noticed.

...",acosta_whiteboard.jpg,1200,340
Jasmin Alić,x,2026-04-12,"the whole post is the first line",,800,41
```
Media files referenced by relative name are looked up next to the CSV (so drop them into `corpus/inbox/` with it).

## 3. JSON
Either an array of objects or JSON Lines, one object per post, using the canonical column names (synonyms from
section 1 are accepted as keys too). `media` may be a string, a list of strings, or a list of
`{path_or_url, description}`.

```json
[
  {"author": "Sahil Bloom", "platform": "linkedin", "posted_at": "2026-03-02",
   "text": "First line.\n\nSecond paragraph.", "media": ["bloom_chart.png"],
   "engagement": {"likes": 5400, "comments": 210, "reposts": 90}},
  {"author": "Paul Graham", "platform": "x", "text": "one-liner", "media": []}
]
```

## 4. Markdown
Two shapes:

One post per file, YAML front matter then the verbatim text:
```markdown
---
author: Lara Acosta
platform: linkedin
posted_at: 2026-05-01
url: https://www.linkedin.com/posts/...
media: [acosta_whiteboard.jpg]
media_description: whiteboard with three boxes
engagement: {likes: 1200, comments: 340}
---
We killed our AI strategy last week.

Nobody noticed.
```

Several posts in one file, separated by a line containing only `---`; each block starts with `key: value` header
lines (`author:` required, `platform:` optional) and a blank line, then the text:
```markdown
author: Shaan Puri
platform: x

chatgpt is a guy on reddit 8 years ago, but polite
---
author: Shaan Puri
platform: linkedin
media: puri_screenshot.png

Longer post text here.
```

## 5. Platform inference
1. An explicit `platform` column or header wins.
2. Else the `url` domain: `linkedin.com` → linkedin; `x.com` or `twitter.com` → x.
3. Else text length: at most 280 characters and no line break → x; otherwise → ask.
4. `--platform` on the command line applies to every row of that source and skips the question.

## 6. Google Sheets
- Header row in row 1, one post per row, columns as in section 1. Each tab is ingested as a separate source.
- Media must be a local file name (drop the file into `corpus/inbox/`) or a Google Drive share link in the `media`
  column. Images inserted into cells (Insert > Image > in cell) are not exported by any read path and are lost;
  so are images floating over cells.
- /ingest reads the sheet through the Drive connector (`search_files`, `read_file_content`) and saves the table
  verbatim to `corpus/inbox/gsheet_<fileid>_<date>.csv` (further tabs: `gsheet_<fileid>_<tab-slug>_<date>.csv`)
  before normalizing, so the ingest is reproducible and idempotent (the manifest dedupes on content, not on the
  file).
- Fallback when the connector is not available: File > Share > Publish to web, format CSV, one URL per tab (the
  `gid` in the URL selects the tab); /ingest fetches it with `curl -L` after asking once.
- Drive-linked media are downloaded through the connector after one consent per run; direct file URLs after the same
  consent; LinkedIn or X page URLs are refused (they are pages, not files; the post is kept text-only). CDN links
  expire, so keep originals locally.

## 7. Self samples (`--self`)
Any first-person writing counts: posts, Slack or WhatsApp messages, emails, memos, the three rewritten train posts
from `/persona`. Author is always `self`, platform is optional (inferred or `--platform`), nothing is ever held out.
`self.md` and the `register_match_self` gate need at least `corpus.self_min_samples` samples or
`corpus.self_min_words` words (config) before they stop reporting "voice anchor: weak".

## 8. What to expect after commit
- Exact duplicate (same normalized text, same author): skipped, listed.
- Near-duplicate by the same author (word 8-gram Jaccard at or above `overlap.near_duplicate_jaccard`): ingested
  as `variant_of` the earlier post; excluded from exemplars.
- Same text by the same author on both platforms: two posts linked by `crosspost_of`; one enters the filler pool.
- Split: heldout by content hash (`corpus.heldout_modulo`), topped up in sorted-hash order to
  `corpus.heldout_min_per_platform`; self never held out; written to the manifest and never changed. Below
  `corpus.small_corpus_max_posts` total or `corpus.small_corpus_min_per_platform` per platform, small-corpus mode:
  no heldout split until the corpus crosses the bar.
- Language: detected by stopword ratio and written as `lang`; non-English posts get null for English-only
  stylometric features and are flagged in the report.
