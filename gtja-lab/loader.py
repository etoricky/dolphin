# -*- coding: utf-8 -*-
"""客户端模块加载器：把本地 modules-local 里的 .dos 公式注入到 DolphinDB 会话。

背景：
    DolphinDB 的 `use` 只能从「服务端」的 moduleDir 加载模块。
    本模块换一条路 —— 由客户端读取本地文件，通过 run() 把函数定义发给服务端，
    服务端把它们编译进「当前会话」。

效果：
    * 公式的源文件放在客户端（modules-local/），由客户端掌控、可随时改；
    * 计算仍然 100% 在服务端执行，客户端只负责“递送源码”。

关于 modules-local 里的文件格式：
    这里存放的是「客户端版」.dos —— 已经去掉了 `module xxx` 声明，
    并把跨模块引用 `gtja191Alpha::gtjaAlpha1` 还原成普通函数名 `gtjaAlpha1`。
    也就是说，每个 .dos 就是一份普通的 `def` 脚本，可以直接注入会话执行。

    为了让本加载器对「原版（未清理）」的文件也健壮，下面仍会做一次归一化：
    去掉 module 声明行、去掉 `模块名::` 前缀。对已清理过的文件是无副作用的空操作。
"""
import os
import re

import config

# 匹配 `module gtja191Alpha` 这样的声明行（要求整行只有 module + 一个词）
_MODULE_DECL = re.compile(r'(?m)^\s*module\s+\S+\s*$')


def _read_module(path):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    return _MODULE_DECL.sub("", src)


def load_modules(sess, names=("gtja191Alpha", "gtja191Prepare"), module_dir=None):
    """把本地 .dos 注入到 sess 对应的服务端会话，返回注入的字符数。"""
    module_dir = module_dir or config.MODULES_LOCAL
    parts = []
    for name in names:
        path = os.path.join(module_dir, name + ".dos")
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        parts.append(_read_module(path))

    script = "\n".join(parts)

    # 兜底：对未清理的原版文件，去掉 `模块名::` 命名空间前缀
    for name in names:
        script = script.replace(name + "::", "")

    sess.run(script)
    return len(script)


if __name__ == "__main__":
    from ddb import connect

    s = connect()
    n = load_modules(s)
    print(f"injected {n} chars from {config.MODULES_LOCAL}")
    print("probe gtjaAlpha1(matrix):", s.run("gtjaAlpha1(matrix(1 2 3), matrix(1 2 3), matrix(1 2 3))"))
