"""Build optimized comparison indexes, then run the standard repetitions."""

from scripts.build_comparison_indexes_from_baseline import main as build_indexes
from scripts.run_c02_c03_comparison import main as run_comparison


if __name__ == "__main__":
    build_indexes()
    run_comparison()
