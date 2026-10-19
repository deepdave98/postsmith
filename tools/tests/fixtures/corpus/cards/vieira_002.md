---
schema: postsmith.card/1
post_id: vieira_002
annotated_by: post-annotator
verified: true
profile_version_at_annotation: 1
thesis: Removing infrastructure is approved in minutes; adding it takes a design doc, from the same people.
subtext: The author reviews code and is quietly indicting the process, not the reviewers.
archetype: one_liner
angle: specific_number
emotion: FINALLY
hook:
  text: the PR that removed our feature flag system was 11 files, -4,812 lines, and got 3 approvals in 20 minutes. the PR that added it took 6 weeks and a design doc. same three reviewers.
  types:
  - specificity
  - outcome_first
  above_fold_chars: 180
  standalone: true
rehook: null
beats:
- lines: '1'
  beat: hook
- lines: '1'
  beat: proof
- lines: '1'
  beat: punchline
expectation_ledger:
- lines: '1'
  sets_up: a comparison of two PRs
  breaks_with: same three reviewers
rhythm: '3'
devices:
- device: specificity
  lines: '1'
  note: 11 files, -4,812 lines, 20 minutes vs 6 weeks
- device: deadpan
  lines: '1'
  note: no adjective anywhere
- device: callback
  lines: '1'
  note: the reviewers return as the punchline
- device: lowercase_everything
  lines: '1'
  note: X register
moves:
- two_numbers_same_unit
- deadpan_number_ending
stance:
  earnest_ironic: 0.55
  humble_brash: 0.5
  warm_cold: 0.55
  dense_airy: 0.65
  abstract_specific: 0.95
pov: first_plural
tense: past
address: none
ending: punchline
why_it_works: Two numbers with the same unit and opposite sizes; the reader does the arithmetic and the last fragment removes the only excuse (different reviewers).
what_would_break_it: Explain what this says about engineering culture.
distinctive_phrases:
- same three reviewers
- -4,812 lines
generic_risk: low
humor_attempted: true
engagement:
  likes: 2380
  comments: 96
  reposts: 210
---
