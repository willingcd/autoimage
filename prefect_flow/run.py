"""
Run the Prefect multi-engine build flow from CLI.

Usage (from project root):
  python -m prefect_flow.run --model-id Qwen/Qwen3.5-35B-A3B-FP8 [--output-root /output]

Requires GITHUB_TOKEN (and any engine-specific env) in the environment.
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on path when run as python -m prefect_flow.run
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from prefect_flow.flow import multi_engine_build_flow


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-engine build flow (Prefect)")
    parser.add_argument("--model-id", required=True, help="Full model ID (e.g. Qwen/Qwen3.5-35B-A3B-FP8)")
    parser.add_argument(
        "--output-root",
        default="/output",
        help="Base output directory; each engine writes to <output_root>/<engine_subdir>/ (default: /output)",
    )
    args = parser.parse_args()

    results = multi_engine_build_flow(model_id=args.model_id, output_root=args.output_root)

    failed = [r for r in results if r["returncode"] != 0]
    if failed:
        for r in failed:
            print(f"[{r['engine_id']}] exit code {r['returncode']}", file=sys.stderr)
            if r["stderr"]:
                print(r["stderr"], file=sys.stderr)
        sys.exit(1)
    print("All engine builds completed successfully.")
    for r in results:
        print(f"  {r['engine_id']} -> {r['output_dir']}")


if __name__ == "__main__":
    main()
