---
platform: linkedin
note: "research-ai-tells.md P4: human; trips only P8_opener (known false positive, jury override allowed)"
---
Hot take nobody asked for: the reason your RAG demo works and your RAG product doesn't is that your demo has 40 documents and your customer has 40,000, and 39,000 of them are the same PDF re-uploaded by 6 people in 2019. Dedup before you touch an embedding model. I learned this after we shipped to a bank and their "AI" confidently cited a 2014 policy that had been rescinded 4 times.
