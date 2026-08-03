---
description: Set up or refresh the fleet provider registry (interview + current model/pricing research)
argument-hint: [refresh]
---

Build or refresh the user's fleet provider registry. The finished artifact is
`.fleet/providers.json` (project-level) or `~/.fleet/providers.json`
(user-level — ask which they want; user-level is the right default for a
personal fleet used across projects).

Read first:
- `${CLAUDE_PLUGIN_ROOT}/skills/fleet-delegation/references/providers-guide.md` (schema)
- `${CLAUDE_PLUGIN_ROOT}/skills/fleet-delegation/config/providers.example.json` (shape)
- If a registry already exists (`python3 ${CLAUDE_PLUGIN_ROOT}/skills/fleet-delegation/scripts/registry.py path`),
  load it — this is a refresh, preserve the user's strengths/weaknesses notes
  and routing order unless they say otherwise.

Then:

0. **If a registry already exists, show it and get direction before asking
   anything else.** Present the current setup in a compact summary — each
   provider with its access mode, default model, trust level, and the user's
   own notes, plus the routing order — and ask whether they want to (a) keep
   it unchanged (stop here), (b) adjust specific entries, or (c) redo the full
   interview. Never ask reconfiguration questions the existing registry
   already answers unless the user chose the full redo; for (b), touch only
   the entries they named and preserve everything else verbatim.

1. **Interview the user** about what they actually have. For each candidate:
   which CLIs are installed (`codex`, `agy` (Antigravity), `gemini`,
   `grok` (Grok Build), `cursor-agent`, `copilot`, `qwen`, `droid`, `amp`,
   `claude`, `opencode` — verify with `command -v`; note Gemini CLI was
   retired 2026-06-18 except for enterprise Gemini Code Assist licenses, so
   steer most users to `antigravity`), how they pay (subscription plan, API
   key, free tier, local),
   and for OpenCode-routed providers, which are authenticated
   (`opencode auth list`) and what local servers exist (LM Studio / Ollama).
   Do not add providers the user doesn't have access to — an aspirational
   registry causes failed dispatches, not capability.

2. **Research current facts with web search.** For each provider the user has:
   current model names, per-token pricing for API access, context windows, and
   any notable recent strengths/weaknesses. Model names and prices change
   monthly — never write these from memory. Date-stamp findings in each
   provider's `notes` field (e.g. "pricing verified 2026-07").
   Also research the **supervisor's own model rates** — the current API list
   price of the model this session runs on, including cache read/write rates —
   and record them in the top-level `supervisor` block (see
   providers-guide.md). These rates price the
   counterfactual in pre-dispatch spend ballparks and the ledger's
   realized-savings figures; without researched numbers those estimates run on
   memory, which is exactly what this step exists to prevent. If the user is
   on a flat-rate plan, use the API list price for the same model — the market
   value of the quota delegation preserves.

3. **Draft the registry** with honest strengths/weaknesses (mark unverified
   claims as such), sensible `max_workers` (1 for local, 2 elsewhere), `trust`
   levels (`restricted` for small local models), and a cheapest-first
   `routing.prefer_order`. Costs: `flat` for subscriptions/free tiers,
   `per_token` with researched prices for API, `free` for local.

4. **Show the draft to the user for correction before writing the file.**
   Their lived experience of these models outranks anything you researched.
   After writing, run
   `python3 ${CLAUDE_PLUGIN_ROOT}/skills/fleet-delegation/scripts/registry.py validate`
   and fix any problems.

5. Remind the user of per-CLI setup the registry can't do for them: `codex
   login`, Antigravity's `agy` Google login (or `GEMINI_API_KEY` /
   `ANTIGRAVITY_API_KEY`), gemini auth (enterprise only), `grok login`
   (needs SuperGrok / X Premium+), `cursor-agent login` or `CURSOR_API_KEY`,
   `copilot` login or `GH_TOKEN`, qwen API key or Coding Plan,
   `FACTORY_API_KEY` (droid), `amp login` or `AMP_API_KEY`, `opencode auth
   login` per provider, OpenCode
   permissions config for unattended runs, and LM Studio's local server if
   used (see the plugin README's per-provider setup section).
