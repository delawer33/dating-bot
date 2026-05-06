from __future__ import annotations

import threading
import time

from common import cfg_from_env, connect, log, q1, reset_db, start_tx, wait_db, x


def main() -> None:
    cfg = cfg_from_env()
    wait_db(cfg)
    reset_db(cfg)

    t1_ready = threading.Event()
    t2_done_read = threading.Event()

    def tx1() -> None:
        c1 = connect(cfg)
        try:
            start_tx(c1, "READ UNCOMMITTED")
            log("T1", "START TRANSACTION (READ UNCOMMITTED)")
            log("T1", "UPDATE notes SET value=999 WHERE id=1 (без COMMIT)")
            x(c1, "UPDATE notes SET value=%s WHERE id=%s", (999, 1))
            t1_ready.set()
            t2_done_read.wait(timeout=10)
            log("T1", "ROLLBACK (откатываем изменения)")
            c1.rollback()
        finally:
            c1.close()

    def tx2() -> None:
        t1_ready.wait(timeout=10)
        c2 = connect(cfg)
        try:
            start_tx(c2, "READ UNCOMMITTED")
            log("T2", "START TRANSACTION (READ UNCOMMITTED)")
            v1 = q1(c2, "SELECT value FROM notes WHERE id=1")
            log("T2", f"SELECT value FROM notes WHERE id=1 -> {v1} (грязное чтение)")
            t2_done_read.set()
            time.sleep(0.5)
            v2 = q1(c2, "SELECT value FROM notes WHERE id=1")
            log("T2", f"SELECT value FROM notes WHERE id=1 -> {v2} (после ROLLBACK в T1)")
            log("T2", "COMMIT")
            c2.commit()
        finally:
            c2.close()

    th1 = threading.Thread(target=tx1, daemon=True)
    th2 = threading.Thread(target=tx2, daemon=True)
    th1.start()
    th2.start()
    th1.join(timeout=20)
    th2.join(timeout=20)

    c = connect(cfg)
    try:
        final_v = q1(c, "SELECT value FROM notes WHERE id=1")
        log("MAIN", f"Итог в БД: notes.value(id=1) = {final_v}")
    finally:
        c.close()


if __name__ == "__main__":
    main()
