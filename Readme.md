# Resume Screening and Ranking Baseline

A Python CLI that parses resumes, applies explicit eligibility filters, scores eligible candidates, optionally enriches GitHub profiles, and writes a JSON report. It is designed as a transparent baseline for the Kasparro SDE Intern assignment.

## Requirements

- Python 3.12.5
- Internet access only for optional GitHub enrichment

## Setup

```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# Windows CMD: .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

Put resume PDFs in `resumes/`. DOCX and TXT are also supported. Scanned/image-only PDFs are reported as processing errors because OCR is not included.

Optional GitHub token: copy `.env.example` to `.env` and add `GITHUB_TOKEN=...`. Never commit `.env` or expose your token. The run continues if GitHub API requests fail.

## Run

```bash
python main.py --input resumes --output output/results.json
```

Offline run without GitHub requests:

```bash
python main.py --input resumes --output output/results.json --no-github
```

Run tests:

Run the test suite using the active Python environment:

```bash
python -m pytest -q
```

## Eligibility

A resume is eligible only when it explicitly mentions Python and has AI/LLM/agentic terminology in project-related text. Rejected candidates include reasons. This is a heuristic approximation and can miss equivalent terminology or mistake keyword mentions for genuine experience; manually inspect evidence.

## GitHub Enrichment

GitHub enrichment is optional and best-effort. When enabled, the system attempts to retrieve public profile or repository metadata for candidates with a detected GitHub username. API failures, unavailable profiles, and rate limits must not stop batch processing or affect eligibility. GitHub points depend on the evidence successfully retrieved; a missing profile or failed enrichment receives zero GitHub points.

## Scoring (100 points)

| Dimension | Maximum | Baseline approach |
|---|---:|---|
| AI/agentic/RAG depth | 40 | AI-related terms; additional signals for RAG/vector retrieval, agents/tool calling, evaluation/guardrails |
| Python/backend | 30 | Python evidence plus backend frameworks, APIs, and databases |
| Cloud/deployment/full-stack | 15 | Cloud, containers, deployment, CI/CD, full-stack signals |
| GitHub | 10 | Profile link and available public profile/repository metadata |
| Engineering depth | 5 | Testing, architecture, reliability, optimization, and observability signals |

Tutorial/shallow-project phrases incur a capped penalty. The weights and keyword lists are explicit in `src/screener.py` and should be calibrated against the assignment's intended evaluation. Scores are heuristic, not proof of ability.

## Output

`output/results.json` is a top-level JSON array following the assignment's candidate-object format. It contains eligible candidates first, ranked by score, followed by rejected candidates so each record can include `eligible` and `rejection_reason`. Eligible records have an integer `rank` and score fields; rejected records have `rank`, `total_score`, and `score_breakdown` set to `null` because rejected candidates are not scored or ranked. Each record includes `candidate_name`, `email`, `matched_skills`, `project_summary`, `github_username`, `github_url`, `github_summary`, `strengths`, `concerns`, and `eligibility_evidence`. Extra audit fields include `candidate_id`, `source_file`, `score_evidence`, `penalties`, `github_details`, and `processing_error`. The public `score_breakdown` reflects any shallow-project penalty deduction, so its category values sum to `total_score`; the original penalty explanation remains in `penalties`.

A sidecar file, `output/screening_report.json`, preserves batch counts and a compact rejected-candidate list without changing the required array shape of `results.json`. GitHub enrichment is best-effort: when a public profile is found, the program queries GitHub's public REST API for profile/repository/event signals. If no profile is linked in the resume, the API is unavailable, or rate limits intervene, the run continues and `github_summary` explains the missing data; unavailable data is not invented.

## Evaluation Note

The screening and ranking logic is a deterministic, keyword-based baseline rather than a validated hiring model. Eligibility decisions and scores can be affected by resume formatting, terminology, keyword stuffing, and extraction errors. Review the recorded evidence and score breakdown for each candidate before making any hiring decision.

## Design Decisions

- **No LLM dependency:** deterministic and cheap to run; every score can be traced to keyword evidence. The trade-off is weaker semantic understanding and possible false positives/negatives.
- **Best-effort extraction:** PDF, DOCX, and TXT are supported. A file-level failure is recorded instead of stopping the batch.
- **Hard filters before ranking:** only candidates passing both filters are scored/ranked.
- **GitHub is optional:** profile/API failures do not disqualify candidates; no profile means zero GitHub points.
- **No database or frontend:** output is a portable JSON artifact and the CLI is sufficient for batch evaluation.
- **Privacy:** resumes are processed locally. Only a GitHub username is sent to GitHub's public API when enrichment is enabled.

## If I Had More Time

1. Add OCR for scanned PDFs and improve layout-aware extraction.
2. Add semantic project evidence extraction and project-by-project scoring, with human-reviewed evaluation examples.
3. Cache GitHub requests and add explicit rate-limit/backoff handling.
4. Add calibration against labeled sample resumes and report precision/recall for eligibility filtering.
5. Expand tests for malformed PDFs, DOCX, API timeouts, rate limits, and scoring edge cases.
6. Add structured logs and a versioned JSON schema.

## Limitations

This baseline uses keywords and simple heuristics, not a validated hiring model. Resume formatting, synonyms, keyword stuffing, and incomplete GitHub data can change scores. It should support, not replace, human review.
