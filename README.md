# DateVision 工业视觉检测平台

<div align="center">

**[English](#) | 简体中文**

**免费使用 · AGPL-3.0 · 流程图式视觉检测 · 插件扩展 · TCP通信**

---

### 开发者声明

| 项目 | 信息 |
|------|------|
| **开发者** | 杨佳祺 |
| **联系电话** | 15803820398 |
| **联系邮箱** | yangjiaqi@datekj.top |
| **版权所有** | 郑州德塔工业自动化 |

</div>

---

## 项目简介


2.

### 为什么选择 DateVision？

| 对比项 | DateVision | Halcon / VisionPro | VisionMaster |
|--------|-----------|-------------------|--------------|
| 费用 | **完全免费** | 数万元/年授权 | 需硬件绑定 |
| 开源 | **AGPL-3.0** | 闭源 | 闭源 |
| 插件扩展 | **Python脚本即插件** | 需要 SDK | 受限 |
| 通信 | **内置 TCP Socket** | 需额外开发 | 需额外开发 |
| 流程图 | **拖拽式** | 有 | 有 |
| 学习门槛 | **低 (Python)** | 高 (Halcon 语法) | 中 |

---

## 功能特性

### 核心功能
- **流程图编辑器** — 拖拽节点 + 连线，可视化构建检测流程
- **14 个内置工具** — 图像源、灰度化、阈值分割、边缘检测、形态学、滤波、斑点分析、模板匹配、测量、线查找、线间距 等
- **插件系统** — 在 `user_plugins/` 下新建 `.py` 文件即可自动加载，参考示例
- **图像预览** — 实时预览处理结果，支持缩放、自适应窗口
- **属性面板** — 选中节点直接修改参数，所见即所得
- **项目保存/加载** — `.ovp` 格式，JSON 可读，含流程图、参数、通信配置

### 线查找工具
- **自动学习** — 基于 ROI 中间基准线，自动学习两侧色差，无需手动调参
- **边缘极性** — 明到暗 / 暗到明 / 任意，适配不同场景
- **单线输出** — 只返回 ROI 中心最近的一条线，配合线间距工具使用

### 通信功能
- **TCP Socket 服务端** — 内置，配置端口即可启动
- **远程触发检测** — 客户端发送控制字自动执行流程图
- **自定义输出格式** — 支持 `{节点ID.端口名}` 引用 + 算术运算
- **响应格式** — `状态;用户定义输出`（如 `OK;OK;100.5;80.2`）

---

## 快速开始

### 环境要求
- Python 3.10+
- Windows 10/11

### 安装运行

```bash
# 1. 克隆或下载项目
cd OPENVISION

# 2. 双击运行（自动创建虚拟环境并安装依赖）
run.bat

# 或手动执行
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python main.py
```

### 依赖清单
```
PySide6 >= 6.5.0    # Qt GUI 框架 (LGPL)
opencv-python >= 4.8 # 计算机视觉库 (BSD)
numpy >= 1.24        # 数值计算 (BSD)
Pillow >= 10.0       # 图像处理 (HPND)
```

---

## 使用指南

### 基本流程
1. 从左侧**工具箱**拖拽工具到画布（或双击添加）
2. 连接节点端口（输出 → 输入）
3. 选中节点，在右侧**属性面板**调整参数
4. 按 **F5** 或点击工具栏运行按钮执行
5. 底部**图像预览**查看处理结果

### 线查找示例
1. 拖入 `图像源` → 选择图片
2. 拖入 `线查找` → 连接图像源输出
3. **双击**线查找节点 → 打开 ROI 编辑对话框
4. 在图像上**拖拽绘制 ROI 框**
5. 点击 **"学习"** 按钮自动分析色差
6. 点击 **"检测"** 查看结果，点击 **"确定"** 保存

### TCP 通信配置
1. 切换到右下角 **"通信"** 标签页
2. 设置端口号，点击 **"启动服务"**
3. 配置输出格式，例如：
   ```
   {abc123.horizontal_dist}
   {abc123.vertical_dist}
   ```
4. 外部客户端连接后发送控制字（默认 `TRIGGER`）触发检测
5. 返回格式：`OK;OK;OK;100.5;80.2`

---

## 自定义插件开发

在 `user_plugins/` 目录下创建 `.py` 文件，继承 `PluginBase`：

```python
from app.plugin_system.base import PluginBase, PortDef, PortType, ParamDef
import cv2

class MyPlugin(PluginBase):
    plugin_id = "my_filter"          # 唯一标识
    plugin_name = "我的滤镜"          # 显示名称
    plugin_category = "图像处理"      # 分类
    plugin_description = "自定义滤镜"

    @classmethod
    def input_ports(cls):
        return [PortDef("input", PortType.IMAGE, "输入图像")]

    @classmethod
    def output_ports(cls):
        return [PortDef("output", PortType.IMAGE, "输出图像")]

    @classmethod
    def input_params(cls):
        return [
            ParamDef("strength", "强度", "slider", 50, 0, 100, 1),
        ]

    def execute(self) -> bool:
        img = self._inputs.get("input")
        if img is None:
            return False
        strength = self.get_param("strength") / 100.0
        result = cv2.addWeighted(img, strength, img, 0, 0)
        self._outputs["output"] = result
        return True
```

重启应用即可在工具箱看到新插件。

---

## 项目结构

```
DATEVISION/
├── main.py                     # 入口文件
├── run.bat                     # 一键启动脚本
├── requirements.txt            # 依赖清单
├── app/
│   ├── main_window.py          # 主窗口
│   ├── flowchart/              # 流程图引擎
│   │   ├── canvas.py           # 画布（场景+视图）
│   │   ├── node.py             # 节点图形项
│   │   ├── port.py             # 端口图形项
│   │   ├── connection.py       # 贝塞尔连接线
│   │   └── engine.py           # 拓扑排序执行引擎
│   ├── panels/                 # 面板组件
│   │   ├── toolbox.py          # 工具箱（拖拽添加）
│   │   ├── properties.py       # 属性面板
│   │   ├── preview.py          # 图像预览
│   │   ├── output.py           # 输出日志
│   │   └── communication.py    # TCP 通信面板
│   ├── dialogs/                # 专用对话框
│   │   └── line_finder_dialog.py # 线查找 ROI 编辑器
│   └── plugin_system/          # 插件系统
│       ├── base.py             # 插件基类
│       ├── loader.py           # 动态加载器
│       └── manager.py          # 插件管理器
├── plugins/                    # 内置插件（14个）
│   ├── image_source.py         # 图像源
│   ├── image_output.py         # 图像输出
│   ├── grayscale.py            # 灰度化
│   ├── threshold.py            # 阈值分割（6种方法）
│   ├── edge_detection.py       # 边缘检测（Canny/Sobel/Laplacian）
│   ├── morphology.py           # 形态学处理（7种操作）
│   ├── image_filter.py         # 图像滤波（6种类型）
│   ├── blob_analysis.py        # 斑点分析
│   ├── pattern_match.py        # 模板匹配
│   ├── measure.py              # 测量工具
│   ├── line_finder.py          # 线查找（自动学习）
│   └── line_distance.py        # 线间距
└── user_plugins/               # 用户扩展插件
    └── example_plugins.py      # 示例插件
```

---

## 技术架构

```
┌─────────────────────────────────────────────────┐
│                   MainWindow                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Toolbox  │ │ Flowchart│ │   Properties     │ │
│  │ (左侧)   │ │ (中央)   │ │   (右侧)         │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
│  ┌──────────────────────────────────────────────┐│
│  │  Preview  │  Output / Communication        ││
│  │  (底部)   │  (底部标签页)                   ││
│  └──────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
          │                    │
          ▼                    ▼
   ┌──────────┐        ┌──────────────┐
   │ Plugin   │◄──────►│  Execution   │
   │ Manager  │        │  Engine      │
   └──────────┘        └──────────────┘
          │                    │
          ▼                    ▼
   ┌──────────┐        ┌──────────────┐
   │ Built-in │        │  Topological │
   │ Plugins  │        │  Sort + Run  │
   └──────────┘        └──────────────┘
```

---

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `F5` | 运行流程图 |
| `Shift+F5` | 停止运行 |
| `Delete` | 删除选中节点/连线 |
| `Ctrl+O` | 打开项目 |
| `Ctrl+S` | 保存项目 |
| `Ctrl+Shift+S` | 另存为 |
| `Ctrl+N` | 新建项目 |
| `Ctrl+滚轮` | 缩放画布 |
| `Ctrl+0` | 适应窗口 |

---

## 广告赞助

<div align="center">

### 开源不易，如果 DateVision 帮助到了你，欢迎支持！


---

### 商业合作

如需**定制开发**、**技术培训**、**产线集成**，请联系：

- **开发者**：杨佳祺
- **电话**：15803820398
- **邮箱**：yangjiaqi@datekj.top
- **公司**：郑州德塔工业自动化

---

### 推荐项目

| 项目 | 说明 |
|------|------|
| [OpenCV](https://opencv.org/) | 开源计算机视觉库 |
| [PySide6](https://wiki.qt.io/Qt_for_Python) | Qt for Python |
| [LabelImg](https://github.com/HumanSignal/labelImg) | 图像标注工具 |
| [OpenVision](https://github.com) | 本项目 - 工业视觉检测平台 |

---

### 开源协议

本项目基于 **GNU AGPL-3.0** 协议开源。简单来说：

- 你可以自由使用、修改、分发
- 但**修改后的代码也必须以 AGPL-3.0 开源**
- 通过网络提供服务也必须公开源码
- 这能有效阻止他人将你的代码闭源后商业售卖

详见 [LICENSE](LICENSE) 文件。

> 如需商业闭源授权或技术支持，请联系：杨佳祺 / 15803820398 / yangjiaqi@datekj.top

</div>

---

<div align="center">

**⭐ 如果觉得有用，请给个 Star！ ⭐**

Made with ❤️ by OpenVision Team

</div>