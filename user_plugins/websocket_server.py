"""WebSocket 服务器插件 - 将检测图片以 base64 发送到订阅客户端"""

import base64
import hashlib
import struct
import socket
import threading
import time
import traceback
from typing import Optional

import cv2
import numpy as np

from app.plugin_system.base import PluginBase, PortDef, PortType, ParamDef


class WebSocketServerPlugin(PluginBase):
    """WebSocket 服务器 - 接收图像，转为 base64 广播给所有订阅客户端"""

    plugin_id = "websocket_server"
    plugin_name = "图像流推送"
    plugin_category = "输入输出"
    plugin_description = "启动 WebSocket 服务器，将图像流以 base64 发送到所有订阅客户端"

    WS_MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self):
        super().__init__()
        self._server_thread: Optional[threading.Thread] = None
        self._broadcast_thread: Optional[threading.Thread] = None
        self._server_socket: Optional[socket.socket] = None
        self._clients: list[socket.socket] = []
        self._clients_lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._current_frame: Optional[np.ndarray] = None
        self._running = False
        self._last_error = ""

    @classmethod
    def input_ports(cls):
        return [PortDef("input", PortType.IMAGE, "输入图像")]

    @classmethod
    def output_ports(cls):
        return [
            PortDef("output", PortType.IMAGE, "原始图像(透传)"),
            PortDef("client_count", PortType.NUMBER, "当前客户端数"),
        ]

    @classmethod
    def input_params(cls):
        return [
            ParamDef("port", "监听端口", "int", 9000, 1024, 65535, 1, description="WebSocket 服务端口"),
            ParamDef("quality", "JPEG质量", "int", 80, 10, 100, 5, description="base64 编码图片的 JPEG 质量"),
            ParamDef("auto_start", "自动启动", "bool", True, description="加载项目时自动启动服务"),
            ParamDef("fps", "发送帧率", "int", 30, 1, 60, 1, description="每秒发送的图像帧数"),
        ]

    def execute(self) -> bool:
        """更新输入图像和客户端状态，实际的发送由后台线程持续进行"""
        img = self._inputs.get("input")
        
        # 更新当前图像（用于后台线程发送）
        with self._frame_lock:
            self._current_frame = img.copy() if img is not None else None
        
        # 更新客户端数量输出
        self._outputs["client_count"] = len(self._clients)
        
        # 透传图像
        self._outputs["output"] = img
        
        # 确保服务器已启动
        if not self._running and self.get_param("auto_start"):
            self._start_server()
        
        return True

    def _encode_image(self, img: np.ndarray, quality: int) -> str:
        """将图像编码为 base64 字符串"""
        if len(img.shape) == 2:
            encode_img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        else:
            encode_img = img
        _, buf = cv2.imencode(".jpg", encode_img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return base64.b64encode(buf).decode("ascii")

    def _broadcast(self, data: str):
        """向所有已连接的客户端广播数据"""
        with self._clients_lock:
            dead = []
            for client in self._clients:
                try:
                    self._send_frame(client, data)
                except Exception:
                    dead.append(client)
            for c in dead:
                self._clients.remove(c)
                try:
                    c.close()
                except Exception:
                    pass

    def _send_frame(self, sock: socket.socket, data: str):
        """发送 WebSocket 文本帧"""
        payload = data.encode("utf-8")
        frame = bytearray()
        frame.append(0x81)  # FIN + text opcode
        length = len(payload)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(struct.pack(">H", length))
        else:
            frame.append(127)
            frame.extend(struct.pack(">Q", length))
        frame.extend(payload)
        sock.sendall(bytes(frame))

    def _start_server(self):
        """启动 WebSocket 服务器线程"""
        if self._running:
            return
        self._running = True
        self._server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self._server_thread.start()
        self._broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._broadcast_thread.start()
        # 等待服务器实际绑定端口（最多等2秒）
        for _ in range(20):
            if self._server_socket is not None or not self._running:
                break
            time.sleep(0.1)
        if not self._running:
            # 启动失败
            self._running = False

    def _stop_server(self):
        """停止服务器"""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None
        with self._clients_lock:
            for c in self._clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()
        # 等待线程结束
        if self._broadcast_thread and self._broadcast_thread.is_alive():
            self._broadcast_thread.join(timeout=2.0)
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=2.0)

    def _server_loop(self):
        """服务器主循环"""
        port = self.get_param("port")
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.settimeout(1.0)
            self._server_socket.bind(("0.0.0.0", port))
            self._server_socket.listen(5)
        except Exception as e:
            self._last_error = f"WebSocket 启动失败: {e}"
            self._running = False
            return

        while self._running:
            try:
                client, addr = self._server_socket.accept()
                try:
                    self._handshake(client)
                    with self._clients_lock:
                        self._clients.append(client)
                except Exception:
                    try:
                        client.close()
                    except Exception:
                        pass
            except socket.timeout:
                continue
            except OSError:
                break

    def _broadcast_loop(self):
        """后台广播循环，持续向客户端发送图像"""
        while self._running:
            try:
                # 获取当前图像和参数
                with self._frame_lock:
                    img = self._current_frame
                
                quality = self.get_param("quality")
                fps = self.get_param("fps")
                
                if img is not None and len(self._clients) > 0:
                    # 编码并广播
                    b64 = self._encode_image(img, quality)
                    if b64:
                        self._broadcast(b64)
                
                # 控制帧率
                time.sleep(1.0 / fps)
                
            except Exception as e:
                self._last_error = f"广播循环错误: {e}"
                time.sleep(0.1)

    def _handshake(self, sock: socket.socket):
        """WebSocket 握手"""
        sock.settimeout(5.0)
        data = sock.recv(4096).decode("utf-8", errors="ignore")
        key = ""
        for line in data.split("\r\n"):
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip()
                break
        if not key:
            raise ValueError("No WebSocket key")

        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()

        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            "\r\n"
        )
        sock.sendall(response.encode())
        sock.settimeout(30.0)

    def get_last_error(self) -> str:
        return self._last_error

    # ---- 序列化 ----

    def get_extra_data(self) -> dict:
        return {"running": self._running}

    def set_extra_data(self, data: dict):
        if data.get("running") and self.get_param("auto_start"):
            self._start_server()