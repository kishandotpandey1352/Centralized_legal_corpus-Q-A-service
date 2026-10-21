# Screenshot Capture Guide

No screenshots are currently tracked in this repository. Do not add placeholder
images or fabricate results. Capture these views from a running local instance
after starting the backend, ingesting the sample corpus, and launching the
Angular frontend:

1. **Grounded legal question**
   - Use the Answer screen.
   - Show a legal question, the grounded answer, inline citations, and the
     citation inspector with source file and chunk metadata visible.
2. **Document summary**
   - Use the Summary screen.
   - Show the selected document, numbered cited summary, and the citation
     inspector.
3. **Evaluation results and run history**
   - Show the browser-local History screen with a completed query/answer or
     summary run.
   - If a separate evaluation report view is available, show the recorded
     metrics and pass/fail result; otherwise use a checked-in evaluation report
     from `mvp/experiments/` rather than implying the frontend renders metrics.

Suggested filenames:

```text
docs/screenshots/grounded-answer.png
docs/screenshots/document-summary.png
docs/screenshots/evaluation-and-history.png
```

When screenshots are added, update the root README's Demo section with relative
image links and record the capture date, configuration, and whether the view is
from a mocked or live backend.
