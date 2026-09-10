from typing import Type

import pyorbbecsdk
import cv2
import numpy as np

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QMessageBox, QGroupBox,
)

from app.plugin_system.base import PluginBase, PortDef, PortType, ParamDef

class OrbbecPlugin(PluginBase):
    plugin_id = "orbbec"
    plugin_name = "奥比相机对象"
    plugin_category = "奥比相机"
    plugin_description = "初始化一个奥比相机对象"
    def __init__(self):
        super().__init__()
        self.device = None
        self.pipeline: pyorbbecsdk.Pipeline | None = None
        self.context = pyorbbecsdk.Context()
        self.config  = pyorbbecsdk.Config()
        self._last_error = ""
    @classmethod
    def input_ports(cls):
        return []
    @classmethod
    def output_ports(cls):
        return [PortDef("camera", PortType.ANY,"camera object")]
    @classmethod
    def input_params(cls):
        return [ParamDef("serial_number", "相机序列号", "str", None)]

    def init_orbbec_config(self,pipeline: pyorbbecsdk.Pipeline,config: pyorbbecsdk.Config) -> pyorbbecsdk.Config:
        """初始化相机配置"""
        color_profiles = pipeline.get_stream_profile_list(pyorbbecsdk.OBSensorType.COLOR_SENSOR)
        if color_profiles is not None:
            color_profile = color_profiles.get_video_stream_profile(1280, 720, pyorbbecsdk.OBFormat.RGB, 30)
            if color_profile is not None:
                config.enable_stream(color_profile)
        depth_profiles = pipeline.get_stream_profile_list(pyorbbecsdk.OBSensorType.DEPTH_SENSOR)
        if depth_profiles is not None:
            depth_profile = depth_profiles.get_default_video_stream_profile()
            if depth_profile is not None:
                config.enable_stream(depth_profile)
        else:
            self._last_error = "没有找到相机配置"
        return config
    def get_dialog_class(self):
        return OrbbecPluginDialog
    def is_connected(self) -> bool:
        """检查相机是否已连接"""
        if self.pipeline is not None:
            return True
        return False
    
    def connect_camera(self,serial_number: str | None = None):
        """连接相机"""
        if self.pipeline is not None:
            self.pipeline.stop()
            self.pipeline = None
        device_list = self.context.query_devices()
        if len(device_list) == 0:
            self._last_error = "没有找到相机"
            return False
        if serial_number is None:
            self.device = device_list.get_device_by_serial_number(self.get_param("serial_number"))
        else:
            self.device = device_list.get_device_by_serial_number(serial_number)
            self.set_param("serial_number",serial_number)
        if self.device is None:
            self._last_error = "相机连接错误"
            return False
        self.pipeline = pyorbbecsdk.Pipeline(self.device)
        config = self.init_orbbec_config(self.pipeline,self.config)
        try:
            self.pipeline.start(config)

        except Exception as e:
            self._last_error = str(e)
            return False
        self._last_error = ""
        return True
    def disconnect_camera(self):
        """断开相机"""
        if self.pipeline is None:
            return True
        self.pipeline.stop()
        self.pipeline = None
        return True
    def get_rgb_frame(self) -> np.ndarray | None:
        """获取RGB帧"""
        if self.pipeline is None:
            return None
        frames = self.pipeline.wait_for_frames(1000)
        if frames is None:
            return None
        frame = frames.get_color_frame()
        if frame is None:
            return None
        image = np.frombuffer(frame.get_data(), dtype=np.uint8)
        image = image.reshape(frame.get_height(), frame.get_width(), 3)
        return image

    def execute(self) -> bool:
        if self.pipeline is not None:
            frames = self.pipeline.wait_for_frames(1000)
            if frames is None:
                self._last_error = "获取图像失败"
                self.disconnect_camera()
                return False
            self._outputs["camera"] = frames
            self._last_error = ""
            return True
        else:
            self.connect_camera()
            if self.pipeline is not None:
                frames = self.pipeline.wait_for_frames(1000).get_frame_by_index(0)
                if frames is None:
                    self._last_error = "获取图像失败"
                    self.disconnect_camera()
                    return False
                self._outputs["camera"] = frames
                self._last_error = ""
                return True
            else:
                self._outputs["camera"] = None
                self._last_error = "相机连接失败"
            return False

            
    def get_last_error(self) -> str:
        return self._last_error
class OrbbecPluginDialog(QDialog):
    """奥比相机设置对话框 - 预览 + 参数设置"""

    def __init__(self, plugin: "OrbbecPlugin", input_image, parent=None):
        super().__init__(parent)
        self._plugin = plugin
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_preview)
        self.setWindowTitle("奥比相机 - 预览与设置")
        self.resize(800, 600)
        self.setMinimumSize(640, 480)

        self._setup_ui()
        self._load_params()



    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        # ---- 相机选择 ----
        cam_group = QGroupBox("相机选择")
        cam_layout = QHBoxLayout(cam_group)
        self._cam_combo = QComboBox()
        self._cam_combo.setMinimumWidth(300)
        cam_layout.addWidget(QLabel("可用相机:"))
        cam_layout.addWidget(self._cam_combo, 1)

        self._btn_refresh = QPushButton("刷新列表")
        self._btn_refresh.clicked.connect(self._refresh_camera_list)
        cam_layout.addWidget(self._btn_refresh)

        self._btn_connect = QPushButton("测试连接")
        self._btn_connect.setStyleSheet(
            "background: #c62828; color: #fff;"
        )
        self._btn_connect.clicked.connect(self._toggle_connection)
        cam_layout.addWidget(self._btn_connect)
        main_layout.addWidget(cam_group)

        # ---- 图像预览 ----
        preview_group = QGroupBox("实时预览")
        preview_layout = QVBoxLayout(preview_group)
        self._preview_label = QLabel("未连接相机")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet(
            "background: #1e1e1e; border: 1px solid #3e3e42; color: #666; font-size: 14px;"
        )
        self._preview_label.setMinimumSize(640, 360)
        preview_layout.addWidget(self._preview_label)

        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        preview_layout.addWidget(self._status_label)
        main_layout.addWidget(preview_group, 1)

        # ---- 底部按钮 ----
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._btn_ok = QPushButton("确定")
        self._btn_ok.clicked.connect(self._on_accept)
        self._btn_cancel = QPushButton("取消")
        self._btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_ok)
        btn_layout.addWidget(self._btn_cancel)
        main_layout.addLayout(btn_layout)

    def _load_params(self):
        saved_serial = self._plugin.get_param("serial_number")
        self._refresh_camera_list()
        if saved_serial:
            self._cam_combo.setCurrentIndex(saved_serial)

    def _refresh_camera_list(self):
        """枚举 奥比 相机列表"""
        self._cam_combo.clear()
        try:
            devices = self._plugin.context.query_devices()
            if devices.get_count() > 0:
                for device in devices:
                    self._cam_combo.addItem(f"{device.get_device_info().get_name()} - {device.get_device_info().get_serial_number()}", device.get_device_info().get_serial_number())
                self._status_label.setText(f"发现 {self._cam_combo.count()} 台相机")
            else:
                self._status_label.setText("未发现相机")
        except Exception as e:
            self._status_label.setText(f"错误: {e}")

    def _toggle_connection(self):
        serial_number = self._cam_combo.currentData()
        if serial_number is None:
            QMessageBox.warning(self, "提示", "请先选择一台相机")
            return
        self._plugin.connect_camera(serial_number)
        self._update_preview()
        self._plugin.disconnect_camera()
        

    def _update_preview(self):
        if not self._plugin.is_connected():
            return
        try:
            
            frame = self._plugin.get_rgb_frame()
            if frame is None:
                return
            self._plugin.disconnect_camera()
            h, w, _ = frame.shape
            bytes_per_line = 3 * w
            qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            scaled = pixmap.scaled(
                self._preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._preview_label.setPixmap(scaled)
        except Exception as e:
            self._status_label.setText(f"取帧失败，连接已断开: {e}")
            self._plugin.disconnect_camera()
            return


    def _on_accept(self):
        if self._cam_combo.currentData() is not None:
            self._plugin.set_param("serial_number", self._cam_combo.currentData())
        self.accept()

    def reject(self):
        super().reject()
    def closeEvent(self, event):
        super().closeEvent(event)

class OrbbecRGBPlugin(OrbbecPlugin):
    plugin_id = "orbbec_rgb"
    plugin_name = "获取RGB图像"
    plugin_category = "奥比相机"
    plugin_description = "从奥比相机获取RGB图像"
    def __init__(self):
        super().__init__()
        self._last_error = ""
    @classmethod
    def input_ports(cls):
       return [PortDef("camera", PortType.ANY,"camera object")]
    @classmethod
    def output_ports(cls):
       return [PortDef("output", PortType.IMAGE,"rgb image")]
    
    @classmethod
    def input_params(cls):
        return [
        ]
    def get_last_error(self):
        return self._last_error
    def execute(self) -> bool:
        camera = self._inputs.get("camera")
        if camera is None:
            self._last_error = "未连接相机"
            return False
        frame = camera.get_color_frame()
        if frame is None:
            self._last_error = "获取图像失败"
            return False
        image = np.frombuffer(frame.get_data(), dtype=np.uint8)
        image = image.reshape(frame.get_height(), frame.get_width(), 3)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        self._outputs["output"] = image
        return True