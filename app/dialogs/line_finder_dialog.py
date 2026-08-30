"""线查找ROI绘制对话框 - 交互式ROI框绘制 + 参数设置 + 手动检测"""

import cv2
import numpy as np
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QImage, QPixmap, QKeyEvent,
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QGroupBox, QFormLayout,
    QSpinBox, QComboBox, QSlider, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QListWidget,
    QListWidgetItem, QMessageBox,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsItem, QGraphicsSceneMouseEvent, QStyleOptionGraphicsItem,
)


from plugins.line_finder import LineFinderPlugin


# ---- ROI 矩形图形项 ----
class ROIRectItem(QGraphicsRectItem):
    """可拖拽、可缩放的ROI矩形"""

    HANDLE_SIZE = 8

    def __init__(self, x, y, w, h, index: int, parent=None):
        super().__init__(x, y, w, h, parent)
        self.roi_index = index
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(10)
        self.setAcceptHoverEvents(True)

        self._dragging_handle = -1  # -1=none, 0=TL, 1=TR, 2=BL, 3=BR
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        self.setPen(QPen(QColor(0, 200, 255), 2, Qt.PenStyle.SolidLine))
        self.setBrush(QBrush(QColor(0, 200, 255, 30)))

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        super().paint(painter, option, widget)
        # 绘制四角手柄
        r = self.rect()
        hs = self.HANDLE_SIZE
        handles = [
            QRectF(r.left() - hs / 2, r.top() - hs / 2, hs, hs),
            QRectF(r.right() - hs / 2, r.top() - hs / 2, hs, hs),
            QRectF(r.left() - hs / 2, r.bottom() - hs / 2, hs, hs),
            QRectF(r.right() - hs / 2, r.bottom() - hs / 2, hs, hs),
        ]
        painter.setPen(QPen(QColor(0, 200, 255), 1))
        painter.setBrush(QBrush(QColor(0, 200, 255)))
        for h in handles:
            painter.drawRect(h)

        # 索引标签
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        painter.drawText(r.adjusted(4, 4, -4, -4), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         str(self.roi_index + 1))

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            r = self.rect()
            hs = self.HANDLE_SIZE
            handle_rects = [
                QRectF(r.left() - hs / 2, r.top() - hs / 2, hs, hs),
                QRectF(r.right() - hs / 2, r.top() - hs / 2, hs, hs),
                QRectF(r.left() - hs / 2, r.bottom() - hs / 2, hs, hs),
                QRectF(r.right() - hs / 2, r.bottom() - hs / 2, hs, hs),
            ]
            for i, hr in enumerate(handle_rects):
                if hr.contains(pos):
                    self._dragging_handle = i
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor if i in (0, 3) else Qt.CursorShape.SizeBDiagCursor)
                    event.accept()
                    return
            self._dragging_handle = -1
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging_handle >= 0:
            pos = event.pos()
            r = self.rect()
            new_rect = QRectF(r)
            if self._dragging_handle == 0:  # TL
                new_rect.setTopLeft(pos)
            elif self._dragging_handle == 1:  # TR
                new_rect.setTopRight(pos)
            elif self._dragging_handle == 2:  # BL
                new_rect.setBottomLeft(pos)
            elif self._dragging_handle == 3:  # BR
                new_rect.setBottomRight(pos)
            if new_rect.width() >= 10 and new_rect.height() >= 10:
                self.setRect(new_rect.normalized())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        self._dragging_handle = -1
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().mouseReleaseEvent(event)

    def get_roi(self) -> tuple[int, int, int, int]:
        pos = self.pos()
        r = self.rect()
        return (int(pos.x() + r.x()), int(pos.y() + r.y()), int(r.width()), int(r.height()))


# ---- 图像场景（支持ROI绘制） ----
class ROIImageScene(QGraphicsScene):
    """带背景图像的场景，支持绘制ROI"""

    roi_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._roi_items: list[ROIRectItem] = []
        self._drawing = False
        self._draw_start = QPointF()
        self._draw_item: Optional[ROIRectItem] = None
        self._image_pixmap: Optional[QPixmap] = None
        self._image_item = None

    def set_image(self, cv_img: np.ndarray):
        """设置背景图像"""
        self.clear()
        self._roi_items.clear()
        self._image_item = None

        if cv_img is None:
            return

        if len(cv_img.shape) == 2:
            h, w = cv_img.shape
            rgb = cv2.cvtColor(cv_img, cv2.COLOR_GRAY2RGB)
        else:
            h, w = cv_img.shape[:2]
            rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)

        bytes_per_line = 3 * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self._image_pixmap = QPixmap.fromImage(qimg)
        self._image_item = self.addPixmap(self._image_pixmap)
        self._image_item.setZValue(-1)
        self.setSceneRect(0, 0, w, h)

    def update_background(self, cv_img: np.ndarray):
        """更新背景图像（不清除ROI）"""
        if self._image_item is not None:
            self.removeItem(self._image_item)
            self._image_item = None

        if cv_img is None:
            return

        if len(cv_img.shape) == 2:
            h, w = cv_img.shape
            rgb = cv2.cvtColor(cv_img, cv2.COLOR_GRAY2RGB)
        else:
            h, w = cv_img.shape[:2]
            rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)

        bytes_per_line = 3 * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self._image_pixmap = QPixmap.fromImage(qimg)
        self._image_item = self.addPixmap(self._image_pixmap)
        self._image_item.setZValue(-1)

    def mark_detected_lines(self, lines: list, cv_img: np.ndarray):
        """在图像上叠加检测到的直线"""
        self.set_image(cv_img)

    def get_rois(self) -> list[tuple[int, int, int, int]]:
        return [item.get_roi() for item in self._roi_items]

    def remove_selected_roi(self):
        for item in self.selectedItems():
            if isinstance(item, ROIRectItem):
                self._roi_items.remove(item)
                self.removeItem(item)
                self._update_indices()
                self.roi_changed.emit()

    def clear_rois(self):
        for item in list(self._roi_items):
            self.removeItem(item)
        self._roi_items.clear()
        self.roi_changed.emit()

    def _update_indices(self):
        for i, item in enumerate(self._roi_items):
            item.roi_index = i

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else None)
            if item is None or item is self._image_item:
                # 开始绘制新ROI
                self._drawing = True
                self._draw_start = event.scenePos()
                self._draw_item = ROIRectItem(0, 0, 0, 0, len(self._roi_items))
                self._draw_item.setPos(self._draw_start)
                self.addItem(self._draw_item)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._drawing and self._draw_item:
            end = event.scenePos()
            start = self._draw_start
            x = min(start.x(), end.x())
            y = min(start.y(), end.y())
            w = abs(end.x() - start.x())
            h = abs(end.y() - start.y())
            self._draw_item.setPos(x, y)
            self._draw_item.setRect(0, 0, w, h)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if self._drawing and self._draw_item:
            self._drawing = False
            r = self._draw_item.rect()
            if r.width() >= 10 and r.height() >= 10:
                self._roi_items.append(self._draw_item)
                self._draw_item.setSelected(True)
                self.roi_changed.emit()
            else:
                self.removeItem(self._draw_item)
            self._draw_item = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ---- 线查找对话框 ----
class LineFinderDialog(QDialog):
    """线查找工具对话框"""

    def __init__(self, plugin: LineFinderPlugin, input_image: np.ndarray | None, parent=None):
        super().__init__(parent)
        self._plugin = plugin
        self._input_image = input_image
        self._source_image = input_image.copy() if input_image is not None else None
        self._detected_lines: list[tuple[float, float, float, float]] = []

        self.setWindowTitle("线查找工具 - ROI绘制与检测")
        self.resize(1200, 750)
        self.setMinimumSize(900, 500)

        self._setup_ui()
        self._load_params()

        if self._source_image is not None:
            self._scene.set_image(self._source_image)
            # 加载已有ROI
            for roi in plugin.get_rois():
                self._add_roi_item(roi[0], roi[1], roi[2], roi[3])

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)

        # ---- 左侧：图像显示区域 ----
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._scene = ROIImageScene()
        self._scene.roi_changed.connect(self._on_roi_changed)

        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setStyleSheet("background: #1e1e1e; border: 1px solid #3e3e42;")
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_layout.addWidget(self._view)

        # 图像下方工具栏
        toolbar = QHBoxLayout()
        self._btn_detect = QPushButton("检测")
        self._btn_detect.setStyleSheet(_btn_style("#0d7377", "#0a5c5f"))
        self._btn_detect.clicked.connect(self._on_detect)

        self._btn_learn = QPushButton("学习")
        self._btn_learn.setStyleSheet(_btn_style("#7b1fa2", "#6a1b9a"))
        self._btn_learn.clicked.connect(self._on_learn)
        self._btn_learn.setToolTip("根据ROI中间基准线自动学习两侧色差，计算出最优边缘位置和阈值")

        self._btn_fit = QPushButton("适应窗口")
        self._btn_fit.setStyleSheet(_btn_style("#3e3e42", "#505050"))
        self._btn_fit.clicked.connect(lambda: self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio))

        self._btn_clear_roi = QPushButton("清除ROI")
        self._btn_clear_roi.setStyleSheet(_btn_style("#3e3e42", "#505050"))
        self._btn_clear_roi.clicked.connect(self._on_clear_roi)

        self._btn_del_roi = QPushButton("删除选中ROI")
        self._btn_del_roi.setStyleSheet(_btn_style("#3e3e42", "#505050"))
        self._btn_del_roi.clicked.connect(self._on_del_roi)

        self._lbl_roi_count = QLabel("ROI: 0")
        self._lbl_roi_count.setStyleSheet("color: #aaa; font-size: 12px;")

        self._lbl_line_count = QLabel("线段: 0")
        self._lbl_line_count.setStyleSheet("color: #aaa; font-size: 12px;")

        toolbar.addWidget(self._btn_detect)
        toolbar.addWidget(self._btn_learn)
        toolbar.addWidget(self._btn_fit)
        toolbar.addWidget(self._btn_clear_roi)
        toolbar.addWidget(self._btn_del_roi)
        toolbar.addStretch()
        toolbar.addWidget(self._lbl_roi_count)
        toolbar.addWidget(self._lbl_line_count)
        left_layout.addLayout(toolbar)

        # ---- 右侧：参数和结果面板 ----
        right_widget = QWidget()
        right_widget.setFixedWidth(320)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 4, 0)
        right_layout.setSpacing(6)

        # 参数设置
        param_group = QGroupBox("检测参数")
        param_group.setStyleSheet(_group_style())
        param_layout = QFormLayout(param_group)
        param_layout.setSpacing(6)

        self._edge_t1 = self._make_slider("边缘低阈值", 0, 255, 30)
        self._edge_t2 = self._make_slider("边缘高阈值", 0, 255, 90)
        self._hough_t = self._make_slider("霍夫阈值", 1, 300, 30)
        self._min_len = self._make_slider("最小线长", 5, 500, 30)
        self._max_gap = self._make_slider("最大断距", 0, 100, 15)
        self._blur_ks = self._make_spin("模糊核", 1, 15, 3, 2)

        self._search_dir = QComboBox()
        self._search_dir.addItems(["垂直", "水平"])
        self._search_dir.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555;")
        self._search_dir.setToolTip("垂直=从上到下扫描找水平线，水平=从左到右扫描找竖直线")

        self._polarity = QComboBox()
        self._polarity.addItems(["明到暗", "暗到明", "任意"])
        self._polarity.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555;")
        self._polarity.setToolTip("明到暗=白底黑线，暗到明=黑底白线")

        self._learn_mode = QCheckBox("启用自动学习")
        self._learn_mode.setStyleSheet("color: #4fc3f7; font-weight: bold;")
        self._learn_mode.setToolTip("根据ROI内容自动学习色差阈值，无需手动调参")

        self._draw_color = QComboBox()
        self._draw_color.addItems(["绿色", "红色", "蓝色", "黄色", "青色", "白色"])
        self._draw_color.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555;")
        self._line_thick = self._make_spin("线宽", 1, 10, 2)

        param_layout.addRow("搜索方向:", self._search_dir)
        param_layout.addRow("边缘极性:", self._polarity)
        param_layout.addRow("", self._learn_mode)
        param_layout.addRow("Canny低阈值:", self._edge_t1)
        param_layout.addRow("Canny高阈值:", self._edge_t2)
        param_layout.addRow("霍夫阈值:", self._hough_t)
        param_layout.addRow("最小线长:", self._min_len)
        param_layout.addRow("最大断距:", self._max_gap)
        param_layout.addRow("模糊核:", self._blur_ks)
        param_layout.addRow("线条颜色:", self._draw_color)
        param_layout.addRow("线宽:", self._line_thick)
        right_layout.addWidget(param_group)

        # ROI 列表
        roi_group = QGroupBox("ROI列表")
        roi_group.setStyleSheet(_group_style())
        roi_layout = QVBoxLayout(roi_group)
        self._roi_list = QListWidget()
        self._roi_list.setStyleSheet("background: #1e1e1e; color: #ccc; border: 1px solid #333; font-size: 11px;")
        self._roi_list.setMaximumHeight(120)
        self._roi_list.itemClicked.connect(self._on_roi_list_clicked)
        roi_layout.addWidget(self._roi_list)
        right_layout.addWidget(roi_group)

        # 线段坐标表
        line_group = QGroupBox("检测结果 - 线段坐标")
        line_group.setStyleSheet(_group_style())
        line_layout = QVBoxLayout(line_group)
        self._line_table = QTableWidget()
        self._line_table.setColumnCount(5)
        self._line_table.setHorizontalHeaderLabels(["序号", "X1", "Y1", "X2", "Y2"])
        self._line_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._line_table.setStyleSheet(
            "QTableWidget { background: #1e1e1e; color: #ccc; border: 1px solid #333; gridline-color: #333; font-size: 11px; }"
            "QHeaderView::section { background: #2d2d30; color: #aaa; border: 1px solid #333; padding: 2px; }"
        )
        line_layout.addWidget(self._line_table)
        right_layout.addWidget(line_group)

        # 底部按钮
        btn_layout = QHBoxLayout()
        self._btn_apply = QPushButton("确定")
        self._btn_apply.setStyleSheet(_btn_style("#0d47a1", "#0a3678"))
        self._btn_apply.clicked.connect(self._on_apply)

        self._btn_cancel = QPushButton("取消")
        self._btn_cancel.setStyleSheet(_btn_style("#3e3e42", "#505050"))
        self._btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_apply)
        btn_layout.addWidget(self._btn_cancel)
        right_layout.addLayout(btn_layout)

        right_layout.addStretch()

        main_layout.addWidget(left_widget, 3)
        main_layout.addWidget(right_widget, 1)

    def _load_params(self):
        """从插件加载参数"""
        params = self._plugin.get_params()
        self._set_slider(self._edge_t1, params.get("edge_threshold1", 30))
        self._set_slider(self._edge_t2, params.get("edge_threshold2", 90))
        self._set_slider(self._hough_t, params.get("hough_threshold", 30))
        self._set_slider(self._min_len, params.get("min_line_length", 30))
        self._set_slider(self._max_gap, params.get("max_line_gap", 15))
        self._blur_ks.setValue(params.get("blur_ksize", 3))

        idx = self._search_dir.findText(params.get("search_direction", "垂直"))
        if idx >= 0:
            self._search_dir.setCurrentIndex(idx)
        idx = self._polarity.findText(params.get("edge_polarity", "明到暗"))
        if idx >= 0:
            self._polarity.setCurrentIndex(idx)
        self._learn_mode.setChecked(params.get("learn_mode", False))

        idx = self._draw_color.findText(params.get("draw_color", "绿色"))
        if idx >= 0:
            self._draw_color.setCurrentIndex(idx)
        self._line_thick.setValue(params.get("line_thickness", 2))

    def _save_params(self):
        """保存参数到插件"""
        self._plugin.set_param("edge_threshold1", self._get_slider(self._edge_t1))
        self._plugin.set_param("edge_threshold2", self._get_slider(self._edge_t2))
        self._plugin.set_param("hough_threshold", self._get_slider(self._hough_t))
        self._plugin.set_param("min_line_length", self._get_slider(self._min_len))
        self._plugin.set_param("max_line_gap", self._get_slider(self._max_gap))
        self._plugin.set_param("blur_ksize", self._blur_ks.value())
        self._plugin.set_param("search_direction", self._search_dir.currentText())
        self._plugin.set_param("edge_polarity", self._polarity.currentText())
        self._plugin.set_param("learn_mode", self._learn_mode.isChecked())
        self._plugin.set_param("draw_color", self._draw_color.currentText())
        self._plugin.set_param("line_thickness", self._line_thick.value())

    def _on_learn(self):
        """自动学习：分析ROI色差，找到最优边缘"""
        if self._source_image is None:
            QMessageBox.warning(self, "无图像", "请先连接图像源节点")
            return

        rois = self._scene.get_rois()
        if not rois:
            QMessageBox.warning(self, "无ROI", "请先在图像上绘制ROI框")
            return

        self._save_params()

        # 对第一个ROI执行学习
        result = self._plugin.auto_learn(self._source_image, rois[0])
        if result is None:
            QMessageBox.warning(self, "学习失败", "无法在ROI内找到有效边缘，请调整ROI位置或检查图像")
            return

        x1, y1, x2, y2, edge_t1, edge_t2 = result

        # 更新阈值滑条
        self._set_slider(self._edge_t1, edge_t1)
        self._set_slider(self._edge_t2, edge_t2)

        # 在图像上显示学习到的线
        self._plugin.set_rois(rois)
        self._plugin.set_input("input", self._source_image)
        self._plugin.execute()
        output_img = self._plugin.get_output("output")
        if output_img is not None:
            self._scene.update_background(output_img)

        # 更新结果
        self._detected_lines = self._plugin.get_detected_lines()
        self._update_line_table()
        self._lbl_line_count.setText(f"线段: {len(self._detected_lines)} (已学习)")
        self._lbl_line_count.setStyleSheet("color: #ce93d8; font-size: 12px;")
        self._lbl_line_count.setToolTip(
            f"学习完成\n阈值: [{edge_t1}, {edge_t2}]\n"
            f"线: ({x1:.0f},{y1:.0f}) → ({x2:.0f},{y2:.0f})"
        )

    def _on_detect(self):
        """手动检测"""
        if self._source_image is None:
            QMessageBox.warning(self, "无图像", "请先连接图像源节点，然后双击线查找节点打开此对话框")
            return

        self._save_params()

        rois = self._scene.get_rois()
        self._plugin.set_rois(rois)

        self._plugin.set_input("input", self._source_image)
        success = self._plugin.execute()

        if success:
            self._detected_lines = self._plugin.get_detected_lines()
            output_img = self._plugin.get_output("output")
            if output_img is not None:
                self._scene.update_background(output_img)
            self._update_line_table()
            self._lbl_line_count.setText(f"线段: {len(self._detected_lines)}")
            if not self._detected_lines:
                self._lbl_line_count.setStyleSheet("color: #ff9800; font-size: 12px;")
                self._lbl_line_count.setToolTip("未检测到线段，请降低边缘阈值或霍夫阈值")
            else:
                self._lbl_line_count.setStyleSheet("color: #4caf50; font-size: 12px;")
                self._lbl_line_count.setToolTip("")
        else:
            err = self._plugin.get_last_error()
            QMessageBox.warning(self, "检测失败", f"线查找检测失败：\n\n{err}" if err else "线查找检测失败，请检查参数")

    def _update_line_table(self):
        self._line_table.setRowCount(0)
        for i, (x1, y1, x2, y2) in enumerate(self._detected_lines):
            row = self._line_table.rowCount()
            self._line_table.insertRow(row)
            self._line_table.setItem(row, 0, QTableWidgetItem(str(i + 1)))
            self._line_table.setItem(row, 1, QTableWidgetItem(f"{x1:.1f}"))
            self._line_table.setItem(row, 2, QTableWidgetItem(f"{y1:.1f}"))
            self._line_table.setItem(row, 3, QTableWidgetItem(f"{x2:.1f}"))
            self._line_table.setItem(row, 4, QTableWidgetItem(f"{y2:.1f}"))

    def _add_roi_item(self, x, y, w, h):
        item = ROIRectItem(0, 0, w, h, len(self._scene._roi_items))
        item.setPos(x, y)
        self._scene.addItem(item)
        self._scene._roi_items.append(item)
        self._update_roi_list()

    def _on_roi_changed(self):
        self._update_roi_list()

    def _update_roi_list(self):
        self._roi_list.clear()
        rois = self._scene.get_rois()
        for i, (x, y, w, h) in enumerate(rois):
            self._roi_list.addItem(f"ROI {i + 1}: ({x},{y}) {w}x{h}")
        self._lbl_roi_count.setText(f"ROI: {len(rois)}")

    def _on_roi_list_clicked(self, item: QListWidgetItem):
        idx = self._roi_list.row(item)
        if idx < len(self._scene._roi_items):
            roi_item = self._scene._roi_items[idx]
            self._scene.clearSelection()
            roi_item.setSelected(True)
            self._view.centerOn(roi_item)

    def _on_clear_roi(self):
        self._scene.clear_rois()
        if self._source_image is not None:
            self._scene.set_image(self._source_image)
        self._line_table.setRowCount(0)
        self._detected_lines = []
        self._lbl_line_count.setText("线段: 0")

    def _on_del_roi(self):
        self._scene.remove_selected_roi()

    def _on_apply(self):
        self._save_params()
        rois = self._scene.get_rois()
        self._plugin.set_rois(rois)
        self._plugin.set_input("input", self._source_image)
        self._plugin.execute()
        self.accept()

    def _make_slider(self, label: str, min_v: int, max_v: int, default: int) -> QWidget:
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(min_v)
        slider.setMaximum(max_v)
        slider.setValue(default)
        slider.setStyleSheet("QSlider::groove:horizontal { height: 4px; background: #333; }"
                             "QSlider::handle:horizontal { width: 12px; margin: -4px 0; background: #0d7377; border-radius: 6px; }")
        val = QLabel(str(default))
        val.setStyleSheet("color: #ccc; min-width: 30px; font-size: 11px;")
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider.valueChanged.connect(lambda v: val.setText(str(v)))
        l.addWidget(slider)
        l.addWidget(val)
        w.slider = slider
        w.value_label = val
        return w

    def _make_spin(self, label: str, min_v: int, max_v: int, default: int, step: int = 1) -> QSpinBox:
        spin = QSpinBox()
        spin.setMinimum(min_v)
        spin.setMaximum(max_v)
        spin.setValue(default)
        spin.setSingleStep(step)
        spin.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555;")
        return spin

    def _get_slider(self, w: QWidget) -> int:
        return w.slider.value()

    def _set_slider(self, w: QWidget, value: int):
        w.slider.setValue(value)
        w.value_label.setText(str(value))

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Delete:
            self._scene.remove_selected_roi()
        else:
            super().keyPressEvent(event)


def _btn_style(bg: str, hover: str) -> str:
    return f"""
        QPushButton {{ background: {bg}; color: #fff; border: 1px solid #555;
            padding: 5px 14px; font-size: 12px; font-family: "Microsoft YaHei"; border-radius: 3px; }}
        QPushButton:hover {{ background: {hover}; }}
    """


def _group_style() -> str:
    return """
        QGroupBox { color: #e0e0e0; border: 1px solid #3e3e42; border-radius: 4px;
            margin-top: 10px; padding-top: 16px; font-size: 12px; font-weight: bold; font-family: "Microsoft YaHei"; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
    """