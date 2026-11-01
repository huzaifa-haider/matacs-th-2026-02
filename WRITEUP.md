# Proposal triage design

The tool should help a reviewer make a defensible shortlist. It should never award a contract or quietly fill in a missing fact.

## Assumptions and scoring

The brief supplies weights but no scoring scale. The rubric below is my proposed admin configuration, not an extra requirement attributed to the brief. An admin approves it before proposals are evaluated. Budget and deadline are project constraints: a confirmed breach is ineligible; an unknown value needs clarification.

For this example, I assume an evaluation date of 1 January 2026 and an inclusive experience window beginning 1 January 2021. This makes A's and E's stated experience usable. In production the reviewer sets the actual evaluation date; a different date can require project-level dates and a new evaluation. C's aggregate count beginning in 2020 cannot establish how many projects fall within the window. I accept “named lead” in the supplied summaries as confirmation of that criterion; real uploads must identify the person.

Only eligible, resolved proposals receive scores. Each formula returns points, capped at its criterion weight:

| Criterion | Configured points |
| --- | --- |
| Experience, 30 | `30 × min(qualifying project count / 15, 1)` |
| Price, 25 | `25 × min(200000 / total CAD price, 1)`; price must be positive and at most 260000 |
| Timeline, 15 | `15 × min(8 / completion weeks, 1)`; weeks must be positive and at most 16 |
| Warranty, 15 | `7.5 × min(panel years / 25, 1) + 7.5 × min(workmanship years / 12, 1)` |
| Team and approach, 15 | 3.75 each for a named lead, described crew, safety plan, and monitoring plan |

The reference targets—15 projects, CAD 200,000, eight weeks, and warranty lengths—are illustrative policy choices, not market claims. Fixed targets avoid changing everyone's score when another bidder is added. Missing evidence is unknown, not a guessed zero; the reviewer resolves it or holds the proposal. Explicitly absent optional team elements earn zero. Additional roof reviews or reports earn no unconfigured bonus.

| Proposal | Experience | Price | Timeline | Warranty | Team | Total / outcome |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| A | 28.00 | 21.01 | 10.00 | 13.75 | 15.00 | **87.76; rank 1** |
| E | 16.00 | 20.62 | 9.23 | 15.00 | 15.00 | **75.85; rank 2** |
| B | — | — | — | — | — | Ineligible |
| C | — | — | — | — | — | Flagged |
| D | — | — | — | — | — | Flagged |

A's stronger experience and lower price outweigh E's longer workmanship warranty. B does not confirm the required licence held by the bidder; a future subcontractor does not satisfy that rule. C's embedded ranking instruction is untrusted text: it earns no points and triggers review, alongside its unclear experience window. D has no completion commitment, so compliance with 16 weeks cannot be established. C and D are held, not assumed to be worse bidders.

## 1. AI vs. rules

The reviewer selects a category and uploads PDFs. Code checks file type, size, duplicates and readable pages, stores originals and hashes, and freezes the category version. A parser extracts page-labelled text; scanned pages use OCR, with poor-quality pages held for review. AI turns varied wording into structured facts with exact evidence quotes. It does not set policy, determine eligibility, calculate scores or rank bidders.

Code validates the extraction schema and evidence against the source. The reviewer confirms the evidence, especially unknown or suspicious fields. Rules then apply mandatory checks, constraints and the saved scoring configuration. A templated explanation shows the point breakdown and links to the supporting evidence.

## 2. Consistency and explainability

Save the document hash, extracted facts, reviewer corrections, evaluation date, prompt/model versions and criteria version. Identical approved facts and configuration produce identical results. Fresh model extraction is not guaranteed identical, even at temperature zero, so reuse approved facts rather than silently re-extracting. Calculate with full precision, round totals to two decimals, and use proposal ID to order exact score ties; label these ties as equal merit. Reviewers see every input, formula, quote and decision.

## 3. Human in the loop

The admin approves the configuration. The reviewer confirms extracted evidence and resolves holds before a final shortlist is produced. A human verifies supporting credentials before award and makes the award decision. Corrections record old/new values, actor, time, evidence and reason, then trigger recalculation. An exceptional award decision is recorded separately; it never rewrites the calculated score or turns a failed requirement into a pass without an approved policy change.

## 4. Changing criteria

Edits create a new immutable version. Existing runs keep their original version and remain readable. The reviewer can start a new run that reevaluates every proposal against the same new version; newly required facts must be extracted and confirmed. Show both versions and the reason for changed outcomes. Never mix versions in one ranking.

## 5. Risks and safeguards

- **Bad extraction or invented facts:** require exact quotes and source locations, reject unsupported values, and review low-quality OCR and conflicting evidence.
- **Manipulation:** treat all PDF content as data, give the model no tools or secrets, flag instruction-like content, and enforce decisions outside the model. Prompt wording alone is not a security boundary.
- **Bias:** score only approved criteria; exclude branding and persuasive language. Review the rubric itself for unfair proxies and record changes before reevaluation.
- **Cost and failures:** cap pages/tokens, cache extraction, limit retries and show a recoverable failure instead of an incomplete ranking.
- **Data exposure:** restrict category and proposal access, encrypt stored files, set retention rules, and use an approved model service. This exercise uses fictional data only.
