# Moves catalogue (fixture, style/moves.md shape)

Cross-author mechanisms learned from the fixture corpus. One `### <slug>` section per move; `seen_in` cites
post ids (with optional `L<a>-<b>` post lines). An old id lives on as an alias, either inline (`aliases:`) or as a
stub section carrying `merged_into:`. Two of the six slugs the fixture cards use are aliases, on purpose.

## Moves

### receipt_as_proof
- mechanism: a claim is followed within one sentence by the number, invoice or artifact that proves it
- trigger: the post makes a claim a reader could doubt
- shape: claim line, then a line whose only content is the receipt
- seen_in: [kessler_001 L1-3, okonkwo_001 L1, vieira_001]
- execute_without_copying: pick a claim from the persona fact bank and put its receipt in the next sentence; never reuse the corpus numbers
- risk: a receipt the author cannot produce on request reads as a fabricated stat
- platforms: [linkedin, x]
- aliases: [two_numbers_same_unit]

### deadpan_number_ending
mechanism: the last line is a flat number or fact with no comment after it
trigger: the body has built toward a verdict
shape: setup, proof, then a one-sentence closer that states a figure and stops
seen_in:
  - kessler_001 L7
  - okonkwo_004
  - vieira_002 L5-6
execute_without_copying: end on the persona's own figure; delete every word after it
risk: reads as a shrug when the number is round or unsurprising
platforms: [linkedin, x]

### flat_literal_description
- mechanism: the hyped or dramatic thing is described in literal, inventory-like terms
- trigger: the topic is something the feed is excited about
- shape: one or two sentences of plain description, no adjectives, no verdict
- seen_in:
  - vieira_004
  - okonkwo_004 L1-2
- execute_without_copying: describe the persona's own product or tool the way a manual would; let the gap between register and stakes do the work
- risk: with no specific inside it, it is a shrug rather than a joke
- platforms: [x]

### escalating_triple_breaks
- mechanism: two items set a pattern and the third degrades or changes category
- trigger: there are three real instances to line up
- shape: item, item, item-that-breaks; the break lands on a specific
- seen_in: [kessler_003 L3-5, okonkwo_003]
- execute_without_copying: take three instances from the persona story bank; make the third literal where the first two were figurative
- risk: a fourth item or a lesson after the third kills it
- platforms: [linkedin, x]

## Merged

### self_undercut_close
merged_into: deadpan_number_ending
