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
        for problem in set_problems(scenarios, load_config()["sets"].get(args.set, {})):
            print(f"  set: {problem}")
    elif args.cmd == "tasks":
        from . import inbox
        inbox.write_tasks(args.set, args.ids)
    elif args.cmd == "import":
        from . import inbox
        inbox.import_drafts(args.set, args.overwrite_drafts)
    elif args.cmd == "spent":
        from .cost import total_spent
        print(f"${total_spent():.2f}")


if __name__ == "__main__":
    main()
