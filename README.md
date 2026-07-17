# grid-agent / GridSociety

面向配电网故障诊断与物理—认知多智能体联合仿真的可扩展工程仓库。

当前 v0.2 在原有树状 10 kV 馈线故障诊断 Demo 上，增加了 **GridSociety MVP**：把诊断 Agent、调度 Agent、现场运维 Agent、客服影响 Agent 和受约束物理环境串成一个可运行的故障处置闭环。

## 核心原则

```text
物理模型负责“电网怎么运行”
认知智能体负责“参与者如何理解、协同和行动”
```

LLM 不直接生成电压、电流、潮流或故障波形。任何模型给出的操作建议都必须经过确定性的可诊断性门控、动作白名单和人工/规程约束。

## 当前能力

### 故障诊断 v0.1

- 树状/辐射状 10 kV 馈线拓扑建模与合法性校验；
- 基于节点电压、支路零序电流、保护及开关动作进行故障区段评分；
- 输出候选故障支路、置信度、证据链与处置建议；
- 为连云港暂态解析、公司 M4、河北中调课题三及专业软件适配预留边界。

### GridSociety v0.2 MVP

- `DiagnosticAgent`：调用现有诊断器并生成可诊断性判断；
- `RuleBasedDispatcher`：提供可复现、安全优先的调度策略基线；
- `FieldCrewAgent`：模拟 Top-K 现场核查反馈；
- `CustomerServiceAgent`：统计受影响用户和关键节点；
- `PhysicalEnvironment`：执行核查、隔离、错误操作回退和人工复核；
- 输出故障控制耗时、用户停电分钟数、开关操作、现场核查、错误隔离和事件时间线；
- 通过 `DispatchPolicy` 接口为后续 LLM、规程 RAG 和本地模型留出统一接入点。

## 目录

```text
src/grid_agent/
├── model.py       # 节点、支路、量测和案例模型
├── topology.py    # 树状馈线校验及上下游查询
├── diagnosis.py   # 可解释故障区段评分
├── society.py     # GridSociety 多智能体仿真闭环
├── demo.py        # 诊断案例读取与结果渲染
└── cli.py         # 命令行入口
examples/
├── feeder_10kv.json
└── gridsociety_incident.json
tests/
├── test_diagnosis.py
└── test_society.py
docs/
├── architecture.md
└── gridsociety_mvp.md
```

## 安装

要求 Python 3.11 及以上。

```bash
python -m pip install -e '.[dev]'
```

## 运行故障诊断

```bash
grid-agent diagnose examples/feeder_10kv.json
grid-agent diagnose examples/feeder_10kv.json --format json
```

当前示例会将 `B23` 判断为最可能故障区段，并逐项输出零序电流、电压跌落、拓扑边界反差和保护/开关动作的评分贡献。

## 运行 GridSociety 仿真

```bash
grid-agent simulate examples/gridsociety_incident.json
grid-agent simulate examples/gridsociety_incident.json --format json
```

默认示例验证：

1. 诊断 Agent 输出 Top-1、置信度和候选间隔；
2. 可诊断性门控判断能否直接隔离；
3. 调度策略选择直接隔离或现场核查 Top-K；
4. 物理环境执行动作并反馈结果；
5. 系统统计用户影响、控制时间和操作风险。

详细设计见 [`docs/gridsociety_mvp.md`](docs/gridsociety_mvp.md)。

## v0.1 诊断权重

| 证据 | 默认权重 |
|---|---:|
| 支路零序电流 | 0.45 |
| 下游电压跌落 | 0.25 |
| 上下游拓扑边界反差 | 0.20 |
| 保护或开关动作 | 0.10 |

这些权重只是工程启动值。当前版本用于最小闭环验证，不把经验评分冒充为暂态解析解，也不能替代继电保护、调度规程和现场安全确认。

## 路线

1. **树状馈线诊断 Demo**：拓扑、诊断、CLI、测试和 CI。
2. **GridSociety MVP**：诊断—判断—核查—隔离—反馈的物理—认知闭环。
3. **GridFaultSFM 接入**：馈线概率、区段概率、故障类型、故障电阻、feasibility、置信度和主动量测建议。
4. **连云港暂态解析**：故障源项、唯一路径传递函数、分支反射/透射、末端反射与衰减。
5. **M4 对接**：准静态状态估计残差、小电流接地选线、FA 隔离与供电恢复。
6. **河北中调对接**：运行风险识别、场景推演、人机协同与调控建议。
7. **专业工具适配**：PSCAD、MATLAB、PSS®E、CDEGS、SCADA/录波数据与自动报告。

## 状态与边界

仓库仍处于工程验证阶段。当前仿真只计算“故障控制前”的影响，不模拟真实保护配合、联络转供、潮流越限、暂态波形和完整恢复过程。所有推导、评分、接口和示例均视为迭代过程，不应直接当作定稿、现场定值或调度指令。
