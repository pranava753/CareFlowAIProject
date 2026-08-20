# Data Handling Standard

## Purpose
This standard governs how patient data is stored, retained, and accessed within the care-coordination system.

## Synthetic data notice
All patient, encounter, eligibility, appointment, and referral records in this environment are synthetically generated for development and evaluation purposes. No record in this environment corresponds to a real person.

## Retention
- Session memory (the current conversation) is retained for 30 days after the last message, then purged.
- Long-term patient memory (summarized interaction history) is retained for the duration the patient remains an active member of the clinic, then purged 1 year after their last visit.
- Human-escalation queue entries are retained for 2 years for audit purposes.

## Access tiers
- **Automated assistants** may read intake, eligibility, appointment, and referral records needed to answer the current request, and may write new appointments, referrals, and flag-for-human entries.
- **Human care coordinators** may read and amend any record.
- **Clinicians** additionally have access to referral clinical notes.

## De-identification
Any data exported for analytics or model evaluation must have direct identifiers (name, phone, email, street address) removed or replaced with synthetic equivalents before export.
