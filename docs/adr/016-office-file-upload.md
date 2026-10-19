# ADR 016: Printing the file the student actually has

Date: 2026-10-20
Status: Accepted
Requirement: FR-15, extending FR-4 (Sprint 6)

## Context

The product is "upload a PDF, get it printed". The customer is a student
with a project report. The student has a Word document.

The current behaviour is a dead end. A customer who uploads a `.docx`
gets `FILE_NOT_PDF` and the message "File does not look like a PDF." The
message is true and useless. It does not say what to do, so the student
closes the tab, and most of them never come back. The order is lost at
the last possible moment, after the customer has already chosen the
shop, the options and the price.

The cheapest fix is not code at all: change the message to name the fix.
"We print PDFs. Open your file in Google Docs, choose File, Download as
PDF, then upload that." That is one string, and it recovers some of the
lost orders on its own.

But it asks the student to do the conversion themselves, in a tool that
is not the one they wrote the document in, for a document they may have
edited in Word an hour ago. Every step of that is a chance to give up.
And the request that started this was the obvious one: accept Word,
Excel and PowerPoint files as well.

### The trap

Accepting a `.docx` sounds small and is not. A `.docx` is a zip archive
of XML parts. Getting the text out means reading `word/document.xml`,
resolving relationships for pictures, walking tables, and understanding
paragraph styles. Getting a *printable* result out means laying that
content out on pages that look like the document the student made.

The naive version of this feature is a trap: accept the file, print the
text, and quietly lose the formatting the student spent an evening on.
A report that comes back with the headings flattened and the pictures
missing is worse than a refusal, because the student finds out at the
counter, after paying.

So the decision is not "can we read a `.docx`". It is "what do we
promise, and what do we tell the customer when we cannot keep that
promise".

## Decision

Accept `.docx`, `.xlsx` and `.pptx` as well as PDF, convert them to PDF
on the server, and print the converted PDF. The customer sees one
upload, one page count and one price. The shop opens a PDF.

The conversion is built on what is already here: the standard library
(`zipfile` and `xml.etree`) to read the file, and PyMuPDF's `Story`
engine, which is already a dependency, to lay it out. **No new
dependency, no new service, no new image.**

### What the conversion keeps, and what it does not

This is the part that has to be said out loud, in the product, not only
here.

Kept: the text, the order of the text, the heading structure, the
pictures, the table contents, one page per slide for a presentation.

Not kept: the fonts (they are substituted), the exact table widths,
headers and footers, columns, text boxes, footnotes, and anything else
that lives in the layout rather than in the content.

The page count, and therefore the price, comes from the converted PDF.
The customer is quoted for what will actually be printed.

A converted document is a *printable approximation* of the document the
student made, not a copy of it. The upload screen says so, in the place
where the customer chooses the file.

### The message is part of the feature

Every file the platform cannot print is refused with a message that
names the fix. This is not a wording preference; it is the difference
between a dead end and a recoverable mistake.

| The customer uploads | What they are told |
|---|---|
| An image | "We print PDF, Word, Excel and PowerPoint files. Open your file in Google Docs, choose File, Download as PDF, then upload that." |
| A plain text file | The same, with "not plain text" said plainly. |
| An old `.doc` or `.xls` | "Save it as a `.docx` or `.xlsx` first, then upload that." |
| An empty file | "That file is empty. Choose it again and upload it." |
| A `.docx` that cannot be read | "We could not read that file. Open it in Word, Excel or Google Docs and download it as a PDF, then upload that." |

The error code does not change. It stays `FILE_NOT_PDF`, because the
code is for the client and the message is for the person. The frontend
map keeps a fallback, but the server's message wins, because the server
is the only party that knows what the file actually was.

### The file the shop opens is a PDF, and it is named for what it is

The customer sent `report.docx`. The shop must not open a PDF called
`report.docx`. The stored object is a PDF, and the download is named
`report.pdf`. The `uploads.source_format` column records what the file
arrived as, so the name can be derived and the fact is kept.

## Alternatives considered

1. **Only change the error message.** Rejected as the whole answer, but
   kept as part of it. It is the cheapest single win available and it
   stays. It is not enough on its own, because it makes the student do
   the conversion by hand, in the wrong tool.
2. **Add a conversion service (LibreOffice, or a hosted API).**
   Rejected: a LibreOffice container is a gigabyte of image, a process
   that needs watching, and a new failure mode (it hangs, it runs out of
   memory, it needs a font configuration). A hosted API is money, a
   network dependency, and a privacy problem: a student's project report
   leaves the country. The standard library plus PyMuPDF does the
   90% case in about 300 lines, and the 10% it does not do is the 10%
   the student would have to ask for anyway.
3. **Let the browser convert it.** Rejected: the browser has no
   reliable Word reader, and a client-side conversion would make the
   page count, and therefore the price, a thing the client decides. The
   price is computed on the server, and it has to stay that way.
4. **Accept the file and print the extracted text, with no layout.**
   Rejected: this is the trap described above. A report with its
   headings flattened and its pictures dropped is not a printout of what
   the student made, and the student finds out at the counter.
5. **A separate "converted documents" product with its own price.**
   Rejected: it invents a second kind of order for what is, to the
   customer, one print job.

## Consequences

- The upload path now has two outcomes: a PDF that is stored as it is,
  and a document that is converted and stored as a PDF. Both end up as
  one PDF object, so everything downstream (the shop's link, the
  retention job, the page count) is unchanged.
- A converted document can be a slightly different number of pages from
  the original. The price follows the converted page count, because that
  is what the shop prints.
- The `domain/` layer grew two files: `documents.py`, which works out
  what a file is, and `office.py`, which reads the three Office formats.
  Both are pure, standard library only, and both are unit tested without
  a database.
- A `.docx` is a zip archive, which means a hostile upload is a zip bomb.
  The reader caps what it will expand: 200 MB expanded, 200 pictures,
  2000 rows, 60 columns, 500 characters per cell.
- **This is scope beyond the original PRD.** The PRD said "upload one
  PDF". A converted document is an approximation, and a customer who
  needs the exact layout has to upload a PDF. The request came from the
  owner, and the alternative (the dead end) was worse, but it is a real
  widening of the promise and it is recorded here.

## Revisit trigger

Revisit if the fidelity of the conversion becomes a complaint. The
signal to watch is how often a customer says the printed document does
not look like the one they sent. At that point the options are a real
office suite in a container, or telling the customer to upload a PDF
before they order, so that the order only starts once the file is right.
