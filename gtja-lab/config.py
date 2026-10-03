# -*- coding: utf-8 -*-
"""全局配置：DolphinDB 连接信息与本地路径。

所有脚本都从这里读取连接参数，改一处即可全局生效。
"""
import os

# ---------------- DolphinDB 连接 ----------------
HOST = "127.0.0.1"
PORT = 8848
USER = "admin"
PASSWORD = "123456"

# ---------------- DolphinDB 安装路径 ----------------
# getHomeDir() 返回的就是这个 server 目录
DDB_HOME = r"C:\d\hub\run\DolphinDB_Win64_V2.00.19\server"

# ---------------- 客户端本地公式模块 ----------------
# 因子公式的「源文件」放在客户端，由 loader.py 注入到服务端会话中执行，
# 不再依赖服务端的 {home}/modules 目录（服务端已经没有任何因子模块了）。
MODULES_LOCAL = r"c:\d\hub\dolphin\modules-local"
# lab 当前用不到的模块（alphalens / ta / mytt / wq101alpha / *Res / *StreamTest）
# 已移到同级的 modules-unused/，需要时再移回来并加进下面的 LOCAL_MODULES。

# 本地模块名（不含 .dos 后缀），按依赖顺序排列
LOCAL_MODULES = ("gtja191Alpha", "gtja191Prepare")

# ---------------- 本项目的 DolphinDB 脚本目录 ----------------
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")

# ---------------- 数据库 / 表命名 ----------------
DB_URI = "dfs://gtja"          # 市场数据与因子库
MARKET_TB = "market"           # 日频行情表
FACTOR_TB = "factor"           # 因子值表
