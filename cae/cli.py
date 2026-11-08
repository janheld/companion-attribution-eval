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

    rn = sub.add_parser("run", help="run the models of a run config on its frozen set")
    rn.add_argument("--config", required=True)
    rn.add_argument("--yes", action="store_true", help="skip the cost confirmation prompt")

    gr = sub.add_parser("grade", help="grade the outputs of a run")
    gr.add_argument("--config", required=True)
    gr.add_argument("--yes", action="store_true")

    co = sub.add_parser("cost", help="offline cost estimate for a run config (no API calls)")
    co.add_argument("--config", required=True)

    gd = sub.add_parser("gold", help="gold set: build | label | eval")
    gd.add_argument("action", choices=["build", "label", "eval"])
    gd.add_argument("--config", nargs="+", default=["configs/dryrun.yaml"],
                    help="run configs whose outputs feed the gold set (build); the first one for eval")
    gd.add_argument("--split", choices=["dev", "heldout"], default="dev")
    gd.add_argument("--port", type=int, default=8766)

    hw = sub.add_parser("handwritten", help="turn gold/handwritten.yaml into a gradable pseudo run")
    hw.add_argument("--config", default="configs/handwritten.yaml")

    ac = sub.add_parser("accumulation", help="exploratory accumulation set: tasks | check | import")
    ac.add_argument("action", choices=["tasks", "check", "import"])

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
        # Versions of one accumulation base share all names and text; set-wide
        # checks look at one version per base.
        seen, scenarios_once = set(), []
        for sc in scenarios:
            base = sc.get("accumulation", {}).get("base_id", sc["id"])
            if base not in seen:
                seen.add(base)
                scenarios_once.append(sc)
        for problem in set_problems(scenarios_once, cfg["sets"].get(args.set, {}), cfg):
            print(f"  set: {problem}")
        # Heuristic warnings: to be looked at, not necessarily wrong.
        from .checks import (block_problems, fragment_problems, opening_problems, situation_problems,
                             time_problems)
        from .people import _all_pool_names
        for problem in (opening_problems(scenarios_once) + fragment_problems(scenarios_once)
                        + situation_problems(scenarios_once, _all_pool_names())
                        + block_problems(scenarios_once, cfg["overused_blocks"])):
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
    elif args.cmd == "run":
        from .run import run
        run(args.config, args.yes)
    elif args.cmd == "grade":
        from .grade import grade
        grade(args.config, args.yes)
    elif args.cmd == "cost":
        from .cost import total_spent
        from .freeze import load_frozen
        from .grade import estimate_before_run
        from .run import estimate, jobs, load_run_config
        cfg = load_run_config(args.config)
        job_list = jobs(cfg, load_frozen(cfg["set"]))
        run_est, grade_est = estimate(cfg, job_list), estimate_before_run(cfg, job_list)
        print(f"{len(job_list)} calls; run ${run_est:.2f}, grading ${grade_est:.2f}, together ${run_est + grade_est:.2f}")
        print(f"spent so far ${total_spent():.2f}; after this config ${total_spent() + run_est + grade_est:.2f}")
    elif args.cmd == "gold":
        from . import gold
        if args.action == "build":
            gold.build(args.config)
        elif args.action == "label":
            gold.serve(args.port)
        else:
            gold.evaluate(args.config, args.split)
    elif args.cmd == "handwritten":
        from .run import import_handwritten
        import_handwritten(args.config)
    elif args.cmd == "accumulation":
        from . import accumulation
        {"tasks": accumulation.write_tasks, "check": accumulation.check, "import": accumulation.import_bases}[args.action]()
    elif args.cmd == "spent":
        from .cost import total_spent
        print(f"${total_spent():.2f}")


if __name__ == "__main__":
    main()
