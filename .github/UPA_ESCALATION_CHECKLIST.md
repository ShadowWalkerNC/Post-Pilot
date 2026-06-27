# UPA Escalation Checklist

> Start every task in Light Mode. Work through this checklist to decide if Full UPA is required.

---

## Step 1 — Light Mode Preflight

Answer all questions before proceeding.

- [ ] What is the goal in one sentence?
- [ ] Is the scope small and well understood?
- [ ] Is the change reversible?
- [ ] Are there security, privacy, or auth impacts?
- [ ] Are there data model or migration impacts?
- [ ] Are there accessibility or compliance impacts?
- [ ] Are multiple teams or stakeholders affected?
- [ ] Is there meaningful uncertainty about the right approach?

---

## Step 2 — Escalation Triggers

Escalate to Full UPA if **any** of the following are true:

### Security & Trust
- [ ] Secrets, credentials, or tokens are involved.
- [ ] Authentication, authorization, or session logic is changed.
- [ ] A trust boundary is crossed or modified.
- [ ] A public-facing bypass or debug route is present.
- [ ] Third-party integrations or external dependencies are introduced.

### Data & Integrity
- [ ] Database schema, migrations, or data integrity are involved.
- [ ] Encryption keys or sensitive data are touched.
- [ ] User data could be exposed, lost, or corrupted.

### Deployment & Reliability
- [ ] Production deployment or infrastructure is changed.
- [ ] The change is hard or impossible to roll back.
- [ ] Monitoring, alerting, or observability is affected.

### Scope & Clarity
- [ ] Requirements are unclear, ambiguous, or contested.
- [ ] Multiple disciplines must weigh in (security + UX + DB, etc.).
- [ ] The decision sets a long-term architectural direction.

### People & Risk
- [ ] Multiple teams or stakeholders are affected.
- [ ] Legal, compliance, or regulatory requirements apply.
- [ ] Failure has material impact on users or business operations.
- [ ] Accessibility or compliance may be impaired.

---

## Step 3 — Full UPA Requirements

If escalation is triggered, the following must be completed before implementation:

- [ ] Real problem defined, not just the requested solution.
- [ ] Assumptions and unknowns explicitly stated.
- [ ] Conservative, balanced, and aggressive options compared.
- [ ] Risks documented with likelihood, impact, mitigation, and owner.
- [ ] Security review completed (STRIDE where relevant).
- [ ] UX and accessibility reviewed.
- [ ] Performance impact assessed.
- [ ] Tests written or planned.
- [ ] Rollback plan defined.
- [ ] Documentation updated.
- [ ] Stakeholders informed.

---

## Step 4 — Decision Log

Fill this in for every escalated task.

```
Date:
Task:
Mode used:          [ ] Light Mode    [ ] Full UPA
Escalation trigger: 
Decision made:
Trade-offs accepted:
Risks acknowledged:
Follow-up items:
Owner:
```

---

## Quick Reference

| Signal | Mode |
|---|---|
| Small, clear, reversible | Light Mode |
| Touches security or auth | Full UPA |
| DB schema or migration | Full UPA |
| Production deployment | Full UPA |
| Multi-stakeholder | Full UPA |
| Unclear requirements | Full UPA |
| Hard to roll back | Full UPA |
| Legal or compliance | Full UPA |

---

## Operating Principle

**Default to Light. Escalate on risk. Always document the decision that matters.**
