You are implementing board task $title.

## Task

- Issue: $issue_url
- Repository: `$repo`
- Spec: `$spec`
- Plan: `$plan`
- Working directory: `$workdir`
- Branch: `$branch` (already checked out there)
$resume
## Before you start

All paths above are relative to the workspace root `$workspace`, where this session
starts. Run git and repository checks inside `$workspace/$workdir`
(e.g. `git -C $workspace/$workdir status`, `git -C $workspace/$workdir log development..$branch`).
Never run `git commit` or other git commands directly in `$workspace` — it is the
meta-repo, not the task's repository.

1. Read `AGENTS.md` in the workspace root.
2. Read the repository instructions: $repo_agents.
3. Read the issue (`gh issue view $issue_url`), then the spec and the plan in full.

## Doing the work

- Work only inside `$workspace/$workdir`, on `$branch`.
- Follow the plan task by task. Tick plan checkboxes as you complete steps.
- Commit locally with focused commits that follow the repository's conventions.
- Run the repository's documented checks (tests, lint, type checks, `make contracts-check`
  where relevant) and fix failures caused by your change.
- Never push, merge, check out `development`, `main` or `staging`, or close the issue.
- Change the board status only with the commands below.

## Finishing

When the work is complete and the checks pass, run:

    $workspace/work board set $id in-review -m "<what was done; checks run and their results; open follow-ups>"

If you cannot continue, run the following and stop:

    $workspace/work board set $id blocked -m "<what blocks you and what is needed>"
