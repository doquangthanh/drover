# Phase 2 — Detection rules in JSON

## Context links
- `src/drover/status/detection_rule_loader.py` (parse_rule_file, load_rule_sets)
- `src/drover/status/rules/*.toml` (claude, codex, gemini, opencode, shell — 128 lines)
- `src/drover/core/status_monitor.py` (reload by user-dir mtime stamp), `rules.list` / `rules.test` RPC
- `frontend/src/views/rule-tester.tsx`

## Overview
Priority: medium. Status: planned. Same rule model, JSON files; bundled rules converted in the repo, user
rules migrated once.

## Key insights
- Regexes in JSON need escaped backslashes (`"\\d"`): convert with a script, never by hand, and compare the
  loaded rule sets before/after (same ids, priorities, regions, pattern strings).
- The monitor's reload stamp globs `*.toml` → must glob `*.json`.

## Requirements
Functional: bundled `rules/*.json`; user `~/.config/drover/rules/*.json` override by id; user `*.toml` migrated
once (backup `.toml.migrated`); errors listed as today.
Non-functional: detection results identical (same tests pass unchanged except file names).

## Architecture
`parse_rule_file(path)` → dispatch on suffix: `.json` (json.load) → same `AgentRuleSet`. Loader globs `*.json`.

## Related code files
Modify: `detection_rule_loader.py`, `status_monitor.py`, `methods_system.py` (rules files in settings.files),
`rule-tester.tsx` if it shows file text, tests `test_detection_rules_bundled.py`, `test_status_detector*`.
Create: `src/drover/status/rules/*.json` (generated), delete `*.toml` there; migration call in phase-1 helper.

## Implementation steps
1. One-off conversion script (not shipped) → write bundled JSON; test: rule sets equal to the TOML ones.
2. Loader + monitor on `*.json`; remove TOML parsing.
3. Migrate user rules TOML → JSON at start (phase-1 helper).
4. Settings page / rule tester show JSON.

## Todo
- [ ] equality test TOML vs JSON rule sets (run once before deleting TOML)
- [ ] loader + monitor on JSON
- [ ] user rules migration + test
- [ ] UI text

## Success criteria
`test_detection_rules_bundled` and status detector tests pass; a migrated user rule overrides the bundled one.

## Risks
Escaping mistakes change a regex silently → equality test against the original TOML before deletion.

## Security
User rule files only from config dir; regex compile errors reported, never crash the monitor.

## Next
Independent of phases 3–4.
