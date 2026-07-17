# GridSociety MVP：配电网故障处置的物理—认知多智能体闭环

## 1. 目标

GridSociety 不是让大语言模型生成电压、电流或故障波形，而是让认知智能体在受约束的物理环境中完成故障处置决策。

```text
馈线量测与拓扑
      │
      ▼
故障诊断 Agent ──► 可诊断性门控 ──► 调度决策策略
      │                                  │
      │                                  ├─ 高置信度：复核后隔离
      │                                  └─ 低置信度：现场核查 Top-K
      │                                             │
      └─────────────────────────────────────────────▼
                              物理环境执行与结果反馈
```

物理模型负责“系统怎么运行”，认知层负责“参与者如何理解、协同和行动”。任何 LLM 决策都必须经过确定性的安全动作门控。

## 2. MVP 角色

| 角色 | 当前实现 | 后续接口 |
|---|---|---|
| 故障诊断 Agent | 调用 `FaultDiagnoser`，输出 Top-K、置信度、证据链 | GridFaultSFM、M4、暂态模型 |
| 调度 Agent | `RuleBasedDispatcher` 可复现安全基线 | 云端 LLM、本地模型、调度规程 RAG |
| 现场运维 Agent | 对候选区段生成受控现场反馈 | 移动巡检、无人机、录波与人工回传 |
| 客服影响 Agent | 根据故障下游拓扑统计用户与关键节点 | 重要用户、投诉、保供优先级 |
| 物理环境 | 记录核查、开关操作、错误隔离与控制时间 | 潮流、联络转供、FA、自愈执行 |

## 3. 可诊断性门控

直接隔离同时要求：

```text
confidence >= minimum_direct_isolation_confidence
Top-1 score - Top-2 score >= minimum_top_margin
```

任一条件不满足，调度策略只能请求现场核查 Top-K，不能直接执行遥控。这个门控对应 GridFaultSFM 的 feasibility head，后续可替换为学习模型，但输出仍需进入同一安全约束层。

## 4. 输入格式

场景文件由馈线案例和事故参数组成。可直接内嵌 `feeder_case`，也可通过相对路径引用：

```json
{
  "name": "10kV馈线高阻接地故障处置闭环",
  "feeder_case_path": "feeder_10kv.json",
  "incident": {
    "ground_truth_fault_branch": "B23",
    "customers_by_node": {"N3": 120, "N4": 380},
    "critical_nodes": ["N4"],
    "minimum_direct_isolation_confidence": 0.72,
    "minimum_top_margin": 0.10,
    "max_field_candidates": 2
  }
}
```

`ground_truth_fault_branch` 只用于离线仿真评估，真实在线系统不能把它提供给诊断或调度 Agent。

## 5. 输出指标

MVP 已输出：

- Top-1 诊断是否正确；
- 场景是否可诊断；
- 是否直接隔离；
- 故障是否被控制；
- 影响用户数与关键节点数；
- 故障控制耗时；
- 用户停电分钟数（控制前）；
- 开关操作、现场核查和错误隔离次数；
- 是否升级人工复核；
- 全过程事件时间线。

## 6. 运行

```bash
python -m pip install -e '.[dev]'
grid-agent simulate examples/gridsociety_incident.json
grid-agent simulate examples/gridsociety_incident.json --format json
```

## 7. 下一阶段

1. 增加联络开关、备用电源和供电恢复搜索，区分“故障控制”与“恢复供电”。
2. 将 `DispatchPolicy` 接到 LLM，并使用结构化输出、动作白名单和规程校验。
3. 接入 GridFaultSFM 的馈线概率、区段概率、故障类型、故障电阻区间、feasibility、置信度和主动量测建议。
4. 批量生成不同拓扑、故障位置、故障电阻、噪声和信息延迟场景，形成仿真评测基准。
5. 分别对接连云港暂态解析、M4 闭环执行和河北中调高层运行推理。

## 8. 当前边界

当前版本只验证“诊断—判断—核查—隔离—反馈”的最小闭环，不模拟真实保护配合、联络转供、潮流越限、暂态波形和现场不确定性。所有结果均为研发过程产物，不应直接作为现场定值或调度指令。
