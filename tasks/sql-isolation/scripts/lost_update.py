from __future__ import annotations

import threading
import time

from common import cfg_from_env, connect, log, q1, reset_db, start_tx, wait_db, x


def main() -> None:
    cfg = cfg_from_env()
    wait_db(cfg)
    reset_db(cfg)

    start_b = None
    c0 = connect(cfg)
    try:
        start_b = q1(c0, "SELECT balance FROM accounts WHERE owner='bob'")
    finally:
        c0.close()

    log("MAIN", f"Стартовый баланс bob = {start_b}")

    # Две транзакции делают read-modify-write без блокировок:
    # обе читают 100, обе пишут 110 => потерянное обновление (ожидали 120).
    t1_read = threading.Event()
    t2_read = threading.Event()

    def tx(name: str, read_evt: threading.Event, other_read_evt: threading.Event) -> None:
        c = connect(cfg)
        try:
            start_tx(c, "READ COMMITTED")
            log(name, "START TRANSACTION (READ COMMITTED)")
            b = q1(c, "SELECT balance FROM accounts WHERE owner='bob'")
            log(name, f"SELECT balance(bob) -> {b}")
            read_evt.set()
            other_read_evt.wait(timeout=10)

            new_b = int(b) + 10
            log(name, f"UPDATE accounts SET balance={new_b} WHERE owner='bob'")
            x(c, "UPDATE accounts SET balance=%s WHERE owner='bob'", (new_b,))
            time.sleep(0.3)
            log(name, "COMMIT")
            c.commit()
        finally:
            c.close()

    th1 = threading.Thread(target=tx, args=("T1", t1_read, t2_read), daemon=True)
    th2 = threading.Thread(target=tx, args=("T2", t2_read, t1_read), daemon=True)
    th1.start()
    time.sleep(0.1)
    th2.start()
    th1.join(timeout=20)
    th2.join(timeout=20)

    c = connect(cfg)
    try:
        final_b = q1(c, "SELECT balance FROM accounts WHERE owner='bob'")
        log("MAIN", f"Итог в БД: balance(bob) = {final_b}")
        log("MAIN", "Ожидали 120, но получили 110 => lost update")
    finally:
        c.close()


if __name__ == "__main__":
    main()
