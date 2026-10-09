# Resume Screening and Ranking Baseline

A Python CLI that parses resumes, applies explicit eligibility filters, scores eligible candidates, optionally enriches GitHub profiles, and generates structured JSON results. It is designed as a transparent, reproducible baseline for the Kasparro SDE Intern assignment.

## Requirements

* Python 3.12.5
* Internet access only for optional GitHub enrichment

## Project Structure

```text
kasparro-resume-screening/
├── main.py
├── requirements.txt
├── README.md
├── src/
│   ├── screener.py
│   └── __init__.py
├── tests/
│   └── test_screener.py
├── resumes/                 # Local resume inputs (Not Uploaded due to sensitive data)
└── output/                  # Generated results (Not uploaded due to sensitive data)
```

## Setup

Create and activate a virtual environment.

```bash
python -m venv .venv
```

**Windows PowerShell:**

```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows Command Prompt:**

```bat
.venv\Scripts\activate.bat
```

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

Place the resume files in the `resumes/` directory. PDF, DOCX, and TXT files are supported. Scanned or image-only PDFs may be reported as processing errors because OCR is not included.

### Optional GitHub Token

GitHub enrichment is optional. To configure it, Create `.env` and add your token:

```dotenv
GITHUB_TOKEN=your_github_token_here
```

Never commit `.env` or expose your token. GitHub enrichment is best-effort, and API failures should not stop batch processing.

## Running the Application

Process resumes and write the candidate results to JSON:

```bash
python main.py --input resumes --output output/results.json
```

To run without making GitHub API requests:

```bash
python main.py --input resumes --output output/results.json --no-github
```

## Running Tests

Run the test suite using the active Python environment:

```bash
python -m pytest -q
```

## Eligibility Criteria

A resume is considered eligible only when both of the following conditions are met:

1. The resume explicitly mentions Python.
2. Project-related text contains AI, LLM, or agentic terminology.

Candidates who fail either condition are rejected, with reasons recorded in the output.

These rules are heuristic approximations. They may miss equivalent terminology or mistake keyword mentions for meaningful experience. Review the recorded evidence before relying on a screening decision.

## Scoring Methodology

Eligible candidates are scored using a weighted rubric with a maximum of 100 points.

| Dimension                   | Maximum Points | Baseline Approach                                                                                                     |
| --------------------------- | -------------: | --------------------------------------------------------------------------------------------------------------------- |
| AI/agentic/RAG depth        |             40 | AI-related terms, with additional signals for RAG, vector retrieval, agents, tool calling, evaluation, and guardrails |
| Python/backend              |             30 | Python evidence, backend frameworks, APIs, and databases                                                              |
| Cloud/deployment/full-stack |             15 | Cloud platforms, containers, deployment, CI/CD, and full-stack signals                                                |
| GitHub                      |             10 | Profile information and available public repository metadata                                                          |
| Engineering depth           |              5 | Testing, architecture, reliability, optimization, and observability                                                   |
| **Total**                   |        **100** | **Weighted score for eligible candidates**                                                                            |

Tutorial or shallow-project phrases incur a capped penalty. The scoring weights, keyword lists, and related rules are defined in `src/screener.py`.

The public score breakdown reflects any shallow-project penalty deduction, so its category values sum to the final total score. The original penalty explanation is retained in the `penalties` field.

The rubric is deterministic and explainable, but it is not a validated hiring model. Scores should be interpreted alongside the evidence recorded for each candidate.

## GitHub Enrichment

GitHub enrichment is optional and best-effort. When enabled, the program attempts to retrieve public profile or repository information for candidates with a detected GitHub username.

If a profile cannot be identified, the API is unavailable, or rate limits intervene, processing continues. The `github_summary` field should explain when information is unavailable, and missing information must not be invented.

GitHub points depend on the evidence successfully retrieved. A missing profile or failed enrichment receives zero GitHub points and does not affect eligibility.

## Output Format

The main output, `output/results.json`, is a top-level JSON array of candidate objects following the assignment's output format.

The array contains eligible candidates first, ranked by score, followed by rejected candidates.

### Eligible Candidates

Eligible candidate records include:

* An integer `rank`.
* `candidate_name` and `email`.
* `eligible` status.
* `total_score` and `score_breakdown`.
* `matched_skills` and `project_summary`.
* `github_username`, `github_url`, and `github_summary`.
* `strengths` and `concerns`.
* `eligibility_evidence`.

Additional audit fields include `candidate_id`, `source_file`, `score_evidence`, `penalties`, `github_details`, and `processing_error`.

### Rejected Candidates

Rejected candidates remain in the output so that eligibility decisions can be reviewed. Their records include the rejection reason and available supporting evidence.

The `rank`, `total_score`, and `score_breakdown` fields are set to `null` because rejected candidates are not scored or ranked.

### Batch Report

A separate file, `output/screening_report.json`, contains batch-level counts and a compact list of rejected candidates. This preserves the required top-level array structure of `results.json`.

## Design Decisions

### 1. No LLM Dependency

The core screening process is deterministic and inexpensive to run. Scores can be traced to explicit keyword evidence, making the system easier to debug and reproduce.

The trade-off is weaker semantic understanding, which can result in false positives and false negatives.

### 2. Best-Effort Resume Extraction

PDF, DOCX, and TXT formats are supported. File-level processing failures are recorded rather than intentionally stopping the entire batch.

OCR for scanned or image-only PDFs is not included.

### 3. Hard Filters Before Ranking

Eligibility checks are performed before scoring. Only candidates who pass both eligibility filters are ranked.

This separates minimum requirements from comparative scoring.

### 4. Optional GitHub Enrichment

GitHub enrichment is not required for the pipeline to run. Profile or API failures do not disqualify candidates, and unavailable GitHub evidence receives zero points.

### 5. CLI and JSON Outputs

A command-line interface and portable JSON outputs are sufficient for batch evaluation. A database or frontend is not required for the current baseline.

### 6. Privacy

Resumes are processed locally. When GitHub enrichment is enabled, the application may send a detected GitHub username to GitHub's public API.

Resume files, candidate-level results, environment files, and API tokens should be excluded from the public repository.

## Testing and Validation

Run the automated test suite before submission:

```bash
python -m pytest -q
```

Also run the pipeline against the supplied resume batch and inspect the generated outputs. Verify that eligible candidates have sensible score breakdowns and that rejected candidates have clear reasons.

Record the actual test results and batch counts from your final run rather than relying on earlier results.

## If I Had More Time

1. **Improve resume extraction:** Add OCR for scanned PDFs and improve layout-aware parsing.
2. **Add semantic project analysis:** Evaluate project descriptions more deeply and score evidence at the project level.
3. **Strengthen GitHub enrichment:** Add request caching, retry logic, rate-limit handling, and explicit backoff.
4. **Calibrate scoring:** Evaluate the rubric against a human-reviewed dataset and report precision and recall for eligibility filtering.
5. **Expand testing:** Cover malformed PDFs, DOCX parsing, API timeouts, rate limits, missing data, and scoring edge cases.
6. **Improve observability:** Add structured logs, a versioned JSON schema, and clearer per-resume processing diagnostics.

## Limitations

This implementation is a deterministic, keyword-based baseline rather than a validated hiring model. Resume formatting, synonyms, keyword stuffing, incomplete extraction, and missing GitHub data can affect scores and eligibility decisions.

The pipeline is intended to support and prioritize human review, not replace it. Reviewers should inspect the recorded evidence, score breakdowns, and concerns before making hiring decisions.
