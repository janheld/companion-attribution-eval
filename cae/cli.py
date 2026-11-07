"""Command line entry point: python -m cae <command> ..."""

import argparse


def main() -> None:
    p = argparse.ArgumentParser(prog="cae")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate scenario drafts for a set")
    g.add_argument("--set", required=True)
    g.add_argument("--ids", nargs="*", help="only these scenario ids")
    g.add_argument("--revise", action="store_true", help="revise rejected / needs_edit scenarios")
    g.add_argument("--yes", action="store_true", help="skip the cost confirmation prompt")

    r = sub.add_parser("review", help="open the local review page")
    r.add_argument("--set", required=True)
    r.add_argument("--port", type=int, default=8765)

    f = sub.add_parser("freeze", help="freeze a fully approved set")
    f.add_argument("--set", required=True)

    s = sub.add_parser("status", help="count scenarios per status")
    s.add_argument("--set", required=True)

    it = sub.add_parser("tasks", help="write task files for scenarios to be written without the API")
    it.add_argument("--set", required=True)
    it.add_argument("--ids", nargs="*")

    ii = sub.add_parser("import", help="import written scenarios from the inbox as drafts")
    ii.add_argument("--set", required=True)
    ii.add_argument("--overwrite-drafts", action="store_true", help="also replace existing drafts (never approved ones)")

    ci = sub.add_parser("check-inbox", help="check written scenarios in the inbox before import")
    ci.add_argument("--set", required=True)
    ci.add_argument("--ids", nargs="*")

    d = sub.add_parser("diff", help="word diff of revised drafts against their previous version")
    d.add_argument("--set", required=True)
    d.add_argument("--ids", nargs="*")

    sub.add_parser("spent", help="show total actual API spend from the ledger")

    args = p.parse_args()
    if args.cmd == "generate":
        from . import generate
        if args.revise:
            generate.revise(args.set, args.yes)
        else:
            generate.generate(args.set, args.ids, args.yes)
    elif args.cmd == "review":
        from . import review
        review.serve(args.set, args.port)
    elif args.cmd == "freeze":
        from . import freeze
        freeze.freeze(args.set)
    elif args.cmd == "status":
        from collections import Counter
        from .schema import load_set, save, sync_status, validate
        scenarios = load_set(args.set)
        for sc in scenarios:
            if sync_status(sc):
                save(sc)
        print(dict(Counter(sc["status"] for sc in scenarios)))
        for sc in scenarios:
            if validate(sc):
                print(f"  {sc['id']}: {'; '.join(validate(sc))}")
        from .generate import load_config
        from .people import set_problems
        cfg = load_config()
        for problem in set_problems(scenarios, cfg["sets"].get(args.set, {}), cfg):
            print(f"  set: {problem}")
        # Heuristic warnings: to be looked at, not necessarily wrong.
        from .checks import (block_problems, fragment_problems, opening_problems, situation_problems,
                             time_problems)
        from .people import _all_pool_names
        for problem in (opening_problems(scenarios) + fragment_problems(scenarios)
                        + situation_problems(scenarios, _all_pool_names())
                        + block_problems(scenarios, cfg["overused_blocks"])):
            print(f"  check: {problem}")
        for sc in scenarios:
            for problem in time_problems(sc):
                print(f"  check: {sc['id']}: {problem}")
    elif args.cmd == "tasks":
        from . import inbox
        inbox.write_tasks(args.set, args.ids)
    elif args.cmd == "import":
        from . import inbox
        inbox.import_drafts(args.set, args.overwrite_drafts)
    elif args.cmd == "check-inbox":
        from . import inbox
        inbox.check_inbox(args.set, args.ids)
    elif args.cmd == "diff":
        from .diff import print_diffs
        print_diffs(args.set, args.ids)
    elif args.cmd == "spent":
        from .cost import total_spent
        print(f"${total_spent():.2f}")


if __name__ == "__main__":
    main()
