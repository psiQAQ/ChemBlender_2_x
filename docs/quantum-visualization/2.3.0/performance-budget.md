# 2.3.0 性能与规模预算

## 数据层级

| 层级 | 结构 | 轨迹 | Grid3D | SDF |
| --- | ---: | ---: | ---: | ---: |
| 即时交互 | 50,000 atoms | 1,000 frames | 128³ | 10,000 records |
| 延迟加载 | 250,000 atoms | 100,000 frames | 256³ | 100,000 records |
| 超大数据 | 元数据和抽样 | 索引/窗口 | LOD/worker | 索引/过滤 |

## 用户时延目标

| 操作 | 目标 |
| --- | ---: |
| Extension enable | ≤ 2 s |
| Quick Import 首次反馈 | ≤ 0.5 s |
| 普通 XYZ/MOL/CIF 创建默认视图 | ≤ 3 s |
| 128³ Cube 创建缓存视图 | ≤ 10 s |
| 已缓存轨迹帧切换 | ≤ 100 ms |
| Project Browser 搜索/过滤 | ≤ 200 ms |
| 预计超过 1 s 的操作 | 进度、取消、UI不长期阻塞 |

## 测量规则

1. 同一硬件 baseline 和 Blender 版本记录冷启动与热缓存。
2. 不用单次最快值；报告 median、p95、样本数和缓存状态。
3. reader parse、sidecar write、view creation 分别计时。
4. 大数据测试不得把全部记录创建为 Blender object。
5. 失败或取消后检查临时文件、handler、object 和项目 dirty state。
6. CI 使用趋势门禁而不是把云 runner绝对时延当作桌面 SLA；本地 reference benchmark负责绝对指标。

## 算法约束

- 缺拓扑结构的键推断不能使用全局 O(N²)。
- SDF 批量预览只解析必要头部和索引，record实体按页或确认范围物化。
- extXYZ 多帧属性进入 lazy sidecar，不复制到每个 Blender object。
- Cube 在大于阈值时流式解析到暂存 NPY，不建立 Python float tuple。
- Project Browser 使用预计算 flat rows 和增量过滤，不在每次 draw 中遍历所有数组。
