"""Milestone 8 -- FastAPI service wrapping the CareFlow agent pipeline.

Run with:
    uvicorn app.api.main:app --reload
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agents.insurance_agent import run_insurance_agent
from app.agents.intake import parse_intake_message
from app.agents.referral_agent import run_referral_agent
from app.graph.intake_workflow import close_workflow_checkpointer, resume_intake_workflow, run_intake_workflow
from app.models.patient_request import PatientRequest
from app.rag.index import close_qdrant_client
from app.rag.qa_agent import answer_policy_question

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_workflow_checkpointer()
    close_qdrant_client()


app = FastAPI(title="CareFlow", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
def ui() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


class IntakeRequest(BaseModel):
    raw_text: str
    channel: str


class AgentChatRequest(BaseModel):
    raw_text: str
    channel: str
    patient_id: str | None = None


class AgentChatResponse(BaseModel):
    patient_request: PatientRequest
    response: str
    flagged: bool
    tool_calls: list[dict]


class PolicyQuestionRequest(BaseModel):
    question: str
    patient_id: str | None = None


class WorkflowStartRequest(BaseModel):
    raw_text: str
    channel: str
    session_id: str
    patient_id: str | None = None


class WorkflowResumeRequest(BaseModel):
    session_id: str
    decision: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/intake", response_model=PatientRequest)
def intake(request: IntakeRequest) -> PatientRequest:
    return parse_intake_message(request.raw_text, channel=request.channel)


def _agent_chat(request: AgentChatRequest, run_agent) -> AgentChatResponse:
    try:
        patient_request = parse_intake_message(request.raw_text, channel=request.channel)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = run_agent(patient_request, request.raw_text, patient_id=request.patient_id)
    return AgentChatResponse(patient_request=patient_request, **result)


@app.post("/insurance/chat", response_model=AgentChatResponse)
def insurance_chat(request: AgentChatRequest) -> AgentChatResponse:
    return _agent_chat(request, run_insurance_agent)


@app.post("/referral/chat", response_model=AgentChatResponse)
def referral_chat(request: AgentChatRequest) -> AgentChatResponse:
    return _agent_chat(request, run_referral_agent)


@app.post("/policy/ask")
def policy_ask(request: PolicyQuestionRequest) -> dict:
    answer = answer_policy_question(request.question, patient_id=request.patient_id)
    return answer.model_dump()


@app.post("/workflow/start")
def workflow_start(request: WorkflowStartRequest) -> dict:
    return run_intake_workflow(
        request.raw_text, request.channel, session_id=request.session_id, patient_id=request.patient_id
    )


@app.post("/workflow/resume")
def workflow_resume(request: WorkflowResumeRequest) -> dict:
    if request.decision not in ("confirm_escalate", "override_proceed"):
        raise HTTPException(status_code=422, detail="decision must be 'confirm_escalate' or 'override_proceed'.")
    return resume_intake_workflow(request.session_id, request.decision)
