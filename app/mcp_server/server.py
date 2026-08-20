"""Milestone 6 -- mock EHR/scheduling system exposed as an MCP server.

Thin re-exposure of the existing tool functions (app/tools/mock_ehr.py,
app/tools/copay_calculator.py, app/tools/referral_tools.py) as MCP tools --
no logic is duplicated here. Runs over stdio so any MCP client (this
project's own app/tools/mcp_client.py, Claude Desktop, another agent
framework, ...) can talk to it as a subprocess.

Run standalone with:
    python -m app.mcp_server.server
"""

from mcp.server.fastmcp import FastMCP

from app.tools import copay_calculator, mock_ehr, referral_tools

mcp = FastMCP("careflow-ehr")


@mcp.tool()
def get_available_slots(specialty_key: str, max_results: int = 5) -> list[dict]:
    """List open appointment slots for a clinic specialty."""
    return mock_ehr.get_available_slots(specialty_key, max_results)


@mcp.tool()
def book_appointment(appointment_id: str, patient_id: str) -> dict:
    """Book a previously-available appointment slot for a patient."""
    return mock_ehr.book_appointment(appointment_id, patient_id)


@mcp.tool()
def check_eligibility(insurance_id: str) -> dict:
    """Look up a patient's insurance eligibility status, plan, and deductible progress."""
    return mock_ehr.check_eligibility(insurance_id)


@mcp.tool()
def calculate_copay(insurance_id: str, visit_type: str = "specialist") -> dict:
    """Calculate the flat office-visit copay for a patient's plan (visit_type: specialist|primary_care)."""
    return copay_calculator.calculate_copay(insurance_id, visit_type)


@mcp.tool()
def estimate_procedure_cost(insurance_id: str, specialty_key: str) -> dict:
    """Estimate a patient's out-of-pocket cost for a specialty's typical procedure."""
    return copay_calculator.estimate_procedure_cost(insurance_id, specialty_key)


@mcp.tool()
def create_referral(patient_id: str, specialty_key: str, referring_provider: str = "Self-referral", reason: str = "") -> dict:
    """Create a new specialist referral for a patient."""
    return referral_tools.create_referral(patient_id, specialty_key, referring_provider, reason)


@mcp.tool()
def get_referral_status(referral_id: str) -> dict:
    """Look up a referral's current status by referral ID."""
    return referral_tools.get_referral_status(referral_id)


@mcp.tool()
def update_referral_status(referral_id: str, status: str) -> dict:
    """Update a referral's status (pending|approved|scheduled|completed|expired|cancelled)."""
    return referral_tools.update_referral_status(referral_id, status)


@mcp.tool()
def list_referrals_for_patient(patient_id: str) -> list[dict]:
    """List all referrals on file for a patient."""
    return referral_tools.list_referrals_for_patient(patient_id)


if __name__ == "__main__":
    mcp.run()
