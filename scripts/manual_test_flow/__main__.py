"""命令行入口：python -m scripts.manual_test_flow [参数]。"""
from __future__ import annotations

import argparse
import sys

from .client import ApiError, Client
from .flows import Runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.manual_test_flow", description="ADP 前后端联通 + 业务闭环 自动验收")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001", help="后端地址或同源代理（Vite 5173）")
    parser.add_argument("--writer-id", required=True, help="创建单据的账号（登录名或手机号）")
    parser.add_argument("--writer-password", required=True)
    parser.add_argument("--verifier-id", required=True, help="负责核验/审批的另一个账号，必须与写入账号不同")
    parser.add_argument("--verifier-password", required=True)
    parser.add_argument("--only", default=None, help="只跑名称包含该子串的阶段，例如 --only 阶段 13")
    args = parser.parse_args(argv)

    runner = Runner(
        Client(args.base_url, args.writer_id, args.writer_password),
        Client(args.base_url, args.verifier_id, args.verifier_password),
        only=args.only,
    )
    try:
        return runner.run()
    except ApiError as error:
        print(f"\n致命错误：{error}")
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
