"""一条命令启动网页版：python run.py

从任意工作目录都能用（脚本自己把项目根目录放进 sys.path），
等价于 python -m ahlcg.web.app。
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from ahlcg.web.app import main as run_app

    run_app()


if __name__ == "__main__":
    main()
