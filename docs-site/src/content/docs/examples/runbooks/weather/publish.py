#!/usr/bin/env python3
"""publish phase — pretty-print the AI's advice (received as JSON on STDIN).

Replace this with whatever sink you want: POST to Slack, write a file, open a
notification… The contract is just "read the result JSON from stdin".
"""

import json
import sys


def main() -> None:
    data = json.load(sys.stdin)

    print(f"\n🧥 {data.get('summary', '')}\n")
    for item in data.get("outfit", []) or []:
        print(f"  • {item}")

    risks = data.get("risks") or []
    if risks:
        print("\n⚠ Risks")
        for r in risks:
            print(f"  • {r}")

    tips = data.get("tips") or []
    if tips:
        print("\n💡 Tips")
        for t in tips:
            print(f"  • {t}")
    print()


if __name__ == "__main__":
    main()
