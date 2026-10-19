---
schema: postsmith.card/1
post_id: okonkwo_004
annotated_by: post-annotator
verified: true
profile_version_at_annotation: 1
thesis: A safety step that never fires is a cost, and removing it changes nothing but throughput.
subtext: The author trusts the reader to get the joke without a lesson attached.
archetype: one_liner
angle: deflation
emotion: LOL
hook:
  text: our enrichment pipeline has a step called "sanity check" that has never once returned false. 2.1 million rows. removed it today. throughput up 4%, sanity unchanged.
  types:
  - deadpan_announcement
  - specificity
  above_fold_chars: 164
  standalone: true
rehook: null
beats:
- lines: '1'
  beat: hook
- lines: '1'
  beat: punchline
expectation_ledger:
- lines: '1'
  sets_up: a bug story about the missing check
  breaks_with: throughput up 4%, sanity unchanged
rhythm: '4'
devices:
- device: deadpan
  lines: '1'
  note: removing a safety check reported as a release note
- device: lowercase_everything
  lines: '1'
  note: X register
- device: fake_precision
  lines: '1'
  note: 2.1 million rows for a step that does nothing
- device: anti_climax
  lines: '1'
  note: the only effect is 4% throughput
moves:
- flat_literal_description
- deadpan_number_ending
stance:
  earnest_ironic: 0.6
  humble_brash: 0.45
  warm_cold: 0.5
  dense_airy: 0.7
  abstract_specific: 0.95
pov: first_plural
tense: past
address: none
ending: punchline
why_it_works: Four fragments, each shorter than the last, and the final one pairs a metric with a non-metric. The reader supplies the opinion about safety theatre; the post never states it.
what_would_break_it: 'Add ''lesson: measure your checks'' or an emoji.'
distinctive_phrases:
- sanity unchanged
- never once returned false
generic_risk: low
humor_attempted: true
engagement:
  likes: 940
  comments: 44
  reposts: 71
---
