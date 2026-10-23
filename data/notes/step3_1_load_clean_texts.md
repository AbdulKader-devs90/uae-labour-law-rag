# Cell 3.1 — Load the clean texts

## What this code does
- It reads the 4 clean `.txt` files that Step 2 saved in `data/clean/`.
- `LAWS` connects each file key to two names:
  - a **full title** (for citations), for example `UAE Labour Law (Federal Decree-Law No. 33 of 2021)`
  - a **short name** (for chunk headers), for example `Labour Law`

## Why we need it
- Each notebook starts from **saved files**. We do not run Step 2 again. If something breaks in Step 3, Step 2 is not affected.
- This is how a real pipeline works: each stage reads the output of the stage before it.

## Small example
```
labour_law                    82,351 chars
exec_regs                     53,018 chars
labour_law_amendment_2022      1,605 chars
pdpl                          41,127 chars
```
