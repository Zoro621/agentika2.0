from typing import Literal
from pydantic import BaseModel, Field


class CaseCreate(BaseModel):
    title: str = Field(default="Untitled investigation", max_length=200)
    provider: Literal["auto", "openai", "ollama", "deterministic"] = "auto"


class GithubSource(BaseModel):
    url: str = Field(max_length=500)
    ref: str | None = Field(default=None, max_length=200)


class DecisionInput(BaseModel):
    question_id: str = Field(max_length=100)
    answer: str = Field(max_length=1000)
    rationale: str = Field(default="", max_length=2000)


class ReviewInput(BaseModel):
    status: Literal["accepted", "revised", "dismissed", "unreviewed"]
    note: str = Field(default="", max_length=4000)


class ExtractedClaim(BaseModel):
    artifact_id: str
    quote: str = Field(min_length=10, max_length=1500)
    type: Literal[
        "numerical",
        "comparison",
        "sample_count",
        "method",
        "generalization",
        "significance",
        "ablation",
    ]
    metric: str | None = None
    value: float | None = None
    units: str | None = None
    dataset: str | None = None
    model: str | None = None
    split: str | None = None
    qualifiers: str = ""


class ClaimBatch(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list, max_length=30)


class OCRPage(BaseModel):
    text: str = Field(max_length=18000)
    unreadable: bool


class ScientificClarification(BaseModel):
    artifact_id: str
    quote: str = Field(min_length=10, max_length=1500)
    title: str = Field(min_length=10, max_length=200)
    why: str = Field(min_length=10, max_length=800)
    purpose: Literal["interpretation", "feature_availability", "experiment_correspondence"]
    subject: str = Field(default="", max_length=200)
    finding_ids: list[str] = Field(default_factory=list, max_length=8)


class InvestigationProposal(BaseModel):
    tool: Literal[
        "inspect_artifact",
        "search_evidence",
        "compare_metrics",
        "inspect_method",
        "run_check",
        "ask_question",
        "extract_claims",
        "finish",
    ]
    artifact_id: str | None = None
    query: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=1000)
    check: (
        Literal["metrics", "methodology", "partitions", "protocol", "paper", "arithmetic"] | None
    ) = None
    question: ScientificClarification | None = None
