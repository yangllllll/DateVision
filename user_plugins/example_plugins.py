"""
示例用户插件 - 图像翻转
将此文件放在 user_plugins 目录下，重启应用即可在工具箱中看到此工具。

自定义插件开发指南：
1. 继承 PluginBase
2. 设置 plugin_id（唯一标识）、plugin_name、plugin_category、plugin_description
3. 定义 input_ports()、output_ports()、input_params()
4. 实现 execute() 方法
5. (可选) 重写 get_dialog_class() 返回专用对话框类，双击节点即可打开
"""

import cv2
import numpy as np
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QSlider
from PySide6.QtCore import Qt
from app.plugin_system.base import PluginBase, PortDef, PortType, ParamDef


# ============================================================
# 示例：带对话框的插件
# 重写 get_dialog_class() 返回对话框类，
# 对话框构造函数签名为 (plugin, input_image, parent)
# ============================================================

class FlipDialog(QDialog):
    """翻转插件的对话框示例"""

    def __init__(self, plugin, input_image, parent=None):
        super().__init__(parent)
        self._plugin = plugin
        self._flip_mode = self._plugin.get_param("flip_mode")
        self.setWindowTitle("图像翻转 - 设置")
        self.resize(300, 150)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("翻转模式:"))
        modes = ["水平翻转", "垂直翻转", "水平+垂直翻转"]
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 2)
        self._slider.setValue(modes.index(self._flip_mode))
        layout.addWidget(self._slider)

        
        self._label = QLabel(modes[0])
        self._slider.valueChanged.connect(lambda v: self._label.setText(modes[v]))
        layout.addWidget(self._label)

        btn = QPushButton("确定")
        btn.clicked.connect(self._on_ok)
        layout.addWidget(btn)

    def _on_ok(self):
        modes = ["水平翻转", "垂直翻转", "水平+垂直翻转"]
        self._plugin.set_param("flip_mode", modes[self._slider.value()])
        self.accept()


class FlipPlugin(PluginBase):
    """图像翻转插件（带对话框示例）"""

    plugin_id = "user_flip"
    plugin_name = "图像翻转"
    plugin_category = "用户插件"
    plugin_description = "对图像进行水平/垂直翻转（双击节点打开对话框）"

    @classmethod
    def input_ports(cls):
        return [PortDef("input", PortType.IMAGE, "输入图像")]

    @classmethod
    def output_ports(cls):
        return [PortDef("output", PortType.IMAGE, "翻转结果")]

    @classmethod
    def input_params(cls):
        return [
            ParamDef("flip_mode", "翻转模式", "choice", "水平翻转",
                     choices=["水平翻转", "垂直翻转", "水平+垂直翻转"],
                     description="选择翻转方向"),
        ]

    def execute(self) -> bool:
        img = self._inputs.get("input")
        if img is None:
            return False
        mode = self.get_param("flip_mode")
        flip_map = {"水平翻转": 1, "垂直翻转": 0, "水平+垂直翻转": -1}
        try:
            result = cv2.flip(img, flip_map.get(mode, 1))
            self._outputs["output"] = result
            return True
        except Exception:
            return False

    def get_dialog_class(self):
        """声明专用对话框：双击节点打开 FlipDialog"""
        return FlipDialog


# ============================================================
# 普通插件（无对话框）
# ============================================================

class InvertPlugin(PluginBase):
    """图像反色插件"""

    plugin_id = "user_invert"
    plugin_name = "图像反色"
    plugin_category = "用户插件"
    plugin_description = "对图像进行反色处理"

    @classmethod
    def input_ports(cls):
        return [PortDef("input", PortType.IMAGE, "输入图像")]

    @classmethod
    def output_ports(cls):
        return [PortDef("output", PortType.IMAGE, "反色结果")]

    def execute(self) -> bool:
        img = self._inputs.get("input")
        if img is None:
            return False
        try:
            result = cv2.bitwise_not(img)
            self._outputs["output"] = result
            return True
        except Exception:
            return False


class NumberPlugin(PluginBase):
    """数学比较插件"""

    plugin_id = "user_number"
    plugin_name = "比较"
    plugin_category = "数学运算"
    plugin_description = "对数字进行比较"

    @classmethod
    def input_ports(cls):
        return [PortDef("input", PortType.NUMBER, "输入数字")]

    @classmethod
    def output_ports(cls):
        return [PortDef("output", PortType.BOOL, "比较结果")]

    @classmethod
    def input_params(cls):
        return [
            ParamDef("compare_mode", "比较模式", "choice", "大于",
                     choices=["大于", "小于", "等于"],
                     description="选择比较模式"),
            ParamDef("NUM", "数字", "float", 0, description="输入数字"),
        ]

    def execute(self) -> bool:
        num1 = self._inputs.get("input")
        if num1 is None:
            return False
        mode = self.get_param("compare_mode")
        compare_map = {
            "大于": lambda x, y: x > y,
            "小于": lambda x, y: x < y,
            "等于": lambda x, y: x == y,
        }
        num2 = self.get_param("NUM")
        try:
            result = compare_map.get(mode, lambda x, y: False)(num1, num2)
            self._outputs["output"] = result
            return True
        except Exception:
            return False

class AndPlugin(PluginBase):
    """逻辑与插件"""
    plugin_id = "user_and"
    plugin_name = "逻辑与"
    plugin_category = "数学运算"
    plugin_description = "对两个布尔值进行逻辑与操作"

    @classmethod
    def input_ports(cls):
        return [
            PortDef("input1", PortType.BOOL, "输入布尔值1"),
            PortDef("input2", PortType.BOOL, "输入布尔值2"),
        ]

    @classmethod
    def output_ports(cls):
        return [PortDef("output", PortType.BOOL, "逻辑与结果")]

    def execute(self) -> bool:
        input1 = self._inputs.get("input1")
        input2 = self._inputs.get("input2")
        if input1 is None or input2 is None:
            return False
        try:
            result = input1 and input2
            self._outputs["output"] = result
            return True
        except Exception:
            return False