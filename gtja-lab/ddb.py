# -*- coding: utf-8 -*-
"""DolphinDB 会话工具：连接、执行脚本文件、小结果打印。"""
import os
import sys

import dolphindb as ddb

import config


def connect():
    """建立并返回一个 DolphinDB session。"""
    s = ddb.session()
    s.connect(config.HOST, config.PORT, config.USER, config.PASSWORD)
    return s


def run_file(s, path, preamble=""):
    """执行一个 DolphinDB 脚本文件（.dos），path 传绝对路径。

    preamble 会拼在脚本最前面，用于传入运行参数（脚本内用 defined() 做默认值保护）。
    脚本是自包含的（内部含 login / use 模块），因此既可以用本函数跑，
    也可以直接在 VS Code 的 DolphinDB 插件里打开运行。
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        script = f.read()
    print(f"\n===== running {path} =====")
    return s.run(preamble + script)


def show(obj, title=None):
    if title:
        print(f"\n----- {title} -----")
    print(obj)
    return obj


if __name__ == "__main__":
    sess = connect()
    print("connected to", config.HOST, config.PORT)
    print("version:", sess.run("version()"))
    print("homeDir:", sess.run("getHomeDir()"))
