# Cell 3.6 — Side by side: the same topic in both versions

## What this code does
- It prints the **article chunk** for Labour Law Article 29 (Annual leave).
- It prints the **fixed chunks** that contain the words "annual leave".

## Why we need it
Numbers are useful, but **seeing** the chunks shows *why* the strategy matters.

## What we saw
**Article chunk** — complete and labelled:
```
[Labour Law — Article 29, part 1/2]
Article (29)
Annual leave
1. ... the Worker shall be entitled to an annual leave with full pay of not less than:
a. Thirty days for each year ...
```

**Fixed chunk `labour_law-f50`** — starts in the middle of a sentence and mixes topics:
```
them.                                   <- end of Article 27
Article (28)
Official Holidays and Requiring Worker to Work Therein
...                                     <- Article 28 (holidays)
Article (29) Annual leave ...           <- start of Article 29
```

**Fixed chunk `labour_law-f51`** — has the actual rule, but **lost its heading**:
```
enforcement of the provisions of this Decree by law, the Worker shall be entitled to an ...
a. Thirty days for each year ...
```
The chunk with the answer ("thirty days") does not contain "Article 29" or "Annual leave". The heading is in the previous chunk. Search may return the wrong chunk, and the bot cannot cite the article.
