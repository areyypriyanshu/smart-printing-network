# ADR 006: Classical image analysis instead of a neural network

Date: 2026-10-19
Status: Accepted
Requirement: Phase 2, FR-27 and FR-28 (quality report)

## Context

A customer uploads a PDF that may contain a photograph scanned at a resolution far too low for the size it is printed at, or a page that has been blurred by a bad scan. The shop finds out when the printout comes out badly, which wastes paper, ink and the customer's money, and it turns into a dispute.

The original idea was to train a convolutional network to spot bad pages. That is a serious undertaking: a labelled dataset, a training pipeline, model hosting, a training schedule, and enough real examples of "bad" to avoid a model that has simply learned what a document looks like.

The actual question is narrower than "is this page good". It is two measurable things: how many pixels does each placed image have per inch of paper, and how much detail does the page have. Both have classical answers.

## Decision

Use effective DPI and a blur score, both computed with classical methods.

- **Effective DPI** is the pixel width of an image divided by the width it occupies on the printed page. A 600 pixel wide image printed across 8 inches is 75 DPI, which is visibly poor. PyMuPDF reports the placement, so this is arithmetic rather than machine learning.
- **Blur** is measured with the variance of the Laplacian over the rasterised region, normalised to a fixed width so the score does not depend on the resolution of the file. A sharp edge gives a high variance, a blurred one a low variance.
- The thresholds that turn the measurements into a verdict live in `domain/pdf_rules.py`, which is pure and unit tested.

There is no model, and there is no training pipeline. The rules are measured against a labelled fixture set and the evaluation is committed to the repository.

## Alternatives considered

1. **A convolutional network.** Rejected: there is no labelled dataset, and building one that represents what real customers upload is more work than the rest of the feature. The failure mode is also worse. A model that is wrong is hard to explain to a customer and hard to argue with a shop; a threshold that is wrong is a number that can be argued with and adjusted.
2. **Ask the customer to self-report the quality.** Rejected: the customer does not know the resolution of their scan, and the point is to catch the case where they do not know.
3. **Check only the file size or the page count.** Rejected: a ten megabyte file can still be a photograph of a business card stretched to a full page.

## Consequences

- The feature is explainable. The customer sees "this image is 40 DPI on the page", and the shop sees the same number.
- The thresholds are a judgement call, and they are visible. The evaluation records the recall and the false positive rate at each threshold, so the choice can be argued with.
- The method only covers the two things it measures. A page that is sharp and well resolved but badly laid out is not flagged, because the feature does not claim to judge layout.
- The analysis is CPU bound and runs in the worker, never in a request. A pathological PDF has a timeout and a memory limit, and a report that fails is advisory: the customer is told the check did not run and can still order.
- If the classical method turns out not to reach the target on the fixture set, the next step is a better classical method, not a network. A network would be the answer only if the measurements themselves turned out to be the wrong ones, and that is a different kind of question.

## Revisit trigger

If the labelled fixture set shows that effective DPI and Laplacian variance do not separate good pages from bad pages at the target rates, and the failures are cases neither measurement describes, then a learned method is worth evaluating. The evaluation has to be committed either way.
