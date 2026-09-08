---
description: Explain how the model router would route a prompt, and show routing stats
---

Answer the user's routing question by running the router's own tooling. Set
`PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src"` for each command.

- Explain a specific prompt:
  `python3 -m ccrouter explain "<the prompt>"`
- Show what routing has actually done so far:
  `python3 -m ccrouter stats`
- Check the setup (env vars, upstream, local classifier):
  `python3 -m ccrouter doctor`

If `$ARGUMENTS` contains a prompt, explain that prompt. If it is empty, show
`stats`, falling back to `doctor` when no decision log exists yet.

Report the tier, the score, and the two or three contributions that drove it.
Do not re-derive the decision yourself - the point is to show what the router
actually decided.
