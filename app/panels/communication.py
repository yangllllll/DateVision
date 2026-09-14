"""通信面板 - TCP Socket 服务端，支持远程触发检测和结果输出"""

import re
import socket
import threading
import time
from typing import Optional, Callable

from PySide6.QtCore import Qt, QThread, Signal as QtSignal
from PySide6.QtGui import QFont, QColor, QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QLineEdit, QTextEdit,
    QGroupBox, QFormLayout, QComboBox, QCheckBox,
    QMessageBox, QScrollArea,
)


def get_local_ip() -> str:
    """获取本机局域网IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class TcpServerThread(QThread):
    """TCP 服务端线程"""

    log_msg = QtSignal(str, str)  # message, color
    client_connected = QtSignal(bool)
    trigger_received = QtSignal()  # 收到控制字，触发检测
    connection_count = QtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._port = 8080
        self._control_word = "TRIGGER"
        self._running = False
        self._server_socket: Optional[socket.socket] = None
        self._client_socket: Optional[socket.socket] = None
        self._response_data = ""
        self._response_lock = threading.Lock()
        self._response_ready = threading.Event()
        self._client_count = 0

    def configure(self, port: int, control_word: str):
        self._port = port
        self._control_word = control_word

    def set_response(self, data: str):
        with self._response_lock:
            self._response_data = data
        self._response_ready.set()

    def _get_response(self, timeout: float = 10.0) -> str:
        """等待响应数据，超时返回空字符串"""
        if self._response_ready.wait(timeout):
            with self._response_lock:
                resp = self._response_data
                self._response_data = ""
            self._response_ready.clear()
            return resp
        return ""

    def run(self):
        self._running = True
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.settimeout(1.0)
            self._server_socket.bind(("0.0.0.0", self._port))
            self._server_socket.listen(1)
            self.log_msg.emit(f"TCP服务已启动，监听端口 {self._port}", "#4caf50")

            while self._running:
                try:
                    client, addr = self._server_socket.accept()
                    self._client_socket = client
                    self._client_count += 1
                    self.connection_count.emit(self._client_count)
                    self.client_connected.emit(True)
                    self.log_msg.emit(f"客户端连接: {addr[0]}:{addr[1]}", "#2196f3")

                    # 处理客户端通信
                    self._handle_client(client)

                except socket.timeout:
                    continue
                except OSError:
                    if self._running:
                        self.log_msg.emit("TCP服务异常", "#f44336")
                    break
                finally:
                    if self._client_socket:
                        try:
                            self._client_socket.close()
                        except Exception:
                            pass
                        self._client_socket = None
                    self.client_connected.emit(False)

        except Exception as e:
            self.log_msg.emit(f"TCP服务启动失败: {e}", "#f44336")
        finally:
            if self._server_socket:
                try:
                    self._server_socket.close()
                except Exception:
                    pass
                self._server_socket = None
            self._running = False

    def _handle_client(self, client: socket.socket):
        """处理客户端请求"""
        client.settimeout(30.0)
        buffer = b""

        while self._running:
            try:
                data = client.recv(4096)
                if not data:
                    self.log_msg.emit("客户端断开连接", "#ff9800")
                    break

                buffer += data

                # 查找控制字
                cw_bytes = self._control_word.encode()
                if cw_bytes in buffer:
                    idx = buffer.find(cw_bytes)
                    buffer = buffer[idx + len(cw_bytes):]  # 移除控制字
                    self.log_msg.emit(f"收到控制字 '{self._control_word}'，触发检测", "#ce93d8")
                    # 清除可能残留的上一次响应，确保本次等待对应本次触发，避免时序错乱
                    with self._response_lock:
                        self._response_data = ""
                    self._response_ready.clear()
                    self.trigger_received.emit()

                    # 等待响应数据（最多等10秒）
                    resp = self._get_response(timeout=10.0)
                    if resp:
                        try:
                            client.sendall((resp + "\n").encode("utf-8"))
                            self.log_msg.emit(f"响应: {resp[:100]}{'...' if len(resp) > 100 else ''}", "#4caf50")
                        except Exception as e:
                            self.log_msg.emit(f"发送响应失败: {e}", "#f44336")
                            break
                    else:
                        try:
                            client.sendall(b"ERROR:TIMEOUT\n")
                        except Exception:
                            pass

            except socket.timeout:
                continue
            except Exception as e:
                self.log_msg.emit(f"通信异常: {e}", "#f44336")
                break

    def stop(self):
        self._running = False
        if self._client_socket:
            try:
                self._client_socket.close()
            except Exception:
                pass
            self._client_socket = None
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None
        self.wait(3000)


class CommunicationPanel(QWidget):
    """通信面板 - 输出栏的通信标签页"""

    # 信号：请求执行流程图
    execute_requested = QtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = TcpServerThread()
        self._server.log_msg.connect(self._log)
        self._server.client_connected.connect(self._on_client_changed)
        self._server.trigger_received.connect(self._on_trigger)
        self._server.connection_count.connect(self._on_count_changed)
        self._setup_ui()

    def _setup_ui(self):
        # 使用 QScrollArea 包裹内容，避免空间不足时被截断
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: #1e1e1e; border: none; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ---- 服务器配置 ----
        server_group = QGroupBox("TCP 服务端配置")
        server_group.setStyleSheet(_group_style())
        server_layout = QFormLayout(server_group)
        server_layout.setSpacing(6)

        ip_layout = QHBoxLayout()
        self._ip_label = QLabel(get_local_ip())
        self._ip_label.setStyleSheet("color: #4fc3f7; font-weight: bold; font-size: 13px; font-family: Consolas;")
        self._ip_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        ip_layout.addWidget(QLabel("本机IP:"))
        ip_layout.addWidget(self._ip_label)
        ip_layout.addStretch()

        port_layout = QHBoxLayout()
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(8080)
        self._port_spin.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555;")
        port_layout.addWidget(QLabel("端口:"))
        port_layout.addWidget(self._port_spin)
        port_layout.addStretch()

        server_layout.addRow("", ip_layout)
        server_layout.addRow("", port_layout)

        # 启动/停止按钮
        btn_layout = QHBoxLayout()
        self._btn_start = QPushButton("启动服务")
        self._btn_start.setStyleSheet(_btn_style("#2e7d32", "#1b5e20"))
        self._btn_start.clicked.connect(self._on_start)

        self._btn_stop = QPushButton("停止服务")
        self._btn_stop.setStyleSheet(_btn_style("#c62828", "#8e0000"))
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.setEnabled(False)

        self._status_label = QLabel("● 已停止")
        self._status_label.setStyleSheet("color: #888; font-size: 12px;")

        self._conn_label = QLabel("连接: 0")
        self._conn_label.setStyleSheet("color: #888; font-size: 12px;")

        btn_layout.addWidget(self._btn_start)
        btn_layout.addWidget(self._btn_stop)
        btn_layout.addWidget(self._status_label)
        btn_layout.addStretch()
        btn_layout.addWidget(self._conn_label)
        server_layout.addRow("", btn_layout)

        layout.addWidget(server_group)

        # ---- 控制字 ----
        ctrl_group = QGroupBox("检测控制字")
        ctrl_group.setStyleSheet(_group_style())
        ctrl_layout = QHBoxLayout(ctrl_group)
        self._control_word = QLineEdit("TRIGGER")
        self._control_word.setStyleSheet("background: #333; color: #4fc3f7; border: 1px solid #555; font-family: Consolas; font-size: 12px;")
        self._control_word.setToolTip("客户端发送此字符串触发检测流程")
        ctrl_layout.addWidget(QLabel("控制字:"))
        ctrl_layout.addWidget(self._control_word)
        layout.addWidget(ctrl_group)

        # ---- 输出格式 ----
        output_group = QGroupBox("输出格式 (支持表达式)")
        output_group.setStyleSheet(_group_style())
        output_layout = QVBoxLayout(output_group)

        # 格式说明
        hint = QLabel("格式: {节点ID.端口名} 引用输出值。支持 + - * / 运算。每行一个输出项。")
        hint.setStyleSheet("color: #888; font-size: 10px;")
        hint.setWordWrap(True)
        output_layout.addWidget(hint)

        self._output_format = QTextEdit()
        self._output_format.setMaximumHeight(100)
        self._output_format.setPlaceholderText(
            "示例:\n"
            "{abc123.horizontal_dist}\n"
            "{abc123.vertical_dist}\n"
            "{def456.line_count}"
        )
        self._output_format.setStyleSheet(
            "background: #1e1e1e; color: #ccc; border: 1px solid #333; font-family: Consolas; font-size: 11px;"
        )
        output_layout.addWidget(self._output_format)

        # 分隔符
        delim_layout = QHBoxLayout()
        delim_layout.addWidget(QLabel("分隔符:"))
        self._delimiter = QComboBox()
        self._delimiter.addItems([";", ",", ".", "/", "|", "\\t", "\\n", "自定义"])
        self._delimiter.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555;")
        self._delimiter.currentTextChanged.connect(self._on_delimiter_changed)
        self._custom_delim = QLineEdit(";")
        self._custom_delim.setMaximumWidth(60)
        self._custom_delim.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555;")
        self._custom_delim.setVisible(False)
        delim_layout.addWidget(self._delimiter)
        delim_layout.addWidget(self._custom_delim)
        delim_layout.addStretch()
        output_layout.addLayout(delim_layout)

        layout.addWidget(output_group)

        # ---- 通信日志 ----
        log_group = QGroupBox("通信日志")
        log_group.setStyleSheet(_group_style())
        log_layout = QVBoxLayout(log_group)
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setStyleSheet(
            "background: #1e1e1e; color: #ccc; border: 1px solid #333; font-family: Consolas; font-size: 11px;"
        )
        log_layout.addWidget(self._log_text)
        layout.addWidget(log_group)

        layout.addStretch()

        scroll.setWidget(content)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _on_delimiter_changed(self, text: str):
        self._custom_delim.setVisible(text == "自定义")

    def _get_delimiter(self) -> str:
        d = self._delimiter.currentText()
        if d == "自定义":
            return self._custom_delim.text()
        elif d == "\\t":
            return "\t"
        elif d == "\\n":
            return "\n"
        return d

    def _on_start(self):
        port = self._port_spin.value()
        cw = self._control_word.text().strip()
        if not cw:
            QMessageBox.warning(self, "配置错误", "请输入检测控制字")
            return

        self._server.configure(port, cw)
        self._server.start()

        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._port_spin.setEnabled(False)
        self._status_label.setText("● 运行中")
        self._status_label.setStyleSheet("color: #4caf50; font-size: 12px;")

    def _on_stop(self):
        self._server.stop()
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._port_spin.setEnabled(True)
        self._status_label.setText("● 已停止")
        self._status_label.setStyleSheet("color: #888; font-size: 12px;")

    def _on_client_changed(self, connected: bool):
        pass

    def _on_count_changed(self, count: int):
        self._conn_label.setText(f"连接: {count}")

    def _on_trigger(self):
        """收到控制字，触发执行"""
        self._log("收到控制字，请求执行流程图...", "#ce93d8")
        self.execute_requested.emit()

    def _log(self, msg: str, color: str = "#cccccc"):
        timestamp = time.strftime("%H:%M:%S")
        self._log_text.moveCursor(QTextCursor.MoveOperation.End)
        self._log_text.setTextColor(QColor(color))
        self._log_text.insertPlainText(f"[{timestamp}] {msg}\n")
        self._log_text.moveCursor(QTextCursor.MoveOperation.End)

    def set_response_data(self, data: str):
        """设置响应数据（供主窗口调用）"""
        self._server.set_response(data)

    def get_output_format(self) -> str:
        return self._output_format.toPlainText()

    def get_delimiter(self) -> str:
        return self._get_delimiter()

    def get_config(self) -> dict:
        """获取通信配置（用于保存项目）"""
        return {
            "port": self._port_spin.value(),
            "control_word": self._control_word.text(),
            "output_format": self._output_format.toPlainText(),
            "delimiter": self._delimiter.currentText(),
            "custom_delimiter": self._custom_delim.text(),
        }

    def set_config(self, config: dict):
        """恢复通信配置（用于加载项目）"""
        if "port" in config:
            self._port_spin.setValue(config["port"])
        if "control_word" in config:
            self._control_word.setText(config["control_word"])
        if "output_format" in config:
            self._output_format.setPlainText(config["output_format"])
        if "delimiter" in config:
            idx = self._delimiter.findText(config["delimiter"])
            if idx >= 0:
                self._delimiter.setCurrentIndex(idx)
        if "custom_delimiter" in config:
            self._custom_delim.setText(config["custom_delimiter"])


def _group_style() -> str:
    return """
        QGroupBox { color: #e0e0e0; border: 1px solid #3e3e42; border-radius: 4px;
            margin-top: 10px; padding-top: 16px; font-size: 12px; font-weight: bold; font-family: "Microsoft YaHei"; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        QLabel { color: #aaa; font-size: 11px; font-family: "Microsoft YaHei"; }
    """


def _btn_style(bg: str, hover: str) -> str:
    return f"""
        QPushButton {{ background: {bg}; color: #fff; border: 1px solid #555;
            padding: 5px 14px; font-size: 12px; font-family: "Microsoft YaHei"; border-radius: 3px; }}
        QPushButton:hover {{ background: {hover}; }}
        QPushButton:disabled {{ background: #333; color: #666; }}
    """