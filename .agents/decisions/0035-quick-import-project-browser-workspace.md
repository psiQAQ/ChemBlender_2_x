# 0035：Quick Import 与双视图 Project Browser 共用同一项目路径

## Status

Proposed for Wave 0; user direction approved.

## Context

简单用户需要一键导入，复杂项目需要来源、数据和诊断浏览。只用N面板过于拥挤，只用项目浏览器又使简单流程过重。

## Decision

提供N面板Quick Import和独立ChemBlender Workspace。Quick Import内部仍提交QCProject并自动选择默认View。Project Browser可切换By Source/By Data，共享active entity。支持单文件、多文件和拖放，不自动扫描目录。

## Consequences

- Workspace布局损坏时N面板仍可完成核心操作。
- 未创建Blender View的数据仍在Project Browser可见。
- 复杂冲突在Import Preview汇总处理。

## Rejected Alternatives

- 两套长期独立导入路径。
- 全部功能塞入N面板。
- 以Blender Outliner/Object作为项目权威模型。

## Verification Contract

同一文件从按钮和拖放产生相同parse identity与项目实体；By Source/By Data选择同步；Workspace缺失不影响Quick Import。
