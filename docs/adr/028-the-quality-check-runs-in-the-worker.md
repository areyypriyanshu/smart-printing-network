# ADR 028: The quality check runs in the worker, on a labelled fixture set

Date: 2026-10-21
Status: Accepted
Requirement: Phase 2, FR-20 and FR-21 (quality report)

## Context

A customer uploads a PDF that may contain a photograph scanned far too low for the size it is printed at, or a page blurred by a bad scan. The shop finds out when the printout comes out badly, and it turns into a dispute.

The measurements themselves are cheap to state and expensive to make. Reading every page of a PDF and rendering every picture on it is CPU heavy work on a file that came from a stranger. The request that carries the file must not wait for it, and the request must not be the place where a hostile file can do damage.

The thresholds are the other half of the problem. A number like "blur score below 90 is blurry" looks like folklore until it has been measured. An unmeasured threshold is a guess with a decimal point in it, and it cannot be defended to a shop that says the report is wrong about their customer's file.

## Decision

Two decisions, one about where the work happens and one about where the numbers come from.

**The analysis runs in the worker.** The customer asks for a report; the API records that the request exists and answers at once; the worker picks it up, does the work and writes the result. The analysis is bounded on every axis it can be: the number of pages, the number of pictures on a page, the size of every rendered region and the time the whole file may take. A file that breaks a bound produces a failed report, not a hung worker. A failed report is advisory too: it says the check did not happen, and the order is not affected.

**The thresholds come from a labelled fixture set.** The set is generated, not collected, so it is reproducible, small and free of anybody's personal documents. It is split in two halves: a whole *kind* of page belongs to the calibration half or the held out half, never both, so the same source image cannot appear on both sides of the split. The threshold is chosen on the calibration half and reported on the held out half. The evaluation script and its output are committed, so the numbers are part of the repository and a change to the rules has to change them.

The rules themselves stay in `domain/pdf_rules.py`, which is pure and unit tested. The analyzer in `quality/analyzer.py` only measures; it decides nothing.

**The report is advisory.** It never changes a price, a status or a payment. A customer who has seen the warnings and wants the print anyway acknowledges them, and the fact is recorded on the report and on the order. Not acknowledging them does not stop the order either.

## Alternatives considered

1. **Analyse the file in the upload request.** Rejected: the upload path answers in milliseconds today, and a 300 page PDF with pictures on every page would turn it into a long request. It also puts a hostile file in the path that serves every customer.
2. **A separate analysis service.** Rejected: it is a new deployment, a new failure mode and a new queue to operate, for a job the worker is already built to do. The worker already owns the file retention job and the refund job, and both are the same shape: claim rows, do the work, write the result.
3. **Use the thresholds that the plotting world uses.** Rejected: those numbers are for charts on screen, not for a page that is going to be printed on paper, and they are not measured against anything that resembles what a customer uploads. The requirement asks for a measured evaluation, and a borrowed constant is not one.
4. **Collect real customer files and label them.** Rejected for now, and it is the obvious next step. Labelling real uploads needs a labelling tool, a labelling policy and a consent question, and the fixtures cannot stand in for it forever. The evaluation is written so that adding a real file to the set is a matter of adding a labelled page, not a change to the method.
5. **Let the customer choose whether to run the check.** Rejected: the check is quick and the customer asked for a print, not a report. It is asked for once, at the review step, and the customer can carry on while it runs.

## Consequences

- The quality feature adds OpenCV to the backend. It is a headless build, pinned, and the analysis is the only thing that imports it.
- The report keeps a copy of the measurements, not of the file, so it survives the file being deleted.
- The evaluation has to be re-run when the analyzer changes, and the numbers in the commit message have to match the numbers in the file.
- A false positive costs the customer a moment of doubt. A false negative costs the shop a wasted printout, which is why the threshold is set to catch the bad pages rather than to be cautious about the good ones.
