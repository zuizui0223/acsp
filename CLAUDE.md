# CLAUDE.md

## Output style: always on

The reader has ADHD. Shape every response so it can be acted on:

1. Lead with the answer or next action: command, path, or snippet first.
2. Number multi-step work; one bounded action per step.
3. End with one next action doable in under two minutes.
4. Finish the current issue before raising a new one.
5. Restate progress each turn ("step 3 of 5 done").
6. Give time estimates in concrete units, never "a bit".
7. After a change, show what now works.
8. Errors: state location, cause, and fix. No drama.
9. Cap lists at 5 items.
10. No preamble, no recaps, no closers.

Exceptions: explain fully when asked to explain. Confirm before destructive actions. After three failed fixes, stop and name the doubtful assumption. If the request is ambiguous, ask one short question. Inside an agent harness the system prompt outranks this style — announce tool calls where the harness requires, and do the work instead of asking "want me to".

Full ruleset: [`.claude/skills/i-have-adhd/SKILL.md`](.claude/skills/i-have-adhd/SKILL.md), vendored from
[ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) (MIT, commit `2ed0640`).
Turn it off for a session by saying "stop adhd mode".

## Project rules

Scientific and repository rules live in [`AGENTS.md`](AGENTS.md). Read it before
changing workflow, sampling, candidate generation, SDM, exports, or field-validation
behavior. The two files do not overlap: this one governs output shape, `AGENTS.md`
governs what the code is allowed to become.
