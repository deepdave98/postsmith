---
platform: linkedin
note: 'Original human-quality LinkedIn positive: non-round numbers, a disagreeable claim about eval suites, deadpan register, ends on a concrete fact. Must pass every deterministic check.'
---
Our eval suite has 1,140 test cases and I can tell you what 1,090 of them measure: whether the model still does the thing it did in April.

The other 50 were written after a customer complaint. Those 50 catch every regression we have shipped this year. The 1,090 have caught one, and it was a typo in the eval.

We keep all 1,140 because deleting tests looks bad in a board deck. The suite takes 41 minutes. The 50 take 90 seconds.

Last week an engineer proposed a nightly job that runs only the 50 and posts the result to Slack. It has been running for six days. Nobody has looked at the full run since.
