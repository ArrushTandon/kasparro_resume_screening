from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pdfplumber
import requests
import logging

try:
    from docx import Document
except ImportError: 
    Document = None 

SKILL_TERMS = [
    "python", "java", "javascript", "typescript", "c++", "sql", "fastapi",
    "flask", "django", "spring boot", "node.js", "react", "postgresql",
    "mongodb", "redis", "docker", "kubernetes", "aws", "azure", "gcp",
    "rest api", "microservices", "git", "linux", "pytest", "pandas",
    "numpy", "scikit-learn", "tensorflow", "pytorch", "langchain",
    "llamaindex", "openai", "hugging face", "vector database", "faiss",
    "chromadb", "pinecone", "rag", "retrieval augmented generation",
    "llm", "large language model", "agents", "agentic", "embeddings",
]
AI_TERMS = [
    "llm", "large language model", "generative ai", "genai", "rag",
    "retrieval augmented generation", "langchain", "llamaindex", "agentic",
    "ai agent", "ai agents", "multi-agent", "multi agent", "tool calling",
    "function calling", "prompt engineering", "embeddings", "vector database",
    "vector store", "semantic search", "transformer", "hugging face",
    "openai api", "anthropic", "llama", "llm-powered", "llm powered",
]
PROJECT_MARKERS = ["project", "built", "developed", "implemented", "created", "deployed", "designed"]
IMPLEMENTATION_MARKERS = ["built", "developed", "implemented", "created", "deployed", "designed", "engineered", "integrated"]
SHALLOW_MARKERS = [
    # Explicit tutorial/clone language.
    "tutorial", "followed a tutorial", "youtube tutorial", "tutorial-based",
    "course project", "beginner project", "copied from", "clone tutorial",
    "hello world", "boilerplate project",
    # Explicitly shallow product/workflow language.
    "basic chatbot", "simple chatbot", "just an api wrapper", "api wrapper",
    "llm wrapper", "basic llm wrapper", "single api call", "one api call",
    "only calls the api", "only calls an api", "sends the prompt to the api",
    "sends a prompt to openai", "without retrieval", "no retrieval",
]
CLOUD_TERMS = ["aws", "azure", "gcp", "google cloud", "cloud run", "vercel", "render.com", "docker", "kubernetes", "ci/cd", "github actions", "deployed", "deployment", "full-stack", "full stack"]
BACKEND_TERMS = ["fastapi", "flask", "django", "spring boot", "rest api", "restful", "backend", "microservices", "postgresql", "mysql", "mongodb", "redis", "sqlalchemy", "api endpoint"]
ENGINEERING_TERMS = ["unit test", "pytest", "testing", "design pattern", "system design", "scalable", "optimization", "optimized", "caching", "concurrency", "logging", "monitoring", "error handling", "retry", "rate limit", "architecture"]


class FontBBoxWarningFilter(logging.Filter):
    """Suppress the known non-fatal missing FontBBox warning."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not (
            record.name == "pdfminer.pdffont"
            and "Could not get FontBBox from font descriptor" in record.getMessage()
        )


logging.getLogger("pdfminer.pdffont").addFilter(FontBBoxWarningFilter())


def extract_text(file_path: str | Path) -> str:
    """Extract text from PDF, DOCX, or TXT; raise a useful error for failures."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {path}")
    if suffix == ".pdf":
        chunks: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                chunks.append(page.extract_text() or "")
        text = "\n".join(chunks).strip()
    elif suffix == ".docx":
        if Document is None:
            raise RuntimeError("DOCX support requires python-docx. Install it with: pip install python-docx")
        doc = Document(path)
        text = "\n".join(p.text for p in doc.paragraphs).strip()
        for table in doc.tables:
            for row in table.rows:
                text += "\n" + " | ".join(cell.text for cell in row.cells)
        text = text.strip()
    elif suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    else:
        raise ValueError(f"Unsupported resume type '{suffix}'. Supported: PDF, DOCX, TXT")
    if not text:
        raise ValueError("No selectable text found. The file may be scanned; OCR is not included in this baseline.")
    return text


def _unique_matches(terms: list[str], text: str) -> list[str]:
    low = text.lower()
    found = []
    for term in terms:
        pattern = r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])"
        if re.search(pattern, low):
            found.append(term)
    return found


def extract_email(text: str) -> str | None:
    match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
    return match.group(0) if match else None


def extract_github(text: str) -> tuple[str | None, str | None]:
    urls = re.findall(r"https?://(?:www\.)?github\.com/[A-Za-z0-9-]+", text, re.I)
    for url in urls:
        parsed = urlparse(url.rstrip("/"))
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0].lower() not in {"features", "topics", "orgs", "settings", "login", "signup"}:
            username = parts[0]
            if username.lower() not in {"github"}:
                return username, f"https://github.com/{username}"
    # A plain @handle is not assumed to be a GitHub username because it is ambiguous.
    return None, None


def extract_name(text: str, file_path: str | Path) -> str | None:
    """Best-effort deterministic name extraction from a resume header.

    Handles names sharing a line with a phone number and names split around
    email/social-link labels. If no credible name is visible, returns None.
    """
    lines = [re.sub(r"\s+", " ", line).strip(" |\t•") for line in text.splitlines()]
    excluded_headings = {
        "resume", "curriculum vitae", "professional summary", "summary",
        "career objective", "objective", "profile", "personal profile",
        "contact", "contact information", "linkedin", "github", "phone",
        "email", "education", "experience", "work experience",
        "professional experience", "skills", "technical skills", "projects",
        "personal projects", "academic projects", "certifications", "achievements",
        "languages", "interests", "references", "technical expertise",
    }
    social_labels = {"linkedin", "github", "portfolio", "website", "email", "phone", "mobile"}

    def clean_header_line(line: str) -> str:
        # A pipe commonly separates the name/contact block from location text.
        line = line.split("|", 1)[0]
        value = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", " ", line, flags=re.I)
        value = re.sub(r"https?://\S+|www\.\S+", " ", value, flags=re.I)
        # Remove phone numbers while preserving any name that precedes them.
        value = re.sub(r"\+?\d[\d () .-]{7,}\d", " ", value)
        value = re.sub(r"\b(?:linkedin|github|portfolio|website|email|phone|mobile)\b", " ", value, flags=re.I)
        value = re.sub(r"[|•,:;()]+", " ", value)
        return re.sub(r"\s+", " ", value).strip(" -|\t")

    header_lines = lines[:8]
    first_heading = next((line.lower().strip(" :-|") for line in lines if line.strip()), "")
    # If the document starts inside a section (e.g. a cropped skills/summary
    # block), don't mislabel its first content line as the candidate's name.
    if first_heading in excluded_headings - {"resume", "curriculum vitae", "contact", "contact information"}:
        return None
    for raw in header_lines:
        candidate = clean_header_line(raw)
        low = candidate.lower().strip(" :-|")
        if not candidate or low in excluded_headings or len(candidate) > 65:
            continue
        words = candidate.split()
        if 2 <= len(words) <= 5 and all(re.fullmatch(r"[A-Za-z][A-Za-z'.-]*", word) for word in words):
            if not any(term in low for term in ("developer", "engineer", "student", "summary", "experience", "skills")):
                return candidate

    # Some PDF layouts split a name across contact-header lines, e.g. first
    # name beside phone, surname beside LinkedIn/GitHub labels.
    single_tokens: list[str] = []
    for raw in header_lines:
        candidate = clean_header_line(raw)
        if not candidate or candidate.lower() in excluded_headings:
            continue
        words = candidate.split()
        if len(words) == 1 and re.fullmatch(r"[A-Za-z][A-Za-z'.-]{1,24}", words[0]):
            if words[0].lower() not in social_labels:
                single_tokens.append(words[0])
        elif len(words) > 1 and all(re.fullmatch(r"[A-Za-z][A-Za-z'.-]*", w) for w in words):
            if any(term in raw.lower() for term in social_labels):
                single_tokens.append(words[0])
    if len(single_tokens) >= 2:
        return f"{single_tokens[0]} {single_tokens[1]}"

    stem = Path(file_path).stem.replace("_", " ").replace("-", " ").strip()
    if re.fullmatch(r"candidate\s*\d+", stem, re.I):
        return None
    return stem or None


def extract_projects(text: str) -> list[str]:
    """Collect project-like lines/paragraphs as explainable evidence snippets."""
    lines = [re.sub(r"\s+", " ", line).strip(" •\t-") for line in text.splitlines()]
    snippets: list[str] = []
    project_section = False
    for line in lines:
        if not line:
            continue
        low = line.lower()
        if re.match(r"^(projects?|personal projects?|academic projects?|selected projects?)\s*:?$", low):
            project_section = True
            continue
        if project_section and re.match(r"^(education|experience|work experience|skills|certifications|achievements|publications)\s*:?$", low):
            project_section = False
        if project_section or any(marker in low for marker in PROJECT_MARKERS):
            if len(line) >= 28 and line not in snippets:
                snippets.append(line[:400])
    # If PDF text has few line breaks, retain sentences mentioning project/build verbs.
    if not snippets:
        for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)):
            low = sentence.lower()
            if len(sentence) >= 35 and any(marker in low for marker in PROJECT_MARKERS):
                snippets.append(sentence[:400])
    return snippets[:30]


def extract_candidate(text: str, file_path: str | Path) -> dict[str, Any]:
    skills = _unique_matches(SKILL_TERMS, text)
    github_username, github_url = extract_github(text)
    return {
        "candidate_id": Path(file_path).stem,
        "source_file": str(file_path),
        "name": extract_name(text, file_path),
        "email": extract_email(text),
        "skills": skills,
        "projects": extract_projects(text),
        "github_username": github_username,
        "github_url": github_url,
        "_raw_text": text,
    }


def evaluate_eligibility(candidate: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    text = candidate.get("_raw_text", "")
    low = text.lower()
    reasons: list[str] = []
    evidence: list[str] = []
    has_python = bool(re.search(r"(?<![a-z0-9])python(?![a-z0-9])", low))
    if has_python:
        evidence.append("Python mentioned in resume")
    else:
        reasons.append("No explicit Python evidence found")
    project_evidence = candidate.get("projects", [])
    # AI evidence must occur in project evidence, not only in a skills list or summary.
    project_text = " ".join(project_evidence).lower()
    ai_terms = _unique_matches(AI_TERMS, project_text)
    # Require AI terminology in an extracted project description with implementation context.
    has_project_context = bool(project_evidence) and any(
        marker in project_text for marker in IMPLEMENTATION_MARKERS
    )
    has_meaningful_ai_project = bool(ai_terms) and has_project_context
    if has_meaningful_ai_project:
        evidence.append("AI/LLM/agentic terminology found in project-related text: " + ", ".join(ai_terms[:8]))
    else:
        reasons.append("No clear AI/LLM/agentic project evidence found")
    return has_python and has_meaningful_ai_project, reasons, evidence


def github_enrichment(username: str | None, timeout: float = 5.0) -> dict[str, Any]:
    """Fetch public GitHub activity/repository signals; fail gracefully per candidate."""
    if not username:
        return {"available": False, "reason": "No GitHub profile URL found in resume"}

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "kasparro-resume-screening"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        profile_response = requests.get(
            f"https://api.github.com/users/{username}", headers=headers, timeout=timeout
        )
        if profile_response.status_code == 404:
            return {"available": False, "reason": "GitHub user not found", "username": username}
        profile_response.raise_for_status()
        profile = profile_response.json()

        repos_response = requests.get(
            f"https://api.github.com/users/{username}/repos?sort=updated&per_page=100&type=owner",
            headers=headers, timeout=timeout,
        )
        warnings: list[str] = []
        if not repos_response.ok:
            warnings.append(f"Repository endpoint failed: HTTP {repos_response.status_code}")
        repos = repos_response.json() if repos_response.ok else []
        if not isinstance(repos, list):
            repos = []

        events_response = requests.get(
            f"https://api.github.com/users/{username}/events/public?per_page=100",
            headers=headers, timeout=timeout,
        )
        if not events_response.ok:
            warnings.append(f"Public events endpoint failed: HTTP {events_response.status_code}")
        events = events_response.json() if events_response.ok else []
        if not isinstance(events, list):
            events = []

        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        cutoff_activity = now - timedelta(days=90)
        recent_events = []
        for event in events:
            if not isinstance(event, dict):
                continue
            try:
                created = datetime.fromisoformat(event.get("created_at", "").replace("Z", "+00:00"))
                if created >= cutoff_activity:
                    recent_events.append(event)
            except (ValueError, TypeError):
                continue

        cutoff_repo = now - timedelta(days=180)
        recently_updated = []
        relevant_repos = []
        relevance_terms = ("python", "ai", "llm", "rag", "agent", "machine learning", "ml", "fastapi")
        for repo in repos:
            if not isinstance(repo, dict) or repo.get("fork"):
                continue
            try:
                updated = datetime.fromisoformat(repo.get("updated_at", "").replace("Z", "+00:00"))
                if updated >= cutoff_repo:
                    recently_updated.append(repo)
            except (ValueError, TypeError):
                pass
            searchable = " ".join(str(repo.get(k) or "") for k in ("name", "description", "language")).lower()
            if any(term in searchable for term in relevance_terms):
                relevant_repos.append(repo)

        # Explainable 0–5 activity and 0–5 repository scores, as requested in the assignment.
        activity_score = min(5, len(recent_events))
        repo_score = min(3, len(recently_updated)) + (2 if relevant_repos else 0)
        repo_score = min(5, repo_score)
        languages = sorted({r.get("language") for r in repos if isinstance(r, dict) and r.get("language")})
        return {
            "available": True,
            "username": username,
            "profile_url": profile.get("html_url", f"https://github.com/{username}"),
            "public_repos": profile.get("public_repos"),
            "followers": profile.get("followers"),
            "account_created": profile.get("created_at"),
            "languages_in_recent_repos": languages,
            "recent_repositories": [
                {"name": r.get("name"), "url": r.get("html_url"), "language": r.get("language"), "description": r.get("description"), "updated_at": r.get("updated_at")}
                for r in repos[:10] if isinstance(r, dict)
            ],
            "recent_public_events_90d": len(recent_events),
            "recently_updated_repositories_180d": len(recently_updated),
            "relevant_repositories": len(relevant_repos),
            "activity_score": activity_score,
            "repository_score": repo_score,
            "enrichment_warnings": warnings,
            "score_method": "0-5 recent public events in 90 days + 0-5 recently updated/relevant repositories",
        }
    except (requests.RequestException, ValueError, TypeError) as exc:
        return {"available": False, "reason": f"GitHub API unavailable: {type(exc).__name__}", "username": username}


def score_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    text = candidate.get("_raw_text", "")
    low = text.lower()
    projects = candidate.get("projects", [])
    project_text = " ".join(projects).lower()
    combined = low + " " + project_text
    evidence: dict[str, list[str]] = {}

    # AI depth is scored from project evidence, not merely a framework name in Skills.
    ai_terms = _unique_matches(AI_TERMS, project_text)
    ai_score = min(40, len(ai_terms) * 5)
    if any(term in project_text for term in ["rag", "retrieval augmented generation", "vector database", "vector store", "embeddings", "semantic search"]):
        ai_score = min(40, ai_score + 8)
    if any(term in project_text for term in ["agentic", "multi-agent", "multi agent", "tool calling", "function calling"]):
        ai_score = min(40, ai_score + 7)
    if any(term in project_text for term in ["evaluation", "evals", "benchmark", "hallucination", "guardrail", "reranking", "re-ranking"]):
        ai_score = min(40, ai_score + 5)
    evidence["ai_agentic_rag_depth"] = ai_terms[:12]

    backend_terms = _unique_matches(BACKEND_TERMS, combined)
    python_evidence = bool(re.search(r"(?<![a-z0-9])python(?![a-z0-9])", low))
    backend_score = min(30, len(backend_terms) * 4 + (8 if python_evidence else 0))
    evidence["python_backend"] = (["Python"] if python_evidence else []) + backend_terms[:8]

    cloud_terms = _unique_matches(CLOUD_TERMS, combined)
    cloud_score = min(15, len(cloud_terms) * 3)
    evidence["cloud_deployment_fullstack"] = cloud_terms[:8]

    github = candidate.get("github", {})
    if github.get("available"):
        github_score = min(5, max(0, int(github.get("activity_score", 0)))) + min(
            5, max(0, int(github.get("repository_score", 0)))
        )
    else:
        # A URL alone is not evidence of activity or maintained repositories.
        github_score = 0
    evidence["github"] = [candidate["github_url"]] if candidate.get("github_url") else []
    if github.get("available"):
        evidence["github"].append(f"{github.get('public_repos', 0)} public repositories; languages: {', '.join(github.get('languages_in_recent_repos', [])) or 'not reported'}")

    engineering_terms = _unique_matches(ENGINEERING_TERMS, combined)
    engineering_score = min(5, len(engineering_terms))
    evidence["engineering_depth"] = engineering_terms[:8]

    penalties: list[dict[str, Any]] = []
    penalty = 0
    shallow = _unique_matches(SHALLOW_MARKERS, project_text)
    # Infer a thin wrapper only when the project explicitly describes a basic
    # prompt/API chatbot and lacks retrieval, state, workflow, data, or evaluation.
    wrapper_hints = _unique_matches(
        ["openai api", "llm api", "chat completion api", "prompt-based chatbot", "prompt based chatbot"],
        project_text,
    )
    meaningful_workflow = _unique_matches(
        ["rag", "retrieval", "embeddings", "vector store", "vector database", "tool calling",
         "multi-agent", "multi agent", "workflow", "state management", "database", "evaluation",
         "guardrail", "reranking", "data processing", "authentication", "caching",
         "pipeline", "orchestration", "log analyser", "log analyzer", "root cause",
         "failure hook", "suggests a fix", "self-correction", "self correction",
         "human-in-the-loop", "human in the loop", "database execution", "multi-step",
         "multi step", "monitoring", "retry", "rate limiting", "structured output"],
        project_text,
    )
    if wrapper_hints and not meaningful_workflow:
        shallow.extend(term for term in wrapper_hints if term not in shallow)
    shallow = list(dict.fromkeys(shallow))
    if shallow:
        penalty = min(15, 5 * len(shallow))
        penalties.append({"reason": "Shallow/tutorial-style project signal", "matched_terms": shallow, "points": -penalty})
    total_before_penalty = ai_score + backend_score + cloud_score + github_score + engineering_score
    total = max(0, min(100, total_before_penalty - penalty))
    return {
        "total": total,
        "max_total": 100,
        "breakdown": {
            "ai_agentic_rag_depth": {"score": ai_score, "max": 40},
            "python_backend": {"score": backend_score, "max": 30},
            "cloud_deployment_fullstack": {"score": cloud_score, "max": 15},
            "github": {"score": github_score, "max": 10},
            "engineering_depth": {"score": engineering_score, "max": 5},
        },
        "penalties": penalties,
        "evidence": evidence,
    }


def screen_one(file_path: str | Path, use_github: bool = True) -> dict[str, Any]:
    path = Path(file_path)
    base: dict[str, Any] = {
        "candidate_id": path.stem,
        "source_file": str(path),
        "name": None,
        "email": None,
        "skills": [],
        "projects": [],
        "github_username": None,
        "github_url": None,
        "eligible": False,
        "rejection_reasons": [],
        "eligibility_evidence": [],
        "score": None,
        "github": {"available": False, "reason": "Not queried"},
        "processing_error": None,
    }
    try:
        text = extract_text(path)
        candidate = extract_candidate(text, path)
        base.update({k: v for k, v in candidate.items() if k != "_raw_text"})
        base["project_summary"] = _select_project_summary(candidate.get("projects", []))
        eligible, reasons, eligibility_evidence = evaluate_eligibility(candidate)
        base["eligible"] = eligible
        base["rejection_reasons"] = reasons
        base["eligibility_evidence"] = eligibility_evidence
        if use_github:
            base["github"] = github_enrichment(candidate.get("github_username"))
        if eligible:
            candidate["github"] = base["github"]
            base["score"] = score_candidate(candidate)
    except Exception as exc:  # malformed files should not stop the batch
        base["rejection_reasons"] = [f"Resume could not be processed: {type(exc).__name__}: {exc}"]
        base["processing_error"] = f"{type(exc).__name__}: {exc}"
    return base



def _select_project_summary(projects: list[str]) -> str:
    """Create a readable deterministic summary from extracted project fragments.

    PDF extraction often splits a sentence across consecutive lines. Prefer a
    complete AI-related implementation sentence; otherwise join nearby project
    fragments and avoid ending on a dangling conjunction/preposition.
    """
    if not projects:
        return "No project summary extracted"

    def clean(value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip(" |:-•·\uf0b7◦▪●")
        # PDF bullet glyphs can be embedded in a single extracted line; keep
        # only the first bullet's text instead of merging multiple projects.
        value = re.split(r"\s+[\uf0b7◦▪●•]\s*", value, maxsplit=1)[0]
        # An unmatched opening parenthesis often signals that extraction ran
        # into the next heading/bullet rather than finishing the sentence.
        if value.count("(") > value.count(")"):
            value = value.split("(", 1)[0].rstrip(" ,;:-")
        return re.sub(r"\s+([,.;:])", r"\1", value)

    def is_good_start(value: str) -> bool:
        low = value.lower().strip()
        return not low.startswith(("and ", "or ", "which ", "that ", "using ", "with ", "to ", "for ", "of ", "including "))

    def is_complete(value: str) -> bool:
        low = value.lower().rstrip()
        return bool(value.endswith((".", "!", "?"))) and not low.endswith((" and", " or", "using", "with", "to", "for", "including", "such as", "by"))

    normalized = [clean(p) for p in projects if clean(p)]
    ai_indices = [i for i, item in enumerate(normalized)
                  if _unique_matches(AI_TERMS, item)
                  and any(marker in item.lower() for marker in IMPLEMENTATION_MARKERS)]
    candidate_indices = ai_indices or list(range(len(normalized)))

    # A line-ending full stop is not enough: PDF extraction can split a sentence
    # or leave a bullet that looks complete but ends in a grammatical fragment.
    bad_tails = {"and", "or", "using", "with", "to", "for", "of", "by", "in", "on",
                 "across", "while", "that", "which", "from", "the", "a", "an", "including",
                 "enabling", "supporting", "combining", "providing", "formatted", "leveraging"}
    complete = [normalized[i] for i in candidate_indices
                if len(normalized[i]) >= 45 and is_good_start(normalized[i]) and is_complete(normalized[i])
                and normalized[i].rstrip(".!? ").split()[-1].lower().strip(",;:") not in bad_tails]
    if complete:
        selected = max(complete, key=len)
        return selected if len(selected) <= 280 else selected[:277].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."

    # Prefer a project sentence with implementation details, then extend it with
    # adjacent PDF fragments until the sentence is plausibly complete.
    index = max(candidate_indices, key=lambda i: (len(normalized[i]), i in ai_indices))
    pieces = [normalized[index]]
    for following in normalized[index + 1:index + 5]:
        current_tail = pieces[-1].rstrip(".!? ").split()[-1].lower().strip(",;:") if pieces[-1].split() else ""
        # A new implementation verb normally starts a new bullet/sentence; do
        # not glue it onto an unfinished previous sentence.
        if current_tail in bad_tails | {"formatted", "interconnected", "specialized", "leveraging"} and re.match(
            r"^(built|developed|implemented|designed|integrated|deployed|engineered|architected|created|automated)\b",
            following, re.I,
        ):
            break
        # Stop only on explicit project headings; ordinary descriptions often
        # contain hyphenated words such as "end-to-end" or "Flask-based".
        if re.match(r"^project\s*\d+\b", following, re.I) or "[github]" in following.lower() or re.search(r"\b20\d{2}\s*$", following) or (
            len(following) <= 90 and (" | " in following or " — " in following)
            and not following.lower().startswith(("built ", "developed ", "implemented ", "designed ", "integrated ", "deployed ", "engineered "))
        ):
            break
        if len(" ".join(pieces)) >= 230:
            break
        pieces.append(following)
        joined = clean(" ".join(pieces))
        tail = joined.rstrip(".!? ").split()[-1].lower().strip(",;:")
        if is_complete(joined) and tail not in bad_tails:
            break
    selected = clean(" ".join(pieces))
    if not is_good_start(selected) and index > 0:
        selected = clean(normalized[index - 1] + " " + selected)

    # If several extracted lines were concatenated, discard an opening fragment
    # before the last sentence-like implementation clause.
    sentences = re.split(r"(?<=[.!?])\s+", selected)
    implementation_sentences = [part for part in sentences
        if any(marker in part.lower() for marker in IMPLEMENTATION_MARKERS)
        and _unique_matches(AI_TERMS, part)]
    if len(sentences) > 1 and implementation_sentences:
        selected = max(implementation_sentences, key=len).strip()

    selected = selected.rstrip(" .!?")
    tail = selected.split()[-1].lower().strip(",;:") if selected.split() else ""
    if tail in bad_tails:
        selected = re.sub(r"\s+(?:(?:and|or)\s+)?(?:and|or|using|with|to|for|of|by|in|on|across|while|that|which|from|including|enabling|supporting|combining|providing)$", "", selected, flags=re.I).rstrip(" ,;:-")
        tail = selected.split()[-1].lower().strip(",;:") if selected.split() else ""
    if tail in {"formatted", "interconnected", "specialized", "including", "enabling", "supporting", "combining", "providing", "leveraging"} and "," in selected:
        selected = selected.rsplit(",", 1)[0].rstrip(" ,;:-")
    if len(selected) > 280:
        selected = selected[:277].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."
    selected = selected.rstrip(" ,;:-")
    if selected and not selected.endswith((".", "!", "?", "...")):
        selected += "."
    return selected or "Project evidence was extracted, but a readable summary could not be generated"


def _github_summary(github: dict[str, Any], username: str | None) -> str:
    """Return a concise, human-readable summary without inventing unavailable data."""
    if not username:
        return "No GitHub profile URL found in resume; activity could not be assessed."
    if not github.get("available"):
        reason = github.get("reason", "GitHub enrichment unavailable")
        return f"Profile identified ({username}), but public data was unavailable: {reason}."
    repos = github.get("public_repos", 0)
    events = github.get("recent_public_events_90d", 0)
    updated = github.get("recently_updated_repositories_180d", 0)
    relevant = github.get("relevant_repositories", 0)
    languages = ", ".join(github.get("languages_in_recent_repos", [])[:5])
    parts = [f"{repos} public repositories", f"{events} public events in the last 90 days",
             f"{updated} repositories updated in the last 180 days"]
    if relevant:
        parts.append(f"{relevant} repositories with AI/Python-related signals")
    if languages:
        parts.append(f"languages include {languages}")
    return "; ".join(parts) + "."


def _public_candidate_record(candidate: dict[str, Any]) -> dict[str, Any]:
    """Convert internal scoring/extraction fields to the assignment's JSON schema."""
    score = candidate.get("score") or {}
    internal_breakdown = score.get("breakdown", {})
    score_breakdown = {
        "ai_project_depth": internal_breakdown.get("ai_agentic_rag_depth", {}).get("score", 0),
        "python_backend": internal_breakdown.get("python_backend", {}).get("score", 0),
        "cloud_fullstack": internal_breakdown.get("cloud_deployment_fullstack", {}).get("score", 0),
        "github": internal_breakdown.get("github", {}).get("score", 0),
        "engineering_depth": internal_breakdown.get("engineering_depth", {}).get("score", 0),
    } if candidate.get("eligible") else None
    if score_breakdown is not None:
        # Keep the public breakdown internally consistent with total_score: shallow-project
        # penalties are deducted from category points in a documented, deterministic order.
        penalty_points = sum(max(0, -int(p.get("points", 0))) for p in score.get("penalties", []))
        for key in ("ai_project_depth", "python_backend", "cloud_fullstack", "github", "engineering_depth"):
            deduction = min(score_breakdown[key], penalty_points)
            score_breakdown[key] -= deduction
            penalty_points -= deduction
            if penalty_points == 0:
                break

    strengths: list[str] = []
    concerns: list[str] = []
    if candidate.get("eligible"):
        labels = (
            ("ai_project_depth", "Strong AI/agentic project evidence", 0.60, 40),
            ("python_backend", "Python/backend experience", 0.60, 30),
            ("cloud_fullstack", "Cloud/deployment/full-stack experience", 0.60, 15),
            ("github", "Public GitHub activity and repository evidence", 0.60, 10),
            ("engineering_depth", "Engineering quality signals", 0.60, 5),
        )
        for key, label, threshold, maximum in labels:
            if score_breakdown[key] >= max(1, int(maximum * threshold)):
                strengths.append(label)
            elif key in {"ai_project_depth", "python_backend"}:
                concerns.append(f"Limited evidence for {label.lower()}")
        concerns.extend(p.get("reason", "Scoring penalty applied") for p in score.get("penalties", []))
        if candidate.get("github_username") and not candidate.get("github", {}).get("available"):
            concerns.append("GitHub profile found, but public activity could not be verified")
        elif not candidate.get("github_username"):
            concerns.append("No GitHub profile link found in the resume")
    else:
        concerns.extend(candidate.get("rejection_reasons", []))

    github = candidate.get("github", {})
    profile_url = github.get("profile_url") or candidate.get("github_url")
    result = {
        "rank": candidate.get("rank") if candidate.get("eligible") else None,
        "candidate_name": candidate.get("name") or "Unknown",
        "eligible": bool(candidate.get("eligible")),
        "email": candidate.get("email"),
        "total_score": score.get("total") if candidate.get("eligible") else None,
        "score_breakdown": score_breakdown,
        "matched_skills": candidate.get("skills", []),
        "project_summary": candidate.get("project_summary", "No project summary extracted"),
        "github_username": candidate.get("github_username") or github.get("username"),
        "github_url": profile_url,
        "github_summary": _github_summary(github, candidate.get("github_username")),
        "strengths": strengths,
        "concerns": list(dict.fromkeys(concerns)),
        "eligibility_evidence": candidate.get("eligibility_evidence", []),
        "rejection_reason": "; ".join(candidate.get("rejection_reasons", [])) or None,
        # Extra audit fields make results traceable without changing the requested fields.
        "candidate_id": candidate.get("candidate_id"),
        "source_file": candidate.get("source_file"),
        "score_evidence": score.get("evidence", {}) if candidate.get("eligible") else {},
        "penalties": score.get("penalties", []) if candidate.get("eligible") else [],
        "github_details": github,
        "processing_error": candidate.get("processing_error"),
    }
    return result


def screen_directory(resume_dir: str | Path, use_github: bool = True) -> list[dict[str, Any]]:
    """Screen a directory and return a top-level JSON-array-ready list.

    Eligible candidates are ranked by score. Rejected candidates are included after
    them with rank/score set to null so eligibility and rejection reasons remain auditable.
    """
    folder = Path(resume_dir)
    if not folder.exists() or not folder.is_dir():
        raise NotADirectoryError(f"Resume directory does not exist: {folder}")
    supported = {".pdf", ".docx", ".txt"}
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in supported)
    results = [screen_one(path, use_github=use_github) for path in files]
    eligible = [r for r in results if r["eligible"]]
    eligible.sort(key=lambda r: (r["score"]["total"] if r["score"] else 0, r["candidate_id"]), reverse=True)
    for rank, candidate in enumerate(eligible, start=1):
        candidate["rank"] = rank
    rejected = [r for r in results if not r["eligible"]]
    rejected.sort(key=lambda r: (r.get("name") or "", r.get("candidate_id") or ""))
    return [_public_candidate_record(candidate) for candidate in eligible + rejected]


def build_batch_report(candidates: list[dict[str, Any]], input_directory: str | Path) -> dict[str, Any]:
    """Build optional sidecar summary so the required results.json stays an array."""
    return {
        "metadata": {
            "system": "Kasparro Resume Screening Baseline",
            "scoring_version": "1.3",
            "scoring_note": "Deterministic, explainable keyword-based baseline with best-effort public GitHub enrichment. No paid LLM/API is required; manually review evidence and scores.",
            "input_directory": str(input_directory),
            "files_processed": len(candidates),
        },
        "batch_summary": {
            "total_processed": len(candidates),
            "eligible_count": sum(c["eligible"] for c in candidates),
            "rejected_count": sum(not c["eligible"] for c in candidates),
            "processing_error_count": sum(bool(c.get("processing_error")) for c in candidates),
            "github_profiles_found": sum(bool(c.get("github_url")) for c in candidates),
            "github_profiles_enriched": sum(bool(c.get("github_details", {}).get("available")) for c in candidates),
        },
        "rejected_candidates": [
            {"candidate_id": c.get("candidate_id"), "candidate_name": c.get("candidate_name"),
             "email": c.get("email"), "rejection_reason": c.get("rejection_reason"),
             "eligibility_evidence": c.get("eligibility_evidence", [])}
            for c in candidates if not c["eligible"]
        ],
    }
