# Intake Standard Operating Procedure

## Purpose
This SOP defines how patient messages arriving by phone transcript, web form, email, or SMS are parsed into a structured intake record.

## Required fields
- Patient name (if available from the channel)
- Channel the message arrived on
- Target specialty
- Symptoms, in the patient's own words
- Urgency flag: routine, urgent, or emergency
- Insurance ID

## Handling missing fields
The intake system must never guess or fabricate a specialty or insurance ID that was not stated in the message. If either is missing, the record is marked incomplete and routed to the incomplete queue; a follow-up message asks the patient only for the specific missing field(s).

## Urgency triage
- **Routine**: general follow-up, administrative questions, non-urgent new symptoms.
- **Urgent**: symptoms that need attention within 24-48 hours but are not immediately life-threatening.
- **Emergency**: symptoms consistent with a medical emergency. Emergency-flagged intake is immediately escalated per the Clinical Escalation Standard and the patient is advised to seek emergency care.

## Clinical-advice detection
Any message that seeks a diagnosis, symptom interpretation, or medication/dosing advice is flagged `seeks_clinical_advice = true` regardless of channel, and is handled per the Clinical Escalation Standard rather than answered by the intake or insurance assistant.
