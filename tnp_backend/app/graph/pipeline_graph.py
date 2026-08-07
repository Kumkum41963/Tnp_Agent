"""
Pipeline Graph — assembles nodes + edges into the compiled LangGraph graph.

The graph implements the full end-to-end pipeline. In simple terms the whole workflow has been visualised implemented as a directed graph.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.graph.edges import (
    after_await_responses,
    after_detect_missing_fields,
    after_deterministic_identity_match,
    after_run_resume_identity_agent,
    after_run_schema_agent,
)
from app.graph.nodes import (
    await_responses,
    detect_missing_fields,
    deterministic_identity_match,
    generate_google_form,
    generate_reports,
    generate_whatsapp_message,
    human_review_gate,
    ingest_company_upload,
    load_master,
    merge_form_and_resume_data,
    parse_resumes,
    populate_company_db,
    retry_schema_agent,
    run_resume_identity_agent,
    run_schema_agent,
    run_validation,
)
from app.graph.state import PipelineState


def build_pipeline_graph() -> object:
    """
    Build and compile the LangGraph pipeline.
    Returns a compiled graph ready for invocation.
    """
    graph = StateGraph(PipelineState)

    # ── Register nodes ────────────────────────────────────────────────────
    graph.add_node("load_master", load_master)
    graph.add_node("ingest_company_upload", ingest_company_upload)
    graph.add_node("run_schema_agent", run_schema_agent)
    graph.add_node("retry_schema_agent", retry_schema_agent)
    graph.add_node("populate_company_db", populate_company_db)
    graph.add_node("detect_missing_fields", detect_missing_fields)
    graph.add_node("generate_google_form", generate_google_form)
    graph.add_node("generate_whatsapp_message", generate_whatsapp_message)
    graph.add_node("await_responses", await_responses)
    graph.add_node("parse_resumes", parse_resumes)
    graph.add_node("deterministic_identity_match", deterministic_identity_match)
    graph.add_node("run_resume_identity_agent", run_resume_identity_agent)
    graph.add_node("merge_form_and_resume_data", merge_form_and_resume_data)
    graph.add_node("run_validation", run_validation)
    graph.add_node("generate_reports", generate_reports)
    graph.add_node("human_review_gate", human_review_gate)

    # ── Set entry point ───────────────────────────────────────────────────
    graph.set_entry_point("load_master")

    # ── Linear edges ─────────────────────────────────────────────────────
    graph.add_edge("load_master", "ingest_company_upload")
    graph.add_edge("ingest_company_upload", "run_schema_agent")
    graph.add_edge("retry_schema_agent", "run_schema_agent")
    graph.add_edge("populate_company_db", "detect_missing_fields")
    graph.add_edge("generate_google_form", "generate_whatsapp_message")
    graph.add_edge("generate_whatsapp_message", "await_responses")
    graph.add_edge("parse_resumes", "deterministic_identity_match")
    graph.add_edge("merge_form_and_resume_data", "run_validation")
    graph.add_edge("run_validation", "generate_reports")
    graph.add_edge("generate_reports", END)
    graph.add_edge("human_review_gate", END)

    # ── Conditional edges ─────────────────────────────────────────────────
    graph.add_conditional_edges(
        "run_schema_agent",
        after_run_schema_agent,
        {
            "retry_schema_agent": "retry_schema_agent",
            "human_review_gate": "human_review_gate",
            "populate_company_db": "populate_company_db",
        },
    )
    graph.add_conditional_edges(
        "detect_missing_fields",
        after_detect_missing_fields,
        {
            "generate_google_form": "generate_google_form",
            "run_validation": "run_validation",
        },
    )
    graph.add_conditional_edges(
        "await_responses",
        after_await_responses,
        {
            "parse_resumes": "parse_resumes",
            "run_validation": "run_validation",
        },
    )
    graph.add_conditional_edges(
        "deterministic_identity_match",
        after_deterministic_identity_match,
        {
            "run_resume_identity_agent": "run_resume_identity_agent",
            "merge_form_and_resume_data": "merge_form_and_resume_data",
        },
    )
    graph.add_conditional_edges(
        "run_resume_identity_agent",
        after_run_resume_identity_agent,
        {
            "human_review_gate": "human_review_gate",
            "merge_form_and_resume_data": "merge_form_and_resume_data",
        },
    )

    return graph.compile()


# Compiled graph singleton — imported by the API routes
pipeline_graph = build_pipeline_graph()
