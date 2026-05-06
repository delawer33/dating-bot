from __future__ import annotations

import threading
import time

from common import cfg_from_env, connect, log, q1, reset_db, start_tx, wait_db, x


def main() -> None:
    cfg = cfg_from_env()
    wait_db(cfg)
    reset_db(cfg)

    # Демонстрируем phantom на READ COMMITTED: повторный SELECT COUNT(*) в одной транзакции
    # увидит строки, которые были закоммичены другой транзакцией.
    t1_count1 = threading.Event()
    t2_committed = threading.Event()

    def tx1() -> None:
        c1 = connect(cfg)
        try:
            start_tx(c1, "READ COMMITTED")
            log("T1", "START TRANSACTION (READ COMMITTED)")
            c1_1 = q1(c1, "SELECT COUNT(*) FROM orders WHERE amount >= 100")
            log("T1", f"SELECT COUNT(orders.amount>=100) -> {c1_1}")
            t1_count1.set()
            t2_committed.wait(timeout=10)
            c1_2 = q1(c1, "SELECT COUNT(*) FROM orders WHERE amount >= 100")
            log("T1", f"SELECT COUNT(orders.amount>=100) -> {c1_2} (phantom read)")
            log("T1", "COMMIT")
            c1.commit()
        finally:
            c1.close()

    def tx2() -> None:
        t1_count1.wait(timeout=10)
        c2 = connect(cfg)
        try:
            start_tx(c2, "READ COMMITTED")
            log("T2", "START TRANSACTION (READ COMMITTED)")
            log("T2", "INSERT INTO orders(amount)=120 (подходит под WHERE amount>=100)")
            x(c2, "INSERT INTO orders(amount) VALUES (%s)", (120,))
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
        final_cnt = q1(c, "SELECT COUNT(*) FROM orders WHERE amount >= 100")
        log("MAIN", f"Итог в БД: COUNT(amount>=100) = {final_cnt}")
    finally:
        c.close()


if __name__ == "__main__":
    main()
