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

- Work only inside `$workspace/$workdir`, on `$branch`, for the owner repository `$repo`.
- A task can change more than one repository. The issue, spec and plan name every repository
  the task changes (for example in an "also changes" note or the plan's global constraints).
  Every repository the task changes is part of this task, and you must do the work in each of
  them, not only in `$repo`.
- For each other repository the task changes, create the same branch from `development` as a
  worktree, without checking anything out in the main checkout:

      git -C $workspace/<repo> worktree add $workspace/.worktrees/<repo>/$branch -b $branch development

  Use the worktree for all work in that repository. If the branch or worktree already exists,
  reuse it and review it before continuing. Read that repository's `AGENTS.md` and `README.md`
  before you change it.
- Order multi-repository changes so each contract or dependency is ready before its consumers
  need it. For example, a `q_contracts` change is committed first, then consumers pin its
  commit in `CONTRACTS_REV` and regenerate their vendored code.
- Follow the plan task by task. Tick plan checkboxes as you complete steps.
- In each repository, commit locally with focused commits that follow that repository's
  conventions.
- Run each repository's documented checks (tests, lint, type checks, `make contracts-check`
  where relevant) and fix failures caused by your change. Report the result for every
  repository.
- Never push, merge, check out `development`, `main` or `staging`, or close the issue, in any
  repository.
- Change the board status only with the commands below. One status covers the whole task, so
  the message must name every repository you changed.

## Finishing

When the work is complete and the checks pass, run:

    $workspace/work board set $id in-review -m "<what was done; checks run and their results; open follow-ups>"

If you cannot continue, run the following and stop:

    $workspace/work board set $id blocked -m "<what blocks you and what is needed>"
