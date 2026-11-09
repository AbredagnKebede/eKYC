---
name: atomic-commits
description: >-
  Create professional, human-sounding git commits that group only related
  changes. Use whenever the user asks to commit, or when finishing a coherent
  unit of work that should be recorded on git.
---

# Atomic professional commits

## When to use

Apply this skill for every commit request and whenever you are about to record finished work on git.

## Rules

1. **Never bulk-commit.** One commit = one concern (one feature slice, one bugfix, one refactor, one docs/chore item). If the working tree mixes concerns, split into multiple commits.
2. **Stage only relevant paths** for that concern. Review `git status` and `git diff` before staging. Do not `git add .` or `git add -A` unless every remaining change truly belongs in the same commit.
3. **Message voice:** 1–2 sentences, at most 3. Sound like an engineer who was there—specific and natural. No chatbot filler, no generic “update files” / “misc changes” / “WIP”.
4. **Lead with why/impact**, not a file list. Prefer present or past tense that names the behavior change.
5. **Do not commit** secrets, `.env`, agent scaffolding that is gitignored, build artifacts, or unrelated dirty files.
6. **Do not push** unless the user explicitly asks.
7. Pass the message via a HEREDOC. Never use `--no-verify` unless the user asks.

## Process

```bash
git status -sb
git diff
git log -8 --oneline   # match repo tone
# stage only paths for THIS concern
git add <paths...>
git commit -m "$(cat <<'EOF'
Specific sentence about why this change landed.

Optional second sentence for consequence or constraint.

EOF
)"
git status -sb
```

## Good vs bad

**Good**

- `Park CBS results in the inbound queue when ff_inbound is off.`
- `Require Fayda OTP before the bank picker so passport identity is bound first.`
- `Stop tracking VibeArch scaffolding so the remote stays product-only.`

**Bad**

- `Update stuff`
- `Fix bugs and add features`
- `Changes`
- `Address feedback`
- Multi-topic dumps that mix API, mobile, and ignore-file cleanup

## Split heuristics

Split when diffs touch more than one of: API routes, DB/models, workers, mobile UI, web portal, docs, tooling/ignore, verification scripts. Same theme across a few tightly coupled files may stay one commit.
