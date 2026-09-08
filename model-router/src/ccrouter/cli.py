"""Command line: run the proxy, explain a decision, read the log, check the setup."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import __version__, classifier, config, proxy, rules, signals
from .config import Config, tier_name


def _body_from(args: argparse.Namespace) -> dict[str, Any]:
    if args.request:
        raw = sys.stdin.read() if args.request == "-" else Path(args.request).read_text()
        return json.loads(raw)
    prompt = " ".join(args.prompt) or sys.stdin.read()
    return {
        "model": args.assume_model,
        "system": "You are Claude Code, Anthropic's official CLI for Claude.",
        "tools": [{"name": n} for n in ("Task", "Bash", "Read", "Edit", "Write", "Glob", "Grep")],
        "messages": [{"role": "user", "content": prompt}],
    }


def cmd_explain(cfg: Config, args: argparse.Namespace) -> int:
    body = _body_from(args)
    s = signals.extract(body, cfg)
    verdict = rules.evaluate(s, cfg)
    verdict = classifier.refine(verdict, s, cfg)

    print(f"prompt      {s.prompt[:100]!r}")
    print(f"phase       {s.phase}  turn={s.turn_index}  subagent={s.is_subagent}"
          f"{' (' + s.agent_hint + ')' if s.agent_hint else ''}")
    print(f"signals     files={s.files_mentioned} steps={s.enumerated_steps} "
          f"failures={s.failures} thrash={s.thrash} broad={s.broad_scope} "
          f"stacktrace={s.has_stacktrace} thinking={s.thinking_budget} "
          f"context~{s.context_tokens}tok")
    print("\ncontributions")
    for c in verdict.contributions:
        print("  " + c.describe())
    print(f"\nscore       {verdict.score:+.2f}  "
          f"(cheap<={cfg.policy.cheap_threshold}, opus>={cfg.policy.expensive_threshold})")
    print(f"confident   {verdict.confident}"
          f"{'' if verdict.confident else '  -> local classifier consulted if enabled'}")
    print(f"\nDECISION    {tier_name(verdict.tier)}  ->  {cfg.model_for(verdict.tier)}"
          f"   [{verdict.source}]")
    return 0


def cmd_serve(cfg: Config, args: argparse.Namespace) -> int:
    server = proxy.ProxyServer(cfg, verbose=not args.quiet)
    host, port = server.server_address[:2]
    print(f"ccrouter {__version__} listening on http://{host}:{port} -> {cfg.upstream}")
    print("  tiers: " + ", ".join(f"{k}={v}" for k, v in cfg.tiers.items()))
    print(f"  log:   {os.path.expanduser(cfg.log_file)}")
    print(f"\n  export ANTHROPIC_BASE_URL=http://{host}:{port}\n")
    if str(host) not in ("127.0.0.1", "::1", "localhost"):
        print(f"  WARNING: bound to {host}, not loopback. This proxy relays your")
        print("           API credentials verbatim -- do not expose it on a network.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.server_close()
    return 0


def cmd_stats(cfg: Config, args: argparse.Namespace) -> int:
    path = Path(os.path.expanduser(args.log or cfg.log_file))
    if not path.is_file():
        print(f"no decision log at {path}")
        return 1

    tiers: Counter[str] = Counter()
    tokens: defaultdict[str, int] = defaultdict(int)
    sources: Counter[str] = Counter()
    rewrites = 0
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines()[-args.limit:]:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        total += 1
        name = tier_name(int(entry.get("tier", 1)))
        tiers[name] += 1
        tokens[name] += int(entry.get("context_tokens", 0))
        sources[entry.get("source", "?")] += 1
        rewrites += bool(entry.get("rewrote"))

    if not total:
        print("decision log is empty")
        return 1

    print(f"{total} decisions  ({rewrites} rewrote the model)\n")
    price = cfg.pricing_per_mtok_in
    ceiling = cfg.policy.max_tier
    routed = baseline = 0.0
    for name in config.TIER_NAMES:
        if not tiers[name]:
            continue
        mtok = tokens[name] / 1e6
        routed += mtok * price.get(name, 0.0)
        baseline += mtok * price.get(ceiling, 0.0)
        print(f"  {name:<7} {tiers[name]:>5} calls  {tokens[name]:>10,} input tok "
              f"({tiers[name] / total:5.1%})")
    print("\n  by source: " + ", ".join(f"{k}={v}" for k, v in sources.most_common()))
    print(f"\n  estimated input cost   ${routed:.3f}")
    print(f"  all-{ceiling} baseline    ${baseline:.3f}")
    print(f"  estimated saving       ${baseline - routed:.3f}  "
          f"({0 if not baseline else (baseline - routed) / baseline:.0%})")
    return 0


def cmd_doctor(cfg: Config, args: argparse.Namespace) -> int:
    ok = True
    print(f"ccrouter {__version__}  python {sys.version.split()[0]}")
    print(f"upstream          {cfg.upstream}")
    for name, model in cfg.tiers.items():
        print(f"  tier {name:<7} {model}")

    base = os.environ.get("ANTHROPIC_BASE_URL", "")
    print(f"\nANTHROPIC_BASE_URL {base or '(unset)'}")
    if not base:
        print("  -> set it to the listen address before starting Claude Code")
        ok = False
    if os.environ.get("ANTHROPIC_MODEL"):
        print(f"  !! ANTHROPIC_MODEL={os.environ['ANTHROPIC_MODEL']} pins the requested model;")
        print("     the router still rewrites it, but /model in the UI will look wrong")

    if cfg.llm.enabled:
        print(f"\nlocal classifier   {cfg.llm.model} at {cfg.llm.endpoint}")
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            request = urllib.request.Request(
                cfg.llm.endpoint,
                data=json.dumps({"model": cfg.llm.model, "max_tokens": 4,
                                 "messages": [{"role": "user", "content": "say haiku"}]}).encode(),
                headers={"content-type": "application/json"})
            with opener.open(request, timeout=cfg.llm.timeout_s) as response:
                answer = json.loads(response.read())["choices"][0]["message"]["content"]
            print(f"  reachable, replied {answer.strip()[:40]!r}")
        except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
            print(f"  UNREACHABLE ({type(exc).__name__}) -- routing falls back to rules only")
            ok = False
        print(f"  prompt template: {cfg.llm.prompt_file or '(bundled prompts/classify.md)'}")
    else:
        print("\nlocal classifier   disabled (rules only)")

    print(f"\ndecision log       {os.path.expanduser(cfg.log_file)}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccrouter", description=__doc__)
    parser.add_argument("--config", help="path to router.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the routing proxy")
    serve.add_argument("--listen", help="override host:port")
    serve.add_argument("--quiet", action="store_true")
    serve.set_defaults(func=cmd_serve)

    explain = sub.add_parser("explain", help="show how a prompt would route, and why")
    explain.add_argument("prompt", nargs="*")
    explain.add_argument("--request", help="a full /v1/messages JSON body, or - for stdin")
    explain.add_argument("--assume-model", default="claude-sonnet-5")
    explain.set_defaults(func=cmd_explain)

    stats = sub.add_parser("stats", help="summarise the decision log")
    stats.add_argument("--log")
    stats.add_argument("--limit", type=int, default=100_000)
    stats.set_defaults(func=cmd_stats)

    doctor = sub.add_parser("doctor", help="check config, endpoints and environment")
    doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = config.load(args.config)
    if getattr(args, "listen", None):
        cfg = config.replace(cfg, listen=args.listen)
    return int(args.func(cfg, args))


if __name__ == "__main__":
    raise SystemExit(main())
