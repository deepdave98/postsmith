---
schema: postsmith.card/1
post_id: vieira_001
annotated_by: post-annotator
verified: true
profile_version_at_annotation: 1
thesis: A 2,300-line resilience module caused every retry incident; 40 lines and a comment fixed it.
subtext: The author has been the person who read the book and is not above the joke.
archetype: hook_reframe_proof_punch
angle: personal_receipt
emotion: OHHH
hook:
  text: I spent Saturday replacing our 2,300-line retry module with 40 lines and a comment.
  types:
  - specificity
  - deadpan_announcement
  above_fold_chars: 83
  standalone: true
rehook: The module had exponential backoff, jitter, circuit breakers, a dashboard, and a config file with 61 keys.
beats:
- lines: '1'
  beat: hook
- lines: '3'
  beat: setup
- lines: '5'
  beat: turn
- lines: '7'
  beat: proof
- lines: '9'
  beat: punchline
expectation_ledger:
- lines: '3'
  sets_up: an engineering war story
  breaks_with: the book is cited in the docstring
- lines: '9'
  sets_up: a lesson about simplicity
  breaks_with: a page count
rhythm: 1/3/1/2/2
devices:
- device: specificity
  lines: '3'
  note: 61 config keys, a 2022 date, a cited book
- device: understatement
  lines: '7'
  note: double-charged a customer for a €14 plan
- device: anti_climax
  lines: '9'
  note: the design document is a 14-word comment
- device: callback
  lines: '9'
  note: the book returns as a page count
moves:
- receipt_as_proof
- deadpan_number_ending
stance:
  earnest_ironic: 0.55
  humble_brash: 0.5
  warm_cold: 0.55
  dense_airy: 0.65
  abstract_specific: 0.95
pov: first_singular
tense: past
address: none
ending: last_concrete_fact
why_it_works: The reader expects the rewrite to be the hero; instead the incident numbers show the old module was the villain, and the closing page count deflates the book without an argument against books.
what_would_break_it: Add 'simplicity wins' or remove the Lisbon customer.
distinctive_phrases:
- cited in the docstring
- do not add jitter
- The book was 380 pages
generic_risk: low
humor_attempted: true
engagement:
  likes: 1290
  comments: 164
  reposts: 52
---
