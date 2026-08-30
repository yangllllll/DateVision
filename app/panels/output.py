"""输出面板 - 显示执行日志和结果"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit,
    QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QHBoxLayout, QPushButton,
)


class OutputPanel(QWidget):
    """输出面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏
        header = QWidget()
        header.setStyleSheet("background: #2d2d30; border-bottom: 1px solid #3e3e42;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)

        title = QLabel("  输出")
        title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")

        self._clear_btn = QPushButton("清空")
        self._clear_btn.setStyleSheet("""
            QPushButton { background: #3e3e42; color: #ccc; border: 1px solid #555;
            padding: 3px 10px; font-size: 11px; }
            QPushButton:hover { background: #505050; }
        """)
        self._clear_btn.clicked.connect(self._clear)

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self._clear_btn)
        layout.addWidget(header)

        # 标签页
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane { background: #1e1e1e; border: none; }
            QTabBar::tab { background: #2d2d30; color: #aaa; padding: 5px 15px;
            font-family: "Microsoft YaHei"; font-size: 11px; }
            QTabBar::tab:selected { background: #1e1e1e; color: #fff; }
        """)

        # 日志
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet("""
            QTextEdit { background: #1e1e1e; color: #ccc; border: none;
            font-family: "Consolas", "Microsoft YaHei"; font-size: 11px; }
        """)
        self._tabs.addTab(self._log, "日志")

        # 结果表格
        self._result_table = QTableWidget()
        self._result_table.setColumnCount(3)
        self._result_table.setHorizontalHeaderLabels(["节点", "输出端口", "值"])
        self._result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._result_table.setStyleSheet("""
            QTableWidget { background: #1e1e1e; color: #ccc; border: none;
            gridline-color: #333; font-family: "Microsoft YaHei"; font-size: 11px; }
            QHeaderView::section { background: #2d2d30; color: #aaa; border: 1px solid #333;
            padding: 4px; }
        """)
        self._tabs.addTab(self._result_table, "结果")

        layout.addWidget(self._tabs)

    def log(self, message: str, color: str = "#cccccc"):
        # 日志超过 50 条时自动清屏
        if self._log.document().blockCount() > 50:
            self._log.clear()
        self._log.moveCursor(QTextCursor.MoveOperation.End)
        self._log.setTextColor(QColor(color))
        self._log.insertPlainText(message + "\n")
        self._log.moveCursor(QTextCursor.MoveOperation.End)

    def log_success(self, message: str):
        self.log(f"[成功] {message}", "#4caf50")

    def log_error(self, message: str):
        self.log(f"[错误] {message}", "#f44336")

    def log_info(self, message: str):
        self.log(f"[信息] {message}", "#2196f3")

    def log_warning(self, message: str):
        self.log(f"[警告] {message}", "#ff9800")

    def update_results(self, results: dict):
        self._result_table.setRowCount(0)
        row = 0
        for node_id, outputs in results.items():
            if node_id.startswith("_"):
                continue
            if isinstance(outputs, dict):
                for port_name, value in outputs.items():
                    self._result_table.insertRow(row)
                    self._result_table.setItem(row, 0, QTableWidgetItem(node_id))
                    self._result_table.setItem(row, 1, QTableWidgetItem(port_name))
                    val_str = str(value)[:100] if value is not None else "None"
                    self._result_table.setItem(row, 2, QTableWidgetItem(val_str))
                    row += 1

    def _clear(self):
        self._log.clear()
        self._result_table.setRowCount(0)