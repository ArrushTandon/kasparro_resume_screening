from pathlib import Path

from src.screener import (
    evaluate_eligibility,
    extract_email,
    extract_github,
    extract_projects,
    extract_text,
    score_candidate,
    extract_name,
)


def test_extract_email():
    assert extract_email("Contact me at test.person+job@example.com") == "test.person+job@example.com"
    assert extract_email("no email here") is None


def test_extract_github():
    assert extract_github("GitHub: https://github.com/octocat") == ("octocat", "https://github.com/octocat")
    assert extract_github("No profile") == (None, None)


def test_eligibility_requires_python_and_ai_project():
    candidate = {
        "_raw_text": "Python developer. Projects: Built a RAG question-answering system using embeddings.",
        "projects": ["Built a RAG question-answering system using embeddings."],
    }
    eligible, reasons, evidence = evaluate_eligibility(candidate)
    assert eligible is True
    assert reasons == []
    assert evidence


def test_eligibility_rejects_missing_python():
    candidate = {
        "_raw_text": "Projects: Built a RAG question-answering system using embeddings.",
        "projects": ["Built a RAG question-answering system using embeddings."],
    }
    eligible, reasons, _ = evaluate_eligibility(candidate)
    assert eligible is False
    assert any("Python" in reason for reason in reasons)


def test_score_is_bounded_and_has_expected_categories():
    candidate = {
        "_raw_text": "Python FastAPI REST API Docker GitHub Actions pytest RAG embeddings evaluation",
        "projects": ["Built and deployed a RAG application using embeddings and evaluation."],
        "github_username": None,
        "github_url": None,
        "github": {"available": False},
    }
    result = score_candidate(candidate)
    assert 0 <= result["total"] <= 100
    assert sum(item["max"] for item in result["breakdown"].values()) == 100
    assert "evidence" in result


def test_extract_text_txt(tmp_path: Path):
    resume = tmp_path / "resume.txt"
    resume.write_text("Python developer", encoding="utf-8")
    assert extract_text(resume) == "Python developer"


def test_extract_projects():
    text = "Projects:\nBuilt a retrieval augmented generation chatbot for internal documents.\nEducation:\nB.Tech"
    projects = extract_projects(text)
    assert any("retrieval augmented generation" in p.lower() for p in projects)


def test_extract_name_skips_professional_summary(): 
    text = "PROFESSIONAL SUMMARY\nPython developer with AI experience" 
    assert extract_name(text, "candidate_35.pdf") is None 

def test_extract_name_skips_skills_heading(): 
    text = "TECHNICAL SKILLS\nPython, FastAPI, SQL" 
    assert extract_name(text, "candidate_01.pdf") is None 

def test_extract_name_preserves_valid_name(): 
    text = "V Sree Raghu Vardhan\nPython Developer" 
    assert extract_name(text, "candidate_30.pdf") == "V Sree Raghu Vardhan"

def test_eligibility_rejects_ai_keyword_only_in_skills_or_summary():
    candidate = {
        "_raw_text": "Python developer. Skills: LangChain, RAG. Projects: Built a normal inventory CRUD application using Flask.",
        "projects": ["Built a normal inventory CRUD application using Flask."],
    }
    eligible, reasons, _ = evaluate_eligibility(candidate)
    assert eligible is False
    assert any("AI/LLM/agentic" in reason for reason in reasons)


def test_github_url_alone_gets_no_github_points():
    candidate = {
        "_raw_text": "Python FastAPI RAG",
        "projects": ["Built a RAG service using Python and FastAPI."],
        "github_username": "octocat",
        "github_url": "https://github.com/octocat",
        "github": {"available": False, "reason": "API timeout"},
    }
    result = score_candidate(candidate)
    assert result["breakdown"]["github"]["score"] == 0


def test_github_score_uses_activity_and_repository_scores():
    candidate = {
        "_raw_text": "Python FastAPI RAG",
        "projects": ["Built a RAG service using Python and FastAPI."],
        "github_username": "octocat",
        "github_url": "https://github.com/octocat",
        "github": {"available": True, "activity_score": 3, "repository_score": 4},
    }
    result = score_candidate(candidate)
    assert result["breakdown"]["github"]["score"] == 7


def test_deterministic_shallow_project_penalty_is_applied():
    candidate = {
        "_raw_text": "Python developer. Built a simple chatbot using an API wrapper.",
        "projects": ["Built a simple chatbot using an API wrapper."],
        "github": {"available": False},
    }
    result = score_candidate(candidate)
    assert result["penalties"]
    assert result["total"] < sum(part["score"] for part in result["breakdown"].values())


def test_project_summary_prefers_ai_project_and_normalizes_whitespace():
    from src.screener import _select_project_summary

    projects = [
        "Built an RBAC platform for tenant management",
        "Built a RAG chatbot\nusing embeddings and vector search",
    ]
    summary = _select_project_summary(projects)
    assert "RAG" in summary
    assert "\n" not in summary


def test_eligibility_does_not_accept_ai_title_without_implementation():
    candidate = {
        "_raw_text": "Python developer. Projects: RAG Project for documents.",
        "projects": ["RAG Project for documents."],
    }
    eligible, _, _ = evaluate_eligibility(candidate)
    assert eligible is False


def test_extract_name_from_split_contact_header():
    text = "Prathamesh +91 73490 41840 | Bengaluru, Karnataka\nprathameshpatil330@gmail.com\nPatil LinkedIn | Github\nPROFESSIONAL SUMMARY"
    assert extract_name(text, "candidate_35.pdf") == "Prathamesh Patil"


def test_shallow_openai_wrapper_gets_penalty_but_workflow_does_not():
    shallow = {
        "_raw_text": "Python developer. Projects: Built a prompt-based chatbot using the OpenAI API.",
        "projects": ["Built a prompt-based chatbot using the OpenAI API."],
        "github": {"available": False},
    }
    meaningful = {
        "_raw_text": "Python developer. Projects: Integrated the OpenAI API into a multi-step workflow with retrieval, evaluation, and retry handling.",
        "projects": ["Integrated the OpenAI API into a multi-step workflow with retrieval, evaluation, and retry handling."],
        "github": {"available": False},
    }
    assert score_candidate(shallow)["penalties"]
    assert score_candidate(meaningful)["penalties"] == []


def test_summary_joins_fragments_and_does_not_end_with_connector():
    from src.screener import _select_project_summary

    summary = _select_project_summary([
        "Built a Graph RAG conversational assistant using Neo4j and LangChain, enabling users to query interconnected",
        "knowledge graph entities and retrieve grounded answers with source context.",
    ])
    assert "interconnected knowledge graph entities" in summary
    assert not summary.rstrip(".").split()[-1].lower() in {"and", "or", "using", "with", "to", "for", "of", "by", "including"}


def test_malformed_pdf_is_recorded_without_crashing_batch(tmp_path: Path):
    from src.screener import screen_one

    malformed = tmp_path / "broken.pdf"
    malformed.write_bytes(b"this is not a valid PDF")
    result = screen_one(malformed, use_github=False)
    assert result["eligible"] is False
    assert result["processing_error"]
    assert result["rejection_reasons"]


def test_summary_does_not_treat_hyphenated_description_as_new_heading():
    from src.screener import _select_project_summary

    summary = _select_project_summary([
        "Built an interactive Chainlit conversational interface that accepts user questions, invokes the Graph RAG pipeline, and returns formatted",
        "Deployed the end-to-end conversational application on AWS EC2, providing a cloud-hosted interface for natural-language exploration.",
    ])
    assert "Graph RAG pipeline." in summary
    assert "formatted." not in summary


def test_github_api_timeout_is_recorded_and_does_not_raise(monkeypatch):
    import requests
    from src.screener import github_enrichment

    def fail_request(*args, **kwargs):
        raise requests.Timeout("simulated timeout")

    monkeypatch.setattr(requests, "get", fail_request)
    result = github_enrichment("octocat", timeout=0.01)
    assert result["available"] is False
    assert "Timeout" in result["reason"]


def test_extract_text_docx(tmp_path: Path):
    import pytest
    from src.screener import Document

    if Document is None:
        pytest.skip("python-docx is not installed")
    path = tmp_path / "resume.docx"
    doc = Document()
    doc.add_paragraph("Python developer with RAG project experience")
    doc.save(path)
    assert "Python developer" in extract_text(path)


def test_screen_directory_returns_assignment_array_schema(tmp_path: Path):
    import json
    from src.screener import screen_directory

    (tmp_path / "eligible.txt").write_text(
        "Asha Rao\nasha@example.com\nPython FastAPI PostgreSQL Docker\n"
        "GitHub: https://github.com/octocat\nProjects:\n"
        "Built a stateful agentic RAG workflow with retrieval, tool calling, and evaluation.",
        encoding="utf-8",
    )
    (tmp_path / "rejected.txt").write_text(
        "Ravi Kumar\nravi@example.com\nJava developer\nProjects:\n"
        "Built a basic inventory CRUD application.",
        encoding="utf-8",
    )
    results = screen_directory(tmp_path, use_github=False)
    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0]["eligible"] is True
    assert results[0]["rank"] == 1
    assert results[0]["candidate_name"] == "Asha Rao"
    assert results[0]["email"] == "asha@example.com"
    assert set(results[0]["score_breakdown"]) == {
        "ai_project_depth", "python_backend", "cloud_fullstack", "github", "engineering_depth"
    }
    assert sum(results[0]["score_breakdown"].values()) == results[0]["total_score"]
    assert "github_summary" in results[0]
    assert results[1]["eligible"] is False
    assert results[1]["rank"] is None
    assert results[1]["total_score"] is None
    assert results[1]["rejection_reason"]
    json.dumps(results)


def test_github_summary_reports_enrichment_and_missing_profile():
    from src.screener import _github_summary

    available = _github_summary({
        "available": True, "public_repos": 12, "recent_public_events_90d": 3,
        "recently_updated_repositories_180d": 4, "relevant_repositories": 2,
        "languages_in_recent_repos": ["Python", "TypeScript"],
    }, "octocat")
    assert "12 public repositories" in available
    assert "Python" in available
    missing = _github_summary({"available": False, "reason": "API timeout"}, "octocat")
    assert "API timeout" in missing
    assert "No GitHub profile URL" in _github_summary({}, None)
