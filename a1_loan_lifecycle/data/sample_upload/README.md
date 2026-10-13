# Sample upload packs for the "New application" tab

Synthetic documents for live ingestion demos. Filenames and content keywords drive classification.

| Pack | Fill the form with | Expected result |
|---|---|---|
| `1_complete_term_loan/` (4 files) | Borrower *Northwind Packaging Ltd*, product *term_loan*, amount 3,000,000, tenor 5, rate 0.100 | All documents received. DSCR ~1.9x, leverage ~2.5x, LTV ~55% → **APPROVE**, routed to **Senior Credit Officer** (amount > $2M) |
| `2_missing_docs_term_loan/` (2 files) | Same form values | Bank statement and collateral valuation missing → **REQUEST INFO**, with a drafted information request |

Steps: sign in as a Credit Analyst → **📥 New application** → fill the form → **Upload** the files of one pack →
**Ingest application** → the new `UPL-xxxx` application is selected in the sidebar → **▶ Run agent pipeline** →
tab **① Origination → Decision**.
