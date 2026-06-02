# Suggested Amendments for Splana Final Report.docx

This document outlines the recommended changes to be applied to [Splana Final Report.docx](file:///c:/Users/9849i/IdeaProjects/bhawana/Splana%20Final%20Report.docx) before the final presentation. These changes address the discrepancies between the prototype database figures, the report text, and the leakage under-reporting issues.

---

## 1. Amendments to Section 5.3 (How the Matching Engine Works)

### Paragraph [301]
- **Current Text**: 
  > *The estimated revenue leakage for each unmatched shift is calculated by multiplying the shift duration in hours by the Price Guide maximum rate for that support item code. The total across all 52 unmatched shifts was $10,747.93.*
- **Correction Required**:
  - The number **52** represents the count of unmatched shifts from **Tier 1 (exact matching only)**. However, the sum **$10,747.93** is the leakage calculated from the **23 shifts** that remain unmatched after **Tier 3 (same-month matching)** is applied.
  - **Option A (If keeping Tier 3 heuristics)**: Change the text to:
    > *The estimated revenue leakage for each unmatched shift is calculated by multiplying the shift duration in hours by the Price Guide maximum rate for that support item code. The total across all 23 active unmatched shifts (after filtering out cancelled shifts and applying loose month matching) was $10,747.93.*
  - **Option B (If retiring Tier 3 due to false-positives - Recommended)**: Change the text to:
    > *The estimated revenue leakage for each unmatched shift is calculated by multiplying the shift duration in hours by the Price Guide maximum rate for that support item code. The total across all 32 active unmatched shifts (excluding 5 cancelled shifts and disabling loose month-matching heuristics due to a 100% false-positive rate) was $14,003.35.*

---

## 2. Amendments to Section 6.3 (What the Engine Found)

### Table 6.3 (Prototype Results Summary)
The prototype results table in the docx report contains inconsistent counts. Update the table depending on your chosen matching engine configuration:

#### Option A: Running with Loose Month-Matching (Tier 3 Enabled)
Use these figures if you keep the current 3-tier matching engine. Note that this configuration includes 9 false-positive matches, which under-reports leakage.

| Category | Count | Dollar Value | Priority | Notes / Corrections |
| :--- | :--- | :--- | :--- | :--- |
| **Shifts matched to invoices** | 440 out of 463 | — | Green | *Corrected from 406 to include Tier 2 and Tier 3 matches.* |
| **Unmatched shifts (no invoice found)** | 23 | $10,747.93 leakage | High | *Corrected count from 52 to 23 to reconcile with the leakage value.* |
| **Orphan invoices (no matching shift)** | 7 | $2,678.39 | High | *Corrected count from 41 and value from $6,273.80 to reconcile with Tier 3.* |
| **NDIS Price Guide rate violations** | 5 | Compliance risk | High | *Corrected from 9 to 5 (these are the true rate violations).* |
| **Partial matches (hours differ)** | 34 | $3,595.41 | Medium | *Comprises 29 duration mismatches ($2,802.23) and 5 rate mismatches ($793.18).* |

#### Option B: Running with Strict Date-Matching (Tier 3 Disabled - Recommended)
Use these figures if you disable Tier 3 to eliminate false-positive month-level matches. This shows the true magnitude of billing issues.

| Category | Count | Dollar Value | Priority | Notes / Corrections |
| :--- | :--- | :--- | :--- | :--- |
| **Shifts matched to invoices** | 431 out of 463 | — | Green | *Comprises 430 Tier 1 matches and 1 Tier 2 match.* |
| **Unmatched shifts (no invoice found)** | 32 | $14,003.35 leakage | High | *These are the true unbilled care shifts (excluding 5 cancelled shifts).* |
| **Orphan invoices (no matching shift)** | 16 | $6,586.08 | High | *True invoices billed without any care shift record.* |
| **NDIS Price Guide rate violations** | 5 | Compliance risk | High | *True rate violations.* |
| **Partial matches (hours differ)** | 25 | $3,595.41 | Medium | *True date-compliant mismatches.* |

---

## 3. Addition to Section 9 (Project Findings / Limitations)

Insert this new subsection to document the technical insights and how a production build would solve them:

> ### *9.3 Heuristic Matching Limitations & Production Recommendations*
> 
> *During final verification of the Splana prototype, two critical limitations were documented in the reconciliation engine:*
> 
> 1. **Date-Slippage and False-Positives (Tier 3 Month Match)**:
>    * **Issue**: *The prototype's Tier 3 logic matches any shift and invoice within the same month if the participant and support code agree. In the sample data, this matched shifts and invoices up to 19 days apart (e.g., Shift care log on Dec 5th matched to an invoice line on Dec 24th). All 9 of the month-level matches in the sample were false-positives, which hid 9 unbilled shifts, under-reporting revenue leakage by $3,255.42 and creating a 28% false-negative rate.*
>    * **Production Solution**: *Production systems must disable month-level heuristics. Matching must be restricted to a strict 24-hour window (±1 day) to handle night shifts. Same-month discrepancies should instead be routed to a "Manual Audit Queue" for human approval.*
> 
> 2. **Direct Integration (Single Source of Truth)**:
>    * **Issue**: *Relying on CSV file uploads is prone to data quality issues, date format mismatches, and parsing failures.*
>    * **Production Solution**: *The production system should integrate directly with ShiftCare and Xero via API. Every shift completed in ShiftCare must generate a unique `Shift_Transaction_ID` which is automatically appended to the Xero invoice line item. Matching can then be performed strictly on this unique ID, achieving a 100% match rate with 0% false-positives.*
