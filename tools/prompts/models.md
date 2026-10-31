You are maintaining the model profiles in `$models_file`, under the workspace root
`$workspace`. Planning agents rely on these profiles to suggest models for board tasks without
researching them again.

## Scope

$scope

## Research

Read `$workspace/AGENTS.md` and all of `$models_file` first. Then, for each model in scope:

- Use its vendor's current documentation for facts, and independent coding benchmarks or
  evaluations for capability. Do not rely on what you remember about a model, and do not treat
  vendor marketing as evidence of capability.
- Rate it against this project's real work: Rust, Python, TypeScript and QML; multi-repository
  changes; and code where a mistake is expensive, such as order execution and deterministic
  kernels.
- Where evidence is thin or sources conflict, say so and rate conservatively. Never invent a
  number or a benchmark result.

## Writing the profiles

Under `## Profiles`, keep exactly one section per profiled model, ordered as in the roster and
in this format (replace any "No profiles yet." line):

    ### <agent> / <model>

    - **Maximum difficulty:** <D1–D4 from the file's scale, the hardest level it can be trusted with>
    - **Efforts:** <when to use each `./work start --effort` level worth using, and the one to default to>
    - **Relative cost:** <low, medium or high within this roster, with published token prices if any>
    - **Limits:** <context window and output limits that matter for long tasks>
    - **Strengths:** <one or two lines of concrete evidence-backed strengths>
    - **Weaknesses:** <one or two lines, including anything to avoid giving it>
    - **Verified:** <today's date, YYYY-MM-DD>
    - **Sources:** <links>

Keep each profile to those bullets, since planning agents read the whole file. Make ratings
comparable across the roster. Change only `## Profiles`. The roster belongs to the human: if a
row looks wrong, for example a model name the vendor does not recognize, report it rather than
editing it.

## Finishing

Do not commit, push, or create a board task. Leave the edit in the working tree for human review,
and report which profiles changed, any rating that moved and why, and anything you could not verify.
