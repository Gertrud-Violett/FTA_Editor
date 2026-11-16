"""Run the batch CLI with longer internal time budgets.

    python cli_with_budgets.py <summary-budget-s> <validate-budget-s> <cli args...>

Two commands have a fixed internal time budget the CLI cannot change:
``quantify`` runs the headline cut sets under ``engine.SUMMARY_LIMITS`` (2 s) and
``validate`` the truncation check under ``cutsets.VALIDATE_TIME_BUDGET_S`` (2 s).
A corpus file whose cut sets need longer (R00 and R03 of the b2b corpus) would be
cut short by time there, so its result would depend on the speed of the machine.
The golden generator and a test that compares those files run them through this
script with budgets large enough to finish; nothing else differs from
``python fta_web/run.py <cli args>`` (the modules are imported by bare name from
``fta_web/``, as ``run.py`` does). The working directory is the repo root.
"""
from __future__ import annotations

import os
import sys


def main(argv):
    summary_budget, validate_budget = float(argv[1]), float(argv[2])
    # As fta_web/run.py does: fta_web/ itself on sys.path, modules by bare name.
    sys.path.insert(0, os.path.join(os.getcwd(), "fta_web"))
    import cli  # noqa: E402
    import cutsets  # noqa: E402
    import engine  # noqa: E402

    engine.SUMMARY_LIMITS["timeBudgetS"] = summary_budget
    cutsets.VALIDATE_TIME_BUDGET_S = validate_budget
    return cli.main(argv[3:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
