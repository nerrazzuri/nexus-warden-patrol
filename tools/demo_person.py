"""演示站点用:让一台仿真机器人「看见一个人」(liang-d5 第 5 轮前:测手机后台值守的响铃档)。

走的是真机器人上检测程序报人的同一条路:连代理本机的人员桥(本机套接字不用密钥),
每 0.5 秒报一帧「前摄像头 1 个人」。代理 3 帧里 2 帧有人就算确认,站点在布防时报 P1
``dog_sees_person``。报满 ``--seconds`` 秒后改报空画面,代理 20 秒后确认人走了(那条报警还开着,
写成「看不到了」)。演示站点要用 ``--persons-sim`` 起。

    .venv/bin/python tools/demo_person.py --socket /tmp/nexwar-demo-8520-A-persons.sock --seconds 30
    (套接字 = /tmp/nexwar-demo-<站点端口>-<机器人>-persons.sock,演示站点起来时打印)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from nexwar_contract.persbridge import PROTO, Hello, Person, Persons, encode


async def run(sock: Path, seconds: float, range_m: float, gone_s: float) -> int:
    rd, w = await asyncio.open_unix_connection(str(sock))
    w.write(encode(Hello(proto=PROTO, name="demo-person")))
    await w.drain()
    back = json.loads(await asyncio.wait_for(rd.readline(), 5))
    if back.get("t") != "hello":
        print(f"人员桥没答应:{back}", file=sys.stderr)
        return 1
    seq = 0
    t0 = time.monotonic()
    print(f"报 {seconds:.0f} 秒有人({range_m} m),再报 {gone_s:.0f} 秒没人", flush=True)
    while time.monotonic() - t0 < seconds + gone_s:
        seq += 1
        people = (Person(bearing_deg=5.0, range_m=range_m, score=0.9),) \
            if time.monotonic() - t0 < seconds else ()
        w.write(encode(Persons(seq=seq, stamp_ns=time.time_ns(), camera="front", people=people)))
        await w.drain()
        await asyncio.sleep(0.5)
    w.close()
    print("报完了", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--socket", type=Path, required=True, help="代理的人员桥套接字")
    ap.add_argument("--seconds", type=float, default=30, help="报多少秒有人(默认 30)")
    ap.add_argument("--range", type=float, default=4.0, help="人离机器人几米(默认 4)")
    ap.add_argument("--gone", type=float, default=25, help="之后报多少秒没人(默认 25)")
    a = ap.parse_args(argv)
    if not a.socket.exists():
        raise SystemExit(f"{a.socket} 不在:演示站点要用 --persons-sim 起")
    return asyncio.run(run(a.socket, a.seconds, a.range, a.gone))


if __name__ == "__main__":
    raise SystemExit(main())
