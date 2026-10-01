"""一键启动入口：在 PyCharm / VS Code 中直接运行本文件即可。

等价于命令行执行 `python -m backend.app`，支持同样的参数（如 --no-crawl、--port 8000）。
"""

from backend.app import main

if __name__ == "__main__":
    main()
