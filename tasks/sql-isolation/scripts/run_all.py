from __future__ import annotations

from common import log

import dirty_read
import lost_update
import non_repeatable_read
import phantom_read


def main() -> None:
    log("RUN", "=== DIRTY READ ===")
    dirty_read.main()
    print()

    log("RUN", "=== NON-REPEATABLE READ ===")
    non_repeatable_read.main()
    print()

    log("RUN", "=== PHANTOM READ ===")
    phantom_read.main()
    print()

    log("RUN", "=== LOST UPDATE ===")
    lost_update.main()


if __name__ == "__main__":
    main()
