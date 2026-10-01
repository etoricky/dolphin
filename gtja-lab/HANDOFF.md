# gtja-lab 交接说明

> 换开发机器时：`git clone` 本仓库，照第 7 节做即可。
> 本文件只记录**代码里看不出来的**设计决策、约定和踩过的坑。

---

## 1. 这是什么

DolphinDB 上的 **GTJA191 因子计算 + 横截面分层回测** 实验台。

核心约定：**公式源码放在客户端，计算 100% 在服务端执行。**

---

## 2. 环境

| 项 | 值 |
|---|---|
| DolphinDB Server | 2.00.19，`127.0.0.1:8848`，`admin` / `123456` |
| server home | `C:\d\hub\run\DolphinDB_Win64_V2.00.19\server` |
| Python | 3.10（`pip install dolphindb`，实测 3.0.6.0） |
| 服务端 `{home}/modules` | **已清空**（故意为之，见第 4 节） |

---

## 3. 目录与职责

```
dolphin/
├─ modules-local/                     # 客户端公式源码（lab 在用）
│   ├─ gtja191Alpha.dos               #   191 个因子公式
│   ├─ gtja191Prepare.dos             #   面板准备 + gtjaCalAlpha1..191
│   └─ datatest.csv                   #   行情原始数据（~177MB，合成数据）
├─ modules-unused/                    # 暂不用的模块
│   └─ alphalens / ta / mytt / wq101alpha / gtja191AlphaRes / gtja191StreamTest
└─ gtja-lab/
    ├─ config.py                      # 连接参数、路径、LOCAL_MODULES
    ├─ ddb.py                         # 建会话 / 执行 .dos / 打印
    ├─ loader.py                      # 把 modules-local 注入服务端会话【核心】
    ├─ run.py                         # 入口：python run.py 1|2|3|4|all
    ├─ plot.py                        # 画分层净值曲线
    ├─ scripts/
    │   ├─ 01_create_market_db.dos    # 建库 + 导入行情
    │   ├─ 02_calc_factors.dos        # 算因子并落库
    │   └─ 03_backtest.dos            # 分层回测
    └─ output/                        # 生成的 CSV / PNG（已 gitignore）
```

数据流：`datatest.csv` →（01）`dfs://gtja/market` →（02）`dfs://gtja/factor` →（03）回测 + 出图。

---

## 4. 关键机制：客户端模块注入

**为什么这么做**

服务端 `{home}/modules` 下的因子模块被移走了（不想依赖服务端 modules，也不想改 `dolphindb.cfg`），
所以 `use gtja191Alpha` 现在会报 `Can't find module [gtja191Alpha]`。

**怎么做**

`loader.py` 读取本地 `.dos` → 去掉 `module xxx` 声明 → 用 `run()` 把函数定义发给服务端 →
服务端把这些 `def` 编译进**当前会话**。

- 源码归客户端（`modules-local/`），由客户端掌控；
- 执行仍在服务端，客户端只负责「递送源码」。

**三条必须记住的**

1. **注入是「每会话一次」的** —— 函数只活在服务端会话内存里，不落盘。
   每次新建连接都要重新注入（`run.py` 已自动处理）。
2. **没有模块隔离** —— 所有函数进入会话全局命名空间，重名会互相覆盖 / 报错。
3. **VS Code 插件的会话是独立的** —— 在插件里跑 `scripts/*.dos` 需要先手动注入一遍
   `modules-local/` 的内容，否则会报 `gtjaCalAlpha1 is not defined`。
   正常用法是走 `python run.py ...`。

---

## 5. 踩过的坑（重要）

### 5.1 `.dos` 本地化改造的规则

要把服务端模块拍平成「客户端版」，需要：

- 删掉 `module <名字>` 声明行
- 把跨模块引用 `gtja191Alpha::gtjaAlpha1` 还原成 `gtjaAlpha1`
- **但是 `::内置函数(...)` 这种调用必须原样保留！**

最后一条最容易翻车。`ta.dos` 里大量这种写法：

```dolphindb
def ma(close, timePeriod=30, maType=0){
 	return ::ma(close, timePeriod, maType)   // :: 表示「调用内置 ma」
}
```

这是「用模块内的名字包装内置实现」。如果把 `::ma` 也改成 `::taMa`，
就变成**自己调自己**，直接爆栈（`A recursive function exceeds the specified maximum depth [1000]`）。
`mytt.dos` 里的 `::abs` / `::pow` / `::sqrt` / `::iif` 同理。

### 5.2 函数名不能与 DolphinDB 内置重名

会话里定义同名函数会直接报 `Not allowed to overwrite existing built-in functions [xxx]`。

已做的改名：

| 文件 | 原函数名 | 改为 |
|---|---|---|
| `ta.dos` | `var` `beta` `sma` `ema` `wma` `dema` `tema` `trima` `kama` `t3` `ma` | 加 `ta` 前缀：`taVar` `taBeta` `taSma` … `taT3` `taMa` |
| `mytt.dos` | `BETWEEN` | `myttBetween` |

> 以后自己写包装函数时同样注意：**别跟内置函数重名**。

### 5.3 多个模块的同名元数据函数

`gtja191Alpha` / `ta` / `mytt` / `wq101alpha` / `alphalens` 都定义了 `module_info`，
同时注入会报 `Can't redefine function/procedure module_info`。
已分别改名为 `<模块名>ModuleInfo`。

### 5.4 列名适配（market 表 ≠ 标准字段名）

`market` 表用的是**自定义列名**：

| 标准字段（GTJA191 要求） | market 实际列名 |
|---|---|
| tradetime / securityid | `Timestamp` / `Symbol` |
| open / close / high / low | `MidOpen` / `MidClose` / `MidHigh` / `MidLow` |
| vol / vwap | `BarVolume` / `BarVwap` |
| index_open / index_close | `IndexOpen` / `IndexClose` |

`02_calc_factors.dos` 用官方辅助函数 `prepareData` 做映射，**模块本身不改动**：

```dolphindb
data = prepareData(rawData = rawData, startTime = startTime, endTime = endTime,
                   securityidName = "Symbol",     tradetimeName  = "Timestamp",
                   openName       = "MidOpen",    closeName      = "MidClose",
                   highName       = "MidHigh",    lowName        = "MidLow",
                   volumeName     = "BarVolume",  vwapName       = "BarVwap",
                   indexCloseName = "IndexClose", indexOpenName  = "IndexOpen")
```

映射之后 `data` 的字段名就是标准名，后续逻辑无需关心原始列名。

### 5.5 幂等开关

| 脚本 | 开关 | 默认 | 含义 |
|---|---|---|---|
| `01` | `RECREATE` | `false` | 库/表已存在就跳过导入；`true` 则删库重建 |
| `02` | `REBUILD_FACTOR` | `true` | `true` 重建因子表；`false` 只补算还没算过的因子 |

命令行覆盖：`python run.py 1 RECREATE=true` / `python run.py 2 REBUILD_FACTOR=false`
（任何 `KEY=VALUE` 参数都会作为变量注入到 .dos 最前面）。

> **改过列名或分区方案后，必须 `RECREATE=true`** ——
> 否则 `01` 会因为「表已存在」而跳过，留下旧 schema，后面步骤就会报莫名其妙的错。
> 删库会连带删掉 `factor` 表，记得重跑 `run.py 2`。

### 5.6 datatest.csv 是合成随机数据

这是 DolphinDB 官方用于**验证因子计算正确性**的数据，价格完全没有连续性：

```
sz000001: 37.7 → 12.6 → 51.1 → 94.7 → 50.2 → 57.1 → 16.1 ...
```

单日收益均值 +181%、标准差 381，直接回测会算出 `1e102` 这种数字。
`03_backtest.dos` 里加了 `RET_CLIP = 0.2`（涨跌停 / 去极值）才让指标落到正常量级。

**结论：回测数字只证明流程能跑通，没有任何策略含义。要看真实效果必须换真实行情。**

---

## 6. DolphinDB 语法备忘

- `rank(x)` 从 **0** 开始；`rank(x, percent=true)` 返回 (0,1] 的百分比排名
- 不支持 `count(distinct x)`，要用 `size(exec distinct x from t)`
- 三元 `? :` 的条件必须是 bool 标量，容易报
  `The condition clause of a ternary operator must return a bool`，改用 `if/else` 更稳
- `move(x, -1)` 取后一个元素（配合 `context by securityid` 算次日收益）
- 矩阵 `flatten()` 是**列优先**
- `panel(行标签, 列标签, [向量...])` 返回矩阵**列表**，且会**排序**标签
- `loadText` 能把 `2010.01.01T00:00:00.000` 自动识别成 `TIMESTAMP`
- `existsTable(db, tb)` 在库不存在时不要直接调，先 `existsDatabase` 判断

---

## 7. 新机器搭建

1. 装 DolphinDB 2.00.x，单节点起在 `8848`，账号 `admin` / `123456`
   （`getHomeDir()` 能返回 server 目录即正常）
2. `pip install dolphindb`（Python 3.10）
3. `git clone` 本仓库（注意 `modules-local/datatest.csv` 有 ~177MB）
4. 改 `gtja-lab/config.py`：
   - `DDB_HOME` → 你机器上的 DolphinDB server 目录
   - `MODULES_LOCAL` → 本仓库 `modules-local/` 的绝对路径
5. 跑：

```powershell
cd gtja-lab
python run.py all
```

---

## 8. 常用命令

```powershell
cd gtja-lab

python run.py all                       # 全流程：建库 -> 因子 -> 回测 -> 出图
python run.py 1                         # 建库 + 导入（已存在则跳过）
python run.py 1 RECREATE=true           # 强制删库重建
python run.py 2                         # 重算因子（重建因子表）
python run.py 2 REBUILD_FACTOR=false    # 只补算新增因子
python run.py 3 4 ja5                   # 回测并画 ja5
python loader.py                        # 单独验证客户端模块能否注入
```

`scripts/*.dos` 也可以直接在 VS Code 的 DolphinDB 插件里跑，但**需要先注入客户端模块**
（见 4.3），否则 `02` 会报 `gtjaCalAlpha1 is not defined`。
