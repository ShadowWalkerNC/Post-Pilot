# UPA Light Mode

> Use Light Mode by default. Escalate to full UPA when risk or uncertainty is high.
> See [UPA_ESCALATION_CHECKLIST.md](./UPA_ESCALATION_CHECKLIST.md) for escalation triggers.

---

## When to use Light Mode

Use Light Mode when the work is:
- Single-purpose and well understood.
- Low-risk and reversible.
- Mostly implementation, review, or planning.

Escalate to full UPA when:
- Security, privacy, auth, or access control is involved.
- Data models or migrations are touched.
- The change is hard to roll back.
- Scope is unclear or requirements are contested.
- Multiple teams or stakeholders are affected.

---

## Core Rules

1. Understand the real problem before proposing a solution.
2. State assumptions explicitly.
3. Separate facts from hypotheses.
4. Prefer the simplest viable option.
5. Identify risks before acting.
6. Verify important claims.
7. Do not ship unsafe or inaccessible work.
8. Document decisions that are hard to reverse.

---

## Light Workflow

### Step 1 — Clarify
Answer in one sentence:
- What is the problem?
- Who is affected?
- What does success look like?

If unclear, flag the ambiguity and proceed with a documented assumption.

### Step 2 — Check Constraints
- Scope
- Deadline
- Environment
- Security impact
- Data impact
- Accessibility impact

### Step 3 — Identify Risks
- What could break?
- What could be abused?
- What is hard to roll back?
- What is unknown?

### Step 4 — Compare Options
For any important choice:
1. Conservative
2. Balanced
3. Aggressive

Choose the option with the best fit for current constraints.

### Step 5 — Act
- Make the smallest correct change.
- Write tests if the change is code.
- Update docs if behavior changes.
- Keep it reversible where possible.

### Step 6 — Verify
- Does it work?
- Did it introduce regressions?
- Is it safe?
- Is it usable?
- Is it documented?

---

## Minimum Required Outputs

Every Light Mode response should include:

- Direct answer or recommendation.
- Assumptions, if any.
- Key risks.
- Next step.
- Verification status or plan.

---

## Security Baseline

- Validate inputs.
- Minimize secrets exposure.
- Use least privilege.
- Review auth and authorization changes.
- Flag any public-facing bypasses.
- Escalate if a change affects trust boundaries.

---

## Accessibility Baseline

Meet WCAG 2.1 AA as a minimum. Quick checks:

- [ ] Keyboard works.
- [ ] Focus is visible.
- [ ] Labels are clear.
- [ ] Contrast is sufficient.
- [ ] Images have text alternatives.
- [ ] Errors are understandable.

---

## Definition of Done

A Light Mode task is done when:

- [ ] Problem is addressed.
- [ ] Major risks are named.
- [ ] Chosen solution is explained.
- [ ] Change is verified.
- [ ] Any follow-up is documented.

---

## One-Sentence Operating Principle

**Think first, act small, verify fast, document the decision that matters.**
