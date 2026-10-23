# Cell 3.2 — Find the real article headings

## What this code does
- A **regular expression** (`HEADING`) finds lines that are article headings.
- `find_article_starts(text)` goes through the text and keeps the position of each real heading. It accepts a number only if it goes **up** (small gaps allowed).
- It prints how many articles it found, and which numbers are **missing**.
- A diagnostic prints other lines that start with "Article" but are not headings.

## Why we need it
To cut the text **at article borders**, we must know exactly where each article starts. A wrong start means a wrong chunk and a wrong citation.

## The final pattern
```
^Article\s*[()]?\s*(\d+)\s*[()]?\s*$
```
| Part | Meaning |
|---|---|
| `^` and `$` | the heading must be **alone on its line** |
| `[()]?` | a bracket is optional, and can face either way |
| `(\d+)` | capture the article number |

## Small example
```
Article (5)                                   -> heading     (normal)
Article )2 (                                  -> heading     (reversed brackets, Labour Law)
Article 21                                    -> heading     (no brackets, PDPL)
Article (5) of the Decree-Law and the ...     -> NOT heading (a mention: text continues on the line)
```

## How we got there (3 iterations)
1. "Accept only the next number" → PDPL stopped at Article 20: Article 21 was not found, so 22–31 were all rejected.
2. Executive Regulation: a **mention** of "Article (5)" was taken as the heading, so the real Article 5 was rejected → rule: heading must be alone on its line.
3. Diagnostic showed PDPL writes `Article 21` with **no brackets** → brackets made optional.

Final result: Labour Law 74/74, Executive Regulation 39/39, Amendment 3/3, PDPL 31/31.
