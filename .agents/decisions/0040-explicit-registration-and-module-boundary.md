# 0040：Blender 注册显式化，纯核心不参与 auto-load 扫描

## Status

Proposed for Wave 0; user direction approved.

## Context

当前auto_load递归导入扩展下大部分模块并扫描class。随着core、UI和插件增长，会增加启用耗时、顶层副作用和错误耦合。

## Decision

建立显式注册模块清单或package聚合入口。只有UI、operators、handlers和menus参与注册；core、reader_api、pure readers/exporters和legacy纯函数不扫描。第三方Reader Plugin独立发现和隔离加载。

## Consequences

- 启用时间更可控。
- optional依赖不会因注册被加载。
- 新Blender模块必须显式加入注册清单和生命周期测试。

## Rejected Alternatives

- 继续扩大EXCLUDED_SUBMODULE_DIRS名单。
- 让每个core文件自行定义空register。

## Verification Contract

enable前后模块集合、注册class、handler数量和optional imports由Blender smoke验证；两次disable/enable无重复或残留。
