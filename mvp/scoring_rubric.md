# RAG Experiment Scoring Rubric

Use this formula for `overall_score` in the tracker:

overall_score =
0.40 * faithfulness +
0.30 * answer_correctness +
0.20 * retrieval_recall_at_5 +
0.10 * abstention_accuracy -
0.10 * hallucination_rate -
0.05 * invalid_citation_rate -
latency_penalty

Where latency_penalty is:
- 0.00 if latency_p95_ms <= 3000
- 0.02 if 3000 < latency_p95_ms <= 5000
- 0.05 if latency_p95_ms > 5000

## Pass/Fail Gates (must all pass)
- faithfulness >= 0.75
- answer_correctness >= 0.70
- retrieval_recall_at_5 >= 0.65
- hallucination_rate <= 0.12
- invalid_citation_rate <= 0.10
- latency_p95_ms <= 5000

## Recommended Comparison Rule
When comparing two experiments, select the winner if:
- overall_score improves by at least 0.02, and
- no pass/fail gate regresses from pass to fail.

If scores are within 0.02, prefer the lower latency and lower hallucination run.
