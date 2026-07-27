---
name: stage-change-delivery
description: Turn an understood change set into an ordered, commit-sized delivery plan, then implement it one reviewable stage at a time with explicit approval checkpoints. Use after brainstorming or design work when the user asks for an implementation plan, PR plan, commit breakdown, stacked-branch plan, incremental execution, or a careful one-change-at-a-time workflow. Also use when the user explicitly wants to review, commit, or push each completed slice manually before Codex continues.
---

# Staged Change Delivery

Convert settled intent into small, coherent changes and deliver them at a pace the user controls. Keep planning, implementation, approval, committing, and pushing as distinct decisions.

## Establish the starting point

- Recover the intended outcome, constraints, and decisions from the conversation and repository context.
- If the design is still materially undecided, resolve it before producing a delivery plan. Do not disguise open product or architecture questions as implementation steps.
- Inspect relevant project instructions and current repository state. Preserve unrelated user changes and account for work already present.
- State any assumption that changes scope, branch structure, or externally visible behavior.

## Build the delivery plan

Produce a concrete plan rather than a narrative recap.

For every stage:

- Define one coherent, independently reviewable change. Split unrelated concerns even when they touch the same file.
- Name the likely files or components, the exact change, and why it belongs in this stage.
- Specify focused verification appropriate to the change.
- Note dependencies, risks, migrations, or behavior changes that affect ordering.

Organize the plan using these conventions:

- Put correctness, safety, and unblockers before convenience work.
- Put foundations before their dependents while keeping each stage useful and reviewable.
- Group stages by PR or branch when the work spans multiple review units. Make stacked dependencies and branch boundaries explicit.
- Prefer the smallest sequence that preserves coherent history; do not create ceremonial stages with no independent value.
- Include code sketches only where they prevent ambiguity.

Present the full plan for approval. Do not begin implementation until the user approves it or explicitly selects a stage to execute.

## Deliver one stage

For the approved current stage:

1. Re-check repository status and relevant files so user edits or earlier commits are not overwritten.
2. Implement only the current stage. Avoid opportunistic cleanup unless it is necessary for correctness; surface newly discovered follow-up work instead.
3. Run the narrowest meaningful verification allowed by the user's instructions and environment. This skill grants no additional authority to run commands or mutate external state.
4. Review the resulting diff for scope, accidental changes, debug artifacts, and consistency with the approved plan.
5. Propose a concise commit message. Prefer a short, lowercase phrase without a Conventional Commit prefix unless repository conventions require otherwise.
6. Stop at a review checkpoint.

At the checkpoint, report:

- what changed and why;
- verification performed and its result;
- material caveats or deviations;
- the proposed commit message;
- what the next approved stage would be.

Show or summarize the diff at the level most useful for review. Do not commit, push, switch branches, rebase, or start the next stage unless the user explicitly authorizes that action.

## Open a draft PR

When the user provides or creates a feature branch whose name includes a ClickUp ticket ID and asks to begin delivery on it:

- Inspect the branch, its remote state, and any existing PR before creating one.
- Target `dev` unless the user specifies another base branch.
- Check related prior PRs, both open and closed, when needed to infer title, formatting, and metadata conventions.
- Use a concise, repository-consistent title. Do not assume a fixed title prefix or verb; derive the wording from the relevant prior PRs and the change itself.
- Assign the PR to the user who requested the work.
- Keep author, labels, reviewers, assignees other than the user, and other metadata at their default values unless the user explicitly requests otherwise. Do not add the agent as an author or assignee.
- Create the PR as a draft and leave it in draft state.
- Write the body as a concise Markdown bullet list describing the intended complete PR at a high level. Derive it from the approved full change plan, not only the current stage or current branch diff. Summarize the whole intended diff as if the PR were complete, even when implementation is still staged; revise the body later if the scope changes.
- Use the current branch as the PR head. If the remote branch does not exist, stop and request explicit authorization to push it; opening the PR workflow must not imply permission to push.
- Do not merge, mark ready for review, request reviewers, or otherwise advance the PR unless explicitly authorized.
- Verify the created PR base branch, head branch, title, body, assignee, and draft status.

## Handle feedback and continuation

- Treat feedback on the current stage as a request to revise it, not as approval to advance.
- Revise or simplify the current stage in place, re-run relevant verification, and return to the checkpoint.
- Treat signals such as "next," "continue," or "looks good" as permission to begin the next planned stage only. Do not infer permission to commit or push.
- Re-read repository state before resuming because the user may have edited, committed, rebased, or switched branches during the checkpoint.
- At a PR, branch, migration, or rebase boundary, explain the transition and obtain explicit confirmation before crossing it.

## Manage plan drift

If implementation reveals that a stage is unsafe, substantially larger, or dependent on an unplanned change:

- stop expanding the current diff;
- explain the discovery with repository evidence;
- propose the smallest plan revision;
- identify effects on later stages;
- wait for approval when the revision materially changes scope or review structure.

Minor file-level adjustments that preserve the approved intent and stage boundary do not require replanning; record them at the checkpoint.

## Finish the workflow

After the final stage is approved, summarize completed stages, remaining caveats, and any intentionally deferred work. Keep uncommitted, committed, and pushed state precise; never describe a change as landed unless repository evidence supports it.
