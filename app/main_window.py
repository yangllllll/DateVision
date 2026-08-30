

import json
import os
import re
import numpy as np

from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QAction, QKeySequence, QFont
from PySide6.QtWidgets import (
    QMainWindow, QToolBar, QStatusBar,
    QDockWidget, QWidget, QVBoxLayout,
    QSplitter, QMessageBox, QFileDialog, QTabWidget,
)

from app.flowchart.canvas import FlowchartScene, FlowchartView
from app.flowchart.node import NodeItem
from app.flowchart.engine import ExecutionEngine
from app.panels.toolbox import ToolboxPanel
from app.panels.properties import PropertiesPanel
from app.panels.preview import PreviewPanel
from app.panels.output import OutputPanel
from app.panels.communication import CommunicationPanel


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DateVision - 工业视觉检测平台")
        self.resize(1400, 900)
        self.setMinimumSize(1024, 600)

        # 暗色主题
        self.setStyleSheet("""
            QMainWindow { background: #1e1e1e; }
            QMainWindow::separator { background: #3e3e42; width: 1px; height: 1px; }
            QDockWidget { background: #252526; titlebar-close-icon: url(none); }
            QDockWidget::title { background: #2d2d30; padding: 6px; border-bottom: 1px solid #3e3e42; }
            QToolBar { background: #2d2d30; border-bottom: 1px solid #3e3e42; spacing: 4px; padding: 2px; }
            QMenuBar { background: #2d2d30; color: #e0e0e0; border-bottom: 1px solid #3e3e42; }
            QMenuBar::item:selected { background: #094771; }
            QMenu { background: #2d2d30; color: #e0e0e0; border: 1px solid #3e3e42; }
            QMenu::item:selected { background: #094771; }
            QStatusBar { background: #007acc; color: white; font-family: "Microsoft YaHei"; }
            QSplitter::handle { background: #3e3e42; }
            QToolTip { background: #333; color: #ccc; border: 1px solid #555; }
        """)

        self._engine = ExecutionEngine()
        self._last_image: dict[str, np.ndarray] = {}
        self._current_file: str | None = None

        # 连续运行定时器
        self._continuous_timer = QTimer(self)
        self._continuous_timer.timeout.connect(self._do_execute)
        self._continuous_mode = False

        self._setup_actions()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_central()
        self._setup_dock_widgets()
        self._setup_statusbar()

    def _setup_actions(self):
        self._act_new = QAction("新建(&N)", self)
        self._act_new.setShortcut(QKeySequence.StandardKey.New)
        self._act_new.triggered.connect(self._on_new)

        self._act_open = QAction("打开(&O)", self)
        self._act_open.setShortcut(QKeySequence.StandardKey.Open)
        self._act_open.triggered.connect(self._on_open)

        self._act_save = QAction("保存(&S)", self)
        self._act_save.setShortcut(QKeySequence.StandardKey.Save)
        self._act_save.triggered.connect(self._on_save)

        self._act_save_as = QAction("另存为...", self)
        self._act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._act_save_as.triggered.connect(self._on_save_as)

        self._act_run = QAction("运行(&R)", self)
        self._act_run.setShortcut(QKeySequence("F5"))
        self._act_run.triggered.connect(self._on_run)

        self._act_continuous = QAction("连续运行", self)
        self._act_continuous.setCheckable(True)
        self._act_continuous.setShortcut(QKeySequence("F6"))
        self._act_continuous.triggered.connect(self._on_toggle_continuous)

        self._act_stop = QAction("停止", self)
        self._act_stop.setShortcut(QKeySequence("Shift+F5"))
        self._act_stop.triggered.connect(self._on_stop)

        self._act_delete = QAction("删除选中", self)
        self._act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self._act_delete.triggered.connect(self._on_delete)

        self._act_zoom_in = QAction("放大", self)
        self._act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self._act_zoom_in.triggered.connect(lambda: self._view.scale(1.15, 1.15))

        self._act_zoom_out = QAction("缩小", self)
        self._act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self._act_zoom_out.triggered.connect(lambda: self._view.scale(1 / 1.15, 1 / 1.15))

        self._act_fit = QAction("适应窗口", self)
        self._act_fit.setShortcut(QKeySequence("Ctrl+0"))
        self._act_fit.triggered.connect(self._on_fit)

        self._act_about = QAction("关于", self)
        self._act_about.triggered.connect(self._on_about)

        self._act_refresh_plugins = QAction("刷新插件", self)
        self._act_refresh_plugins.triggered.connect(self._on_refresh_plugins)

    def _setup_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("文件(&F)")
        file_menu.addAction(self._act_new)
        file_menu.addAction(self._act_open)
        file_menu.addAction(self._act_save)
        file_menu.addAction(self._act_save_as)
        file_menu.addSeparator()
        file_menu.addAction("退出(&X)", self.close)

        edit_menu = menu_bar.addMenu("编辑(&E)")
        edit_menu.addAction(self._act_delete)
        edit_menu.addSeparator()
        edit_menu.addAction(self._act_zoom_in)
        edit_menu.addAction(self._act_zoom_out)
        edit_menu.addAction(self._act_fit)

        run_menu = menu_bar.addMenu("运行(&R)")
        run_menu.addAction(self._act_run)
        run_menu.addAction(self._act_continuous)
        run_menu.addAction(self._act_stop)

        tools_menu = menu_bar.addMenu("工具(&T)")
        tools_menu.addAction(self._act_refresh_plugins)

        help_menu = menu_bar.addMenu("帮助(&H)")
        help_menu.addAction(self._act_about)

    def _setup_toolbar(self):
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        toolbar.setIconSize(toolbar.iconSize())

        for act in [self._act_new, self._act_open, self._act_save, None, self._act_run, self._act_continuous, self._act_stop, None, self._act_delete]:
            if act is None:
                toolbar.addSeparator()
            else:
                toolbar.addAction(act)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

    def _setup_central(self):
        self._scene = FlowchartScene()
        self._view = FlowchartView(self._scene, self)

        self._scene.node_selected.connect(self._on_node_selected)
        self._scene.node_deselected.connect(self._on_node_deselected)
        self._scene.node_added.connect(self._on_node_added)

        self.setCentralWidget(self._view)

    def _setup_dock_widgets(self):
        # 工具箱（左侧）
        self._toolbox = ToolboxPanel()
        toolbox_dock = QDockWidget("工具箱", self)
        toolbox_dock.setWidget(self._toolbox)
        toolbox_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        toolbox_dock.setMinimumWidth(180)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, toolbox_dock)

        # 属性面板（右侧）
        self._properties = PropertiesPanel()
        prop_dock = QDockWidget("属性", self)
        prop_dock.setWidget(self._properties)
        prop_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        prop_dock.setMinimumWidth(220)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, prop_dock)

        # 预览和输出（底部）
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._preview = PreviewPanel()

        # 右侧：输出 + 通信 标签页
        right_tabs = QTabWidget()
        right_tabs.setStyleSheet("""
            QTabWidget::pane { background: #1e1e1e; border: none; }
            QTabBar::tab { background: #2d2d30; color: #aaa; padding: 5px 15px;
                font-family: "Microsoft YaHei"; font-size: 11px; }
            QTabBar::tab:selected { background: #1e1e1e; color: #fff; }
        """)
        self._output = OutputPanel()
        self._communication = CommunicationPanel()
        right_tabs.addTab(self._output, "输出")
        right_tabs.addTab(self._communication, "通信")

        splitter.addWidget(self._preview)
        splitter.addWidget(right_tabs)
        splitter.setSizes([700, 300])
        bottom_layout.addWidget(splitter)

        # 通信面板触发执行
        self._communication.execute_requested.connect(self._on_comm_trigger)

        bottom_dock = QDockWidget("预览与输出", self)
        bottom_dock.setWidget(bottom_widget)
        bottom_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        bottom_dock.setMinimumHeight(200)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, bottom_dock)

        # 工具箱双击添加节点
        self._toolbox.plugin_double_clicked.connect(self._add_node_to_center)

    def _setup_statusbar(self):
        self._statusbar = QStatusBar()
        self._statusbar.showMessage("就绪")
        self.setStatusBar(self._statusbar)

    def _add_node_to_center(self, plugin_id: str):
        view_center = self._view.mapToScene(self._view.viewport().rect().center())
        offset = len(self._scene.get_nodes()) * 30
        pos = QPointF(view_center.x() - 70 + offset, view_center.y() - 50 + offset)
        self._scene.add_plugin_node(plugin_id, pos)
        self._statusbar.showMessage(f"已添加工具: {plugin_id}")

    def _on_node_selected(self, node: NodeItem):
        self._properties.set_node(node)

    def _on_node_deselected(self):
        self._properties.set_node(None)

    def _on_node_added(self, node: NodeItem):
        self._output.log_info(f"添加节点: {node.plugin_name} [{node.node_id}]")
        node.on_double_clicked = self._on_node_double_clicked

    def _on_node_double_clicked(self, node: NodeItem):
        """双击节点：打开专用编辑对话框（由插件自己声明）"""
        dialog_cls = node.plugin.get_dialog_class()
        if dialog_cls is None:
            self._output.log_info(f"节点 [{node.plugin_name}] 没有专用编辑界面")
            return

        input_image = self._get_input_image_for_node(node)
        dialog = dialog_cls(node.plugin, input_image, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._output.log_info(f"节点 [{node.plugin_name}] 编辑完成")
            self._statusbar.showMessage(f"{node.plugin_name} 参数已保存")

    def _get_input_image_for_node(self, node: NodeItem) -> np.ndarray | None:
        """获取节点的输入图像（执行上游节点）"""
        connections = self._scene.get_connections()
        executed = set()

        def _execute_upstream(n: NodeItem):
            """递归执行上游节点，传递所有端口数据"""
            if n.node_id in executed:
                return
            n.plugin.reset()
            for conn in connections:
                if conn.target_port and conn.target_port.parent_node is n:
                    src = conn.source_port.parent_node
                    _execute_upstream(src)
                    src_outputs = src.plugin.get_outputs()
                    tgt_port = conn.target_port.port_name
                    src_port = conn.source_port.port_name
                    if src_port in src_outputs:
                        n.plugin.set_input(tgt_port, src_outputs[src_port])
            n.plugin.execute()
            executed.add(n.node_id)

        for conn in connections:
            if conn.target_port and conn.target_port.parent_node is node:
                src_node = conn.source_port.parent_node
                try:
                    _execute_upstream(src_node)
                    outputs = src_node.plugin.get_outputs()
                    for name, val in outputs.items():
                        if isinstance(val, np.ndarray) and len(val.shape) >= 2:
                            return val
                except Exception:
                    pass
        return None

    def _on_run(self):
        self._output.log_info("开始执行流程图...")
        self._act_run.setEnabled(False)
        self._do_execute()
        self._act_run.setEnabled(True)
        self._statusbar.showMessage("执行完成")

    def _on_toggle_continuous(self, checked: bool):
        """切换连续运行模式"""
        self._continuous_mode = checked
        if checked:
            # 停止单次触发相关状态，启动连续运行
            self._continuous_timer.start(100)  # 每 100ms 执行一次
            self._act_run.setEnabled(False)
            self._output.log_info("已开启连续运行模式（每 100ms 执行一次）")
            self._statusbar.showMessage("连续运行中...")
        else:
            self._continuous_timer.stop()
            self._act_run.setEnabled(True)
            self._output.log_info("已关闭连续运行模式")
            self._statusbar.showMessage("已切换为单次触发")

    def _on_stop(self):
        self._engine._running = False
        # 连续模式下停止定时器
        if self._continuous_mode:
            self._act_continuous.setChecked(False)
            self._on_toggle_continuous(False)
        self._output.log_warning("执行已停止")
        self._act_run.setEnabled(True)

    def _on_delete(self):
        self._scene.remove_selected()
        self._properties.set_node(None)

    def _on_new(self):
        reply = QMessageBox.question(self, "新建", "确定要新建吗？当前流程图将被清除。",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._scene.clear_all()
            self._preview.set_image(None)
            self._output._clear()
            self._current_file = None
            self.setWindowTitle("DateVision - 工业视觉检测平台")
            self._statusbar.showMessage("新建流程图")

    def _on_open(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "打开项目", "",
            "DateVision 项目文件 (*.dvp);;JSON 文件 (*.json);;所有文件 (*.*)"
        )
        if not filepath:
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._scene.from_dict(data)
            self._preview.set_image(None)
            self._output._clear()
            self._current_file = filepath

            # 恢复通信配置
            if "communication" in data:
                self._communication.set_config(data["communication"])

            self.setWindowTitle(f"DateVision - {os.path.basename(filepath)}")
            self._output.log_success(f"已打开: {filepath}")
            self._statusbar.showMessage(f"已加载: {os.path.basename(filepath)}")
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法加载项目文件：\n{e}")
            self._output.log_error(f"打开失败: {e}")

    def _on_save(self):
        if self._current_file:
            self._save_to_file(self._current_file)
        else:
            self._on_save_as()

    def _on_save_as(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "保存项目", "untitled.dvp",
            "DateVision 项目文件 (*.dvp);;JSON 文件 (*.json);;所有文件 (*.*)"
        )
        if not filepath:
            return
        self._save_to_file(filepath)

    def _save_to_file(self, filepath: str):
        try:
            data = self._scene.to_dict()
            data["communication"] = self._communication.get_config()
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._current_file = filepath
            self.setWindowTitle(f"DateVision - {os.path.basename(filepath)}")
            self._output.log_success(f"已保存: {filepath}")
            self._statusbar.showMessage(f"已保存: {os.path.basename(filepath)}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存项目文件：\n{e}")
            self._output.log_error(f"保存失败: {e}")

    def _on_fit(self):
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _on_about(self):
        QMessageBox.about(self, "关于 DateVision",
                          "<h3>DateVision 工业视觉检测平台 v1.20.0.2</h3>"
                          "<p>基于 PySide6 + OpenCV 构建</p>"
                          "<p>开源免费，无授权限制</p>"
                          "<hr>"
                          "<p><b>开发者：</b>杨佳祺</p>"
                          "<p><b>联系电话：</b>15803820398</p>"
                          "<p><b>联系邮箱：</b>yangjiaqi@datekj.top</p>"
                          "<p><b>版权所有：</b>郑州德塔工业自动化</p>")

    def _on_refresh_plugins(self):
        self._toolbox.refresh()
        self._output.log_info("插件列表已刷新")

    def _on_comm_trigger(self):
        """通信面板触发检测"""
        self._output.log_info("TCP通信触发检测...")
        self._do_execute()

    def _do_execute(self):
        """执行流程图并生成通信响应"""
        nodes = self._scene.get_nodes()
        connections = self._scene.get_connections()

        if not nodes:
            self._output.log_warning("流程图为空，无法执行")
            self._communication.set_response_data("ERROR:NO_NODES")
            return

        self._engine.setup(nodes, connections)
        results = self._engine.execute()

        # 构建状态字符串
        order = self._engine.topological_sort()
        status_parts = []
        if order:
            node_map = self._scene.get_nodes()
            for nid in order:
                if nid in node_map:
                    status = "OK" if nid in results and not isinstance(results.get(nid), str) else "NG"
                    status_parts.append(status)

        delim = self._communication.get_delimiter()
        status_str = delim.join(status_parts) if status_parts else "NO_RESULT"

        # 构建输出内容
        output_str = self._build_comm_response(nodes, results)

        # 组合响应
        if output_str:
            response = f"{status_str}{delim}{output_str}"
        else:
            response = status_str

        self._communication.set_response_data(response)
        self._output.log_info(f"通信响应: {response[:200]}{'...' if len(response) > 200 else ''}")

        if "_error" in results:
            self._output.log_error(results["_error"])

        # 预览图像（成功的节点照常显示）
        if order:
            for node_id in reversed(order):
                node_results = self._engine.get_node_results(node_id)
                if isinstance(node_results, str):
                    continue
                for port_name, value in node_results.items():
                    if value is not None and hasattr(value, 'shape') and len(value.shape) >= 2:
                        self._preview.set_image(value)
                        break
                else:
                    continue
                break

        self._output.log_success("流程图执行完成")
        self._output.update_results(results)

    def _build_comm_response(self, nodes: dict, results: dict) -> str:
        """根据通信面板的输出格式生成响应字符串"""
        fmt = self._communication.get_output_format().strip()
        if not fmt:
            return ""

        delim = self._communication.get_delimiter()
        lines = [l.strip() for l in fmt.split("\n") if l.strip()]
        output_parts = []

        for line in lines:
            try:
                result = self._eval_format_line(line, nodes, results)
                output_parts.append(str(result))
            except Exception as e:
                output_parts.append(f"ERR:{e}")

        return delim.join(output_parts)

    def _eval_format_line(self, line: str, nodes: dict, results: dict) -> str:
        """解析一行格式字符串，替换 {node_id.port_name} 引用为实际值"""
        # 先替换所有 {node_id.port_name} 引用
        def replace_ref(match):
            ref = match.group(1).strip()
            parts = ref.split(".")
            if len(parts) >= 2:
                node_id = parts[0]
                port_name = parts[1]
                val = self._get_node_output_value(node_id, port_name, results)
                return str(val)
            return match.group(0)

        # 替换 {xxx} 引用
        line = re.sub(r'\{([^}]+)\}', replace_ref, line)

        # 尝试安全求值（仅允许 + - * / 和数字）
        try:
            # 安全检查：只允许数字、空格、运算符、小数点
            safe = re.sub(r'[\d\s+\-*/().]', '', line)
            if safe == '':
                val = eval(line)
                if isinstance(val, float):
                    return f"{val:.6f}".rstrip('0').rstrip('.')
                return str(val)
        except Exception:
            pass

        return line

    def _get_node_output_value(self, node_id: str, port_name: str, results: dict) -> str:
        """从执行结果中获取节点输出值"""
        node_results = results.get(node_id, {})
        if isinstance(node_results, dict):
            val = node_results.get(port_name)
            if val is not None:
                if isinstance(val, (int, float)):
                    return str(val)
                elif isinstance(val, list):
                    return str(len(val)) if len(val) > 0 else "0"
                return str(val)
        return "N/A"