---
platform: linkedin
note: P4 from research-ai-tells.md 7.2. 'Hot take nobody asked for:' trips the P8 regex; the opener is subverted, so a jury override (or base-rate downgrade when the lens uses 'hot take' > 25%) must rescue it.
---
Hot take nobody asked for: the reason your RAG demo works and your RAG product doesn't is that your demo has 40 documents and your customer has 40,000, and 39,000 of them are the same PDF re-uploaded by 6 people in 2019. Dedup before you touch an embedding model. I learned this after we shipped to a bank and their "AI" confidently cited a 2014 policy that had been rescinded 4 times.
