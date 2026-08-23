"""插件基类 - 所有视觉工具插件必须继承此类"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type
import numpy as np


class PortType(Enum):
    IMAGE = "image"
    REGION = "region"
    NUMBER = "number"
    STRING = "string"
    POINT = "point"
    MATRIX = "matrix"
    BOOL = "bool"
    ANY = "any"


@dataclass
class PortDef:
    """端口定义"""
    name: str
    port_type: PortType
    description: str = ""


@dataclass
class ParamDef:
    """参数定义"""
    name: str
    display_name: str
    param_type: str  # "int", "float", "str", "bool", "choice", "slider", "file"
    default: Any = None
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    step: Optional[float] = None
    choices: Optional[List[str]] = None
    description: str = ""


class PluginBase(ABC):
    """视觉工具插件基类"""

    plugin_id: str = ""
    plugin_name: str = "未命名工具"
    plugin_category: str = "通用"
    plugin_description: str = ""
    plugin_version: str = "1.0.0"
    plugin_icon: str = ""

    def __init__(self):
        self._params: Dict[str, Any] = {}
        self._inputs: Dict[str, Any] = {}
        self._outputs: Dict[str, Any] = {}
        self._init_params()

    def _init_params(self):
        """初始化默认参数"""
        for pdef in self.input_params():
            self._params[pdef.name] = pdef.default

    @classmethod
    def input_ports(cls) -> List[PortDef]:
        """定义输入端口"""
        return []

    @classmethod
    def output_ports(cls) -> List[PortDef]:
        """定义输出端口"""
        return []

    @classmethod
    def input_params(cls) -> List[ParamDef]:
        """定义可调参数"""
        return []

    def set_param(self, name: str, value: Any):
        """设置参数值"""
        self._params[name] = value

    def get_param(self, name: str) -> Any:
        """获取参数值"""
        return self._params.get(name)

    def get_params(self) -> Dict[str, Any]:
        """获取所有参数"""
        return dict(self._params)

    def set_input(self, port_name: str, value: Any):
        """设置输入端口数据"""
        self._inputs[port_name] = value

    def get_output(self, port_name: str) -> Any:
        """获取输出端口数据"""
        return self._outputs.get(port_name)

    def get_outputs(self) -> Dict[str, Any]:
        """获取所有输出"""
        return dict(self._outputs)

    @abstractmethod
    def execute(self) -> bool:
        """执行处理 - 返回是否成功"""
        ...

    def reset(self):
        """重置状态"""
        self._inputs.clear()
        self._outputs.clear()

    def get_extra_data(self) -> Dict[str, Any]:
        """获取插件特有数据（用于保存/加载）。子类重写以序列化自定义数据。"""
        return {}

    def set_extra_data(self, data: Dict[str, Any]):
        """恢复插件特有数据（用于保存/加载）。子类重写以反序列化自定义数据。"""
        pass

    def get_last_error(self) -> str:
        """返回最近一次执行失败的错误信息。子类可重写以提供更详细的错误。"""
        return getattr(self, '_last_error', '')

    def get_dialog_class(self):
        """返回插件专用对话框类（用于双击节点打开编辑界面）。
        返回 None 表示没有专用对话框。
        子类重写返回 QDialog 子类，构造函数签名为 (plugin, input_image, parent)。
        """
        return None