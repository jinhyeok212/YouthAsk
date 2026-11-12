"""Run C01 repetitions, then validate the completed handoff artifacts."""

from scripts.run_c01_comparison import main as run_comparison
from scripts.validate_c01_results import main as validate_results


if __name__ == "__main__":
    run_comparison()
    validate_results()
