---
platform: linkedin
note: About 2,900 chars; the first 210+ chars are a single throat-clearing sentence with no clause boundary, so both fold cuts land mid-sentence (mid-word). The body after the preamble is a decent receipt post. P2_fold must fail and judge-reader hook must score below threshold.
---
Before I get into what happened with our onboarding numbers this quarter I want to step back and give some context on how I have been thinking about this whole area of the business over the previous couple of years because without that context the rest of this post is going to be hard to follow and I would rather be clear than fast. A lot of what follows will sound obvious in hindsight and some of it was obvious at the time too but we did it anyway and I think the reasons we did are more interesting than the results, so bear with me for a paragraph.

Some background. We sell a data enrichment product to sales teams. Onboarding used to mean a 45-minute call with a customer success manager, a shared Google Doc with 14 steps, and a follow-up email that nobody read. Median time from signup to first enriched list was 9 days. Median time to the second list was 31 days, which is a polite way of saying most people never made a second list.

In January we replaced the call with a 6-minute product tour and a single required action: upload one CSV. If the CSV has a column that looks like a company name, we enrich the first 50 rows for free while the tour is still running. The tour ends on the enriched rows, not on a slide.

Time to first list went from 9 days to 11 minutes. Time to second list went from 31 days to 4 days.

The tour itself is nothing clever. Six screens, one of them a progress bar. What changed is the order: the first thing a new account sees is its own data, enriched. We tried a version in February that showed a sample dataset instead, because our security reviewer did not want us enriching a stranger's upload before they had accepted the terms. Activation on that version was 19%. On the version that uses their own CSV it is 58%. The terms are now a checkbox on the upload screen, which nobody reads either.

The number I did not expect: support tickets in an account's first seven days dropped from 2.3 per account to 0.4. The 14-step document had been generating most of the questions it was supposed to answer. Step 7 alone, which asked people to map their CRM fields before they had seen any output, accounted for 38% of week-one tickets.

We also lost something. The CSM call was where we learned what the customer was trying to do. Without it our churn reasons went from specific ("we needed phone numbers, you gave us emails") to blank. So in March we added one question at the end of the tour, free text, no required answer. 61% of people type something. The most common answer, by a wide margin, is the name of a competitor they are comparing us with.

Onboarding now costs us about $4 per account in enrichment credits. The old version cost about $140 in CSM time. The 14-step document is still in the help centre. It has been viewed 212 times since January, 180 of them by our own sales team, who use it to find the field-mapping screenshot on page 3 because nobody has moved it.
