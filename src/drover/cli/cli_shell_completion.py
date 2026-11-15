"""`dr completion bash|zsh|fish|powershell`: tab completion scripts generated from the argparse tree.

Subcommands, their flags and fixed choices come from the parser, so new commands complete without edits here.
Agent names come from `dr ls --names`, which never starts the daemon.
"""

from __future__ import annotations

import argparse

SHELLS = ["bash", "zsh", "fish", "powershell"]
PROGRAMS = ["dr", "hd"]


def add_completion_parser(sub) -> None:
    completion = sub.add_parser("completion", help="print a tab-completion script: bash | zsh | fish | powershell")
    completion.add_argument("shell", choices=SHELLS)


def command_table(parser: argparse.ArgumentParser) -> dict[str, tuple[list[str], list[str]]]:
    """{subcommand: (flags, choices of its positionals)} read from the parser."""
    sub_action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    table = {}
    for name, sub in sub_action.choices.items():
        flags, choices = [], []
        for action in sub._actions:
            if action.option_strings:
                flags += [o for o in action.option_strings if o.startswith("--") and o != "--help"]
            elif action.choices:
                choices += [str(c) for c in action.choices]
        table[name] = (flags, choices)
    return table


def _bash(table: dict) -> str:
    cases = "\n".join(f'    {name}) flags="{" ".join(f)}"; words="{" ".join(c)}" ;;'
                      for name, (f, c) in table.items())
    return f"""# drover completion for bash. Add to ~/.bashrc:  eval "$(dr completion bash)"
_dr_complete() {{
  local cur=${{COMP_WORDS[COMP_CWORD]}} flags="" words=""
  if [ "$COMP_CWORD" -eq 1 ]; then
    COMPREPLY=($(compgen -W "{' '.join(table)}" -- "$cur")); return
  fi
  case "${{COMP_WORDS[1]}}" in
{cases}
  esac
  if [[ $cur == -* ]]; then COMPREPLY=($(compgen -W "$flags" -- "$cur")); return; fi
  COMPREPLY=($(compgen -W "$words $(dr ls --names 2>/dev/null)" -- "$cur"))
}}
complete -o default -F _dr_complete {' '.join(PROGRAMS)}
"""


def _zsh(table: dict) -> str:
    return ("# drover completion for zsh. Add to ~/.zshrc:  eval \"$(dr completion zsh)\"\n"
            "autoload -U +X bashcompinit && bashcompinit\n" + _bash(table).split("\n", 1)[1])


def _fish(table: dict) -> str:
    lines = ["# drover completion for fish:  dr completion fish > ~/.config/fish/completions/dr.fish"]
    for prog in PROGRAMS:
        lines.append(f'complete -c {prog} -f -n "__fish_use_subcommand" -a "{" ".join(table)}"')
        for name, (flags, choices) in table.items():
            seen = f'-n "__fish_seen_subcommand_from {name}"'
            lines += [f"complete -c {prog} -f {seen} -l {flag[2:]}" for flag in flags]
            lines.append(f'complete -c {prog} -f {seen} -a "{" ".join(choices)} (dr ls --names 2>/dev/null)"')
    return "\n".join(lines) + "\n"


def _ps_list(values: list[str]) -> str:
    return "@(" + ", ".join(f"'{v}'" for v in values) + ")"


def _powershell(table: dict) -> str:
    flags = "\n".join(f"    '{name}' = {_ps_list(f)}" for name, (f, _) in table.items())
    choices = "\n".join(f"    '{name}' = {_ps_list(c)}" for name, (_, c) in table.items())
    return f"""# drover completion for PowerShell. Add to $PROFILE:  dr completion powershell | Out-String | Invoke-Expression
$drFlags = @{{
{flags}
}}
$drChoices = @{{
{choices}
}}
Register-ArgumentCompleter -Native -CommandName {', '.join(PROGRAMS)} -ScriptBlock {{
  param($wordToComplete, $commandAst, $cursorPosition)
  $words = @($commandAst.CommandElements | ForEach-Object {{ $_.ToString() }})
  $typed = if ($wordToComplete) {{ $words.Count - 1 }} else {{ $words.Count }}
  if ($typed -le 1) {{
    $candidates = $drFlags.get_Keys()  # not .Keys: `dr keys` makes 'keys' an entry, which .Keys would return
  }} elseif ($wordToComplete -like '-*') {{
    $candidates = $drFlags[$words[1]]
  }} else {{
    $names = @()
    if (Get-Command dr -CommandType Application -ErrorAction SilentlyContinue) {{ $names = @(& dr ls --names 2>$null) }}
    $candidates = @($drChoices[$words[1]]) + $names
  }}
  $candidates | Where-Object {{ $_ -and $_ -like "$wordToComplete*" }} | Sort-Object -Unique | ForEach-Object {{
    [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
  }}
}}
"""


RENDERERS = {"bash": _bash, "zsh": _zsh, "fish": _fish, "powershell": _powershell}


def cmd_completion(args, parser: argparse.ArgumentParser) -> int:
    print(RENDERERS[args.shell](command_table(parser)), end="")
    return 0
