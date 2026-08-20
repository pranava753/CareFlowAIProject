# Referral Management Policy

## Purpose
This policy governs how specialist referrals are created, validated, routed, and closed across all clinic locations. It applies to referrals originating from primary care providers, self-referrals where permitted by the patient's plan, and referrals generated from an intake message triaged by the Intake team.

## Required fields on every referral
- Patient identifier and active insurance ID
- Referring provider name (or "Self-referral" where the plan allows it)
- Target specialty
- Reason for referral, in the referring provider's or patient's own words
- Urgency flag: routine, urgent, or emergency

## Referral validity windows
A referral is valid for scheduling for a limited number of days from its creation date, after which it must be re-issued. Validity windows differ by specialty; see the relevant service-line handbook for the exact number of days. If a patient has not scheduled within the validity window, the Referral Tracking system marks the referral "expired" and notifies the referring provider.

## Routing
Referrals are routed to the target specialty's scheduling queue automatically once the required fields are complete. Referrals missing the insurance ID or specialty are held in an "incomplete" queue and the patient is contacted for the missing information before routing continues.

## Pre-authorization coordination
Where the target specialty's typical procedure requires pre-authorization under the patient's plan (see the Pre-Authorization Matrix), the referral is held at "pending pre-auth" status until the insurance team confirms approval. The Referral Tracking Agent must not confirm an appointment slot for a pre-auth-required procedure until that status changes to "approved".

## Overdue referrals
A referral pending pre-authorization for longer than the plan tier's standard turnaround time (see the Pre-Authorization Matrix) is escalated to a human care coordinator for manual follow-up with the payer.
