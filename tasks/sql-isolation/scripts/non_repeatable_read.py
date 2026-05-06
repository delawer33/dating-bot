from __future__ import annotations

import threading
import time

from common import cfg_from_env, connect, log, q1, reset_db, start_tx, wait_db, x


def main() -> None:
    cfg = cfg_from_env()
    wait_db(cfg)
    reset_db(cfg)

    t1_read1 = threading.Event()
    t2_committed = threading.Event()

    def tx1() -> None:
        c1 = connect(cfg)
        try:
            start_tx(c1, "READ COMMITTED")
            log("T1", "START TRANSACTION (READ COMMITTED)")
            b1 = q1(c1, "SELECT balance FROM accounts WHERE owner='alice'")
            log("T1", f"SELECT balance(alice) -> {b1}")
            t1_read1.set()
            t2_committed.wait(timeout=10)
            b2 = q1(c1, "SELECT balance FROM accounts WHERE owner='alice'")
            log("T1", f"SELECT balance(alice) -> {b2} (non-repeatable read)")
            log("T1", "COMMIT")
            c1.commit()
        finally:
            c1.close()

    def tx2() -> None:
        t1_read1.wait(timeout=10)
        c2 = connect(cfg)
        try:
            start_tx(c2, "READ COMMITTED")
            log("T2", "START TRANSACTION (READ COMMITTED)")
            log("T2", "UPDATE accounts SET balance=balance+50 WHERE owner='alice'")
            x(c2, "UPDATE accounts SET balance=balance+50 WHERE owner='alice'")
            log("T2", "COMMIT")
            c2.commit()
            t2_committed.set()
        finally:
            c2.close()

    th1 = threading.Thread(target=tx1, daemon=True)
    th2 = threading.Thread(target=tx2, daemon=True)
    th1.start()
    time.sleep(0.2)
    th2.start()
    th1.join(timeout=20)
    th2.join(timeout=20)

    c = connect(cfg)
    try:
        final_b = q1(c, "SELECT balance FROM accounts WHERE owner='alice'")
        log("MAIN", f"Итог в БД: balance(alice) = {final_b}")
    finally:
        c.close()


if __name__ == "__main__":
    main()
