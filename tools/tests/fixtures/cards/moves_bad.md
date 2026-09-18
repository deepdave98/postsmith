# Moves catalogue (fixture: every structural problem moves_lint reports)

### receipt_as_proof
- mechanism: a claim is followed by its receipt
- trigger: a doubtful claim
- shape: claim, receipt
- seen_in: [kessler_001 L1-3, okonkwo_001]
- execute_without_copying: use the persona's own receipt
- aliases: [deadpan_number_ending, shared_alias]

### deadpan_number_ending
- mechanism: the last line is a number
- trigger: a verdict is due
- shape: setup, proof, number
- seen_in: [kessler_001 L7]
- execute_without_copying: end on a figure
- aliases: [shared_alias]
- platforms: [linkedin, instagram]

### Bad-Slug
- mechanism: uppercase and a hyphen
- trigger: t
- shape: s
- seen_in: [vieira_001, vieira_002]
- execute_without_copying: e

### receipt_as_proof
- mechanism: duplicate id
- trigger: t
- shape: s
- seen_in: [vieira_001, vieira_002]
- execute_without_copying: e

### missing_fields
- seen_in: [vieira_001 L9-3, nobody_001, not a citation, vieira_002 L1]

### cycle_a
merged_into: cycle_b

### cycle_b
merged_into: cycle_a

### orphan_stub
merged_into: no_such_move
