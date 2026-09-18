---
name: voice
description: Rewrites, tightens, shortens or rewords a line or paragraph of Deep's own text in his voice when he asks in plain chat, such as "tighten this", "shorten this line", "make this sound like me", "less corporate", "reword this", "cut this to 280", or pastes a sentence and asks for a better one. Not for writing a new post (that is /post) and never runs the eval.
user-invocable: false
metadata:
  skill_version: "1.0"
---

# voice

Deep is asking for an edit to text he owns, in chat, and wants it back in seconds. Apply his voice, not the reference authors' and not a model's default, because a line that reads like the feed's median or like a model undoes the point of the project.

Before the first rewrite in a session read `style/persona.md` (Voice choices, Vocabulary, Comfort levels, Platform choices, Never), `style/lexicon.yaml` (tiers, `user_tells`, `do_not_reuse`) and `style/self.md` when it exists. They are standing constraints:
- Keep the claim set identical: same facts, numbers, names, opinions, jokes; nothing added, nothing that changes what he is asserting. Tightening means fewer words for the same claims. If a claim must go to hit a length he asked for, say which one and why, and let him choose.
- No phrase from any lexicon tier or `do_not_reuse` list, no `user_tells`; these are the tells the deterministic check would flag and Deep has said he hates.
- Em dashes only if his Voice choices allow them; casing, contractions, sentence length and how he addresses the reader follow the same table.
- No engagement bait, no closing question unless it is specific to the claim, no summary line, no moral, no triplet of abstract nouns, no "not X but Y".
- Platform limits when the platform is known: X 280 as X counts (URL 23, emoji 2, CJK 2); LinkedIn first line one line long and readable before the fold (~140 chars).
- Do not explain a joke; the punch word stays last.

Answer with the rewrite (at most two alternatives when they differ in something real, such as length band), then one line naming what changed. No preamble.

Do not run Tier 0, judges or `/eval`; this is his edit, not a candidate. Do not write the result into any file under `drafts/`: a candidate changed outside the loop would carry a verdict it did not earn, and if he pastes the edited line the change is captured as `edit_ops` by `/posted` anyway. If he wants it judged: `/eval - --platform li|x` with the text pasted after the flags.
