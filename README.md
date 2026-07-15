# grid-agent

面向电力系统工程分析的可扩展 Agent 仓库。当前第一阶段是一个可运行的树状 10 kV 配电馈线故障诊断 Demo，用于验证“拓扑约束 + 量测异常 + 工程规则”的最小闭环。

## 当前能力

- 树状/辐射状 10 kV 馈线拓扑建模与合法性校验；
- 基于节点电压、支路零序电流、保护及开关动作进行故障区段评分；
- 输出候选故障支路、置信度、证据链与处置建议；
- 提供 JSON 示例、命令行入口、单元测试和 GitHub Actions；
- 为连云港暂态解析、公司 M4、河北中调课题三及专业软件适配预留边界。

## 目录

```text
src/grid_agent/
├── model.py       # 节点、支路、量测和案例模型
├── topology.py    # 树状馈线校验及上下游查询
├── diagnosis.py   # 可解释故障区段评分
├── demo.py        # 案例读取与结果渲染
└── cli.py         # 命令行入口
examples/
└── feeder_10kv.json
tests/
└── test_diagnosis.py
docs/
└── architecture.md
```

## 运行

要求 Python 3.11 及以上。

```bash
python -m pip install -e '.[dev]'
grid-agent diagnose examples/feeder_10kv.json
```

JSON 输出：

```bash
grid-agent diagnose examples/feeder_10kv.json --format json
```

当前示例会将 `B23` 判断为最可能故障区段，并逐项输出零序电流、电压跌落、拓扑边界反差和保护/开关动作的评分贡献。

## v0.1 方法

| 证据 | 默认权重 |
|---|---:|
| 支路零序电流 | 0.45 |
| 下游电压跌落 | 0.25 |
| 上下游拓扑边界反差 | 0.20 |
| 保护或开关动作 | 0.10 |

这些权重只是工程启动值。当前版本用于最小闭环验证，不把经验评分冒充为暂态解析解，也不能替代继电保护、调度规程和现场安全确认。

## 路线

1. **树状馈线 Demo**：拓扑、诊断、CLI、测试和 CI。
2. **连云港暂态解析**：故障源项、唯一路径传递函数、分支反射/透射、末端反射与衰减。
3. **M4 对接**：准静态状态估计残差、小电流接地选线、FA 隔离与供电恢复。
4. **河北中调对接**：运行风险识别、场景推演与调控建议。
5. **专业工具适配**：PSCAD、MATLAB、PSS®E、CDEGS、SCADA/录波数据与自动报告。

详细设计见 [`docs/architecture.md`](docs/architecture.md)。

## 状态

仓库处于工程验证初期。所有推导、评分、接口和示例均视为迭代过程，不应直接当作定稿或现场定值依据。
