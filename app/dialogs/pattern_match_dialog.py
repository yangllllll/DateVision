"""模板匹配专用对话框 - ROI框选训练模板 + 参数设置 + 检测"""


from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QPainter, QImage, QPixmap,
    QKeyEvent,
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QGroupBox, QFormLayout, QComboBox, QSlider,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QGraphicsView
)

from app.dialogs.line_finder_dialog import ROIImageScene, ROIRectItem


class PatternMatchDialog(QDialog):
    """模板匹配训练对话框"""

    def __init__(self, plugin, input_image, parent=None):
        super().__init__(parent)
        self._plugin = plugin
        self._source_image = input_image.copy() if input_image is not None else None
        self._match_positions = []

        self.setWindowTitle("模板匹配 - 训练与检测")
        self.resize(1100, 700)
        self.setMinimumSize(800, 500)

        self._setup_ui()
        self._load_params()

        if self._source_image is not None:
            self._scene.set_image(self._source_image)
            # 加载已有模板ROI
            roi = self._plugin.get_template_roi()
            if roi:
                self._add_roi_item(roi[0], roi[1], roi[2], roi[3])

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)

        # ---- 左侧：图像显示 ----
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._scene = ROIImageScene()
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setStyleSheet("background: #1e1e1e; border: 1px solid #3e3e42;")
        left_layout.addWidget(self._view)

        toolbar = QHBoxLayout()
        self._btn_train = QPushButton("训练")
        self._btn_train.setStyleSheet(_btn_style("#7b1fa2", "#6a1b9a"))
        self._btn_train.clicked.connect(self._on_train)
        self._btn_train.setToolTip("从当前ROI框选区域提取模板")

        self._btn_detect = QPushButton("检测")
        self._btn_detect.setStyleSheet(_btn_style("#0d7377", "#0a5c5f"))
        self._btn_detect.clicked.connect(self._on_detect)

        self._btn_fit = QPushButton("适应窗口")
        self._btn_fit.setStyleSheet(_btn_style("#3e3e42", "#505050"))
        self._btn_fit.clicked.connect(lambda: self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio))

        self._btn_clear = QPushButton("清除ROI")
        self._btn_clear.setStyleSheet(_btn_style("#3e3e42", "#505050"))
        self._btn_clear.clicked.connect(self._on_clear)

        self._lbl_status = QLabel("请绘制ROI框")
        self._lbl_status.setStyleSheet("color: #aaa; font-size: 12px;")

        toolbar.addWidget(self._btn_train)
        toolbar.addWidget(self._btn_detect)
        toolbar.addWidget(self._btn_fit)
        toolbar.addWidget(self._btn_clear)
        toolbar.addStretch()
        toolbar.addWidget(self._lbl_status)
        left_layout.addLayout(toolbar)

        # ---- 右侧面板 ----
        right_widget = QWidget()
        right_widget.setFixedWidth(300)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 4, 0)
        right_layout.setSpacing(6)

        # 模板预览
        preview_group = QGroupBox("模板预览")
        preview_group.setStyleSheet(_group_style())
        preview_layout = QVBoxLayout(preview_group)
        self._template_preview = QLabel("(未训练)")
        self._template_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._template_preview.setMinimumHeight(120)
        self._template_preview.setStyleSheet("background: #1e1e1e; border: 1px solid #333; color: #666;")
        self._template_size = QLabel("")
        self._template_size.setStyleSheet("color: #888; font-size: 11px;")
        preview_layout.addWidget(self._template_preview)
        preview_layout.addWidget(self._template_size)
        right_layout.addWidget(preview_group)

        # 匹配参数
        param_group = QGroupBox("匹配参数")
        param_group.setStyleSheet(_group_style())
        param_layout = QFormLayout(param_group)
        param_layout.setSpacing(6)

        self._method = QComboBox()
        self._method.addItems(["CCOEFF", "CCOEFF_NORMED", "CCORR", "CCORR_NORMED", "SQDIFF", "SQDIFF_NORMED"])
        self._method.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555;")

        self._threshold = self._make_slider("匹配阈值", 0, 100, 80)
        self._max_matches = self._make_slider("最大匹配数", 1, 50, 10)

        self._draw_color = QComboBox()
        self._draw_color.addItems(["绿色", "红色", "蓝色", "黄色", "青色", "白色"])
        self._draw_color.setStyleSheet("background: #333; color: #ccc; border: 1px solid #555;")
        self._line_thick = self._make_slider("线宽", 1, 5, 2)

        param_layout.addRow("匹配方法:", self._method)
        param_layout.addRow("阈值(%):", self._threshold)
        param_layout.addRow("最大匹配:", self._max_matches)
        param_layout.addRow("标记颜色:", self._draw_color)
        param_layout.addRow("线宽:", self._line_thick)
        right_layout.addWidget(param_group)

        # 匹配结果
        result_group = QGroupBox("匹配结果")
        result_group.setStyleSheet(_group_style())
        result_layout = QVBoxLayout(result_group)
        self._result_table = QTableWidget()
        self._result_table.setColumnCount(3)
        self._result_table.setHorizontalHeaderLabels(["序号", "X", "Y"])
        self._result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._result_table.setStyleSheet(
            "QTableWidget { background: #1e1e1e; color: #ccc; border: 1px solid #333; gridline-color: #333; font-size: 11px; }"
            "QHeaderView::section { background: #2d2d30; color: #aaa; border: 1px solid #333; padding: 2px; }"
        )
        result_layout.addWidget(self._result_table)
        right_layout.addWidget(result_group)

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

        main_layout.addWidget(left_widget, 3)
        main_layout.addWidget(right_widget, 1)

    def _load_params(self):
        params = self._plugin.get_params()
        idx = self._method.findText(params.get("method", "CCOEFF_NORMED"))
        if idx >= 0:
            self._method.setCurrentIndex(idx)
        self._set_slider(self._threshold, int(params.get("threshold", 0.8) * 100))
        self._set_slider(self._max_matches, params.get("max_matches", 10))
        idx = self._draw_color.findText(params.get("draw_color", "绿色"))
        if idx >= 0:
            self._draw_color.setCurrentIndex(idx)
        self._set_slider(self._line_thick, params.get("line_thickness", 2))

    def _save_params(self):
        self._plugin.set_param("method", self._method.currentText())
        self._plugin.set_param("threshold", self._get_slider(self._threshold) / 100.0)
        self._plugin.set_param("max_matches", self._get_slider(self._max_matches))
        self._plugin.set_param("draw_color", self._draw_color.currentText())
        self._plugin.set_param("line_thickness", self._get_slider(self._line_thick))

    def _on_train(self):
        if self._source_image is None:
            QMessageBox.warning(self, "无图像", "请先连接图像源节点")
            return

        rois = self._scene.get_rois()
        if not rois:
            QMessageBox.warning(self, "无ROI", "请先在图像上框选模板区域")
            return

        template = self._plugin.train_template(self._source_image, rois[0])
        if template is None:
            QMessageBox.warning(self, "训练失败", "无法提取模板，请确保ROI大小合适")
            return

        # 显示模板预览
        h, w = template.shape
        preview_h = 120
        scale = preview_h / h if h > preview_h else 1.0
        pw, ph = int(w * scale), int(h * scale)
        if pw > 250:
            scale = 250 / w
            pw, ph = int(w * scale), int(h * scale)

        qimg = QImage(template.data, w, h, w, QImage.Format.Format_Grayscale8)
        pixmap = QPixmap.fromImage(qimg).scaled(pw, ph, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._template_preview.setPixmap(pixmap)
        self._template_size.setText(f"模板尺寸: {w} x {h}")

        self._lbl_status.setText(f"模板已训练 ({w}x{h})，缓存: tmp/template_pattern_match.png")
        self._lbl_status.setStyleSheet("color: #ce93d8; font-size: 12px;")

    def _on_detect(self):
        if self._source_image is None:
            return
        self._save_params()

        template = self._plugin.get_template_image()
        if template is None:
            QMessageBox.warning(self, "无模板", '请先点击"训练"按钮提取模板')
            return

        self._plugin.set_input("input", self._source_image)
        success = self._plugin.execute()

        if success:
            output = self._plugin.get_output("output")
            if output is not None:
                self._scene.update_background(output)
                # 恢复ROI框
                for roi in self._scene.get_rois():
                    self._add_roi_item(roi[0], roi[1], roi[2], roi[3])

            self._match_positions = self._plugin.get_output("match_positions") or []
            self._update_result_table()
            self._lbl_status.setText(f"匹配到 {len(self._match_positions)} 个位置")
            self._lbl_status.setStyleSheet(f"color: {'#4caf50' if self._match_positions else '#ff9800'}; font-size: 12px;")
        else:
            QMessageBox.warning(self, "检测失败", self._plugin.get_last_error())

    def _update_result_table(self):
        self._result_table.setRowCount(0)
        for i, (x, y) in enumerate(self._match_positions):
            row = self._result_table.rowCount()
            self._result_table.insertRow(row)
            self._result_table.setItem(row, 0, QTableWidgetItem(str(i + 1)))
            self._result_table.setItem(row, 1, QTableWidgetItem(str(x)))
            self._result_table.setItem(row, 2, QTableWidgetItem(str(y)))

    def _add_roi_item(self, x, y, w, h):
        item = ROIRectItem(0, 0, w, h, len(self._scene._roi_items))
        item.setPos(x, y)
        self._scene.addItem(item)
        self._scene._roi_items.append(item)

    def _on_clear(self):
        self._scene.clear_rois()
        if self._source_image is not None:
            self._scene.set_image(self._source_image)
        self._template_preview.setText("(未训练)")
        self._template_preview.setPixmap(QPixmap())
        self._template_size.setText("")
        self._result_table.setRowCount(0)
        self._match_positions = []
        self._lbl_status.setText("请绘制ROI框")
        self._lbl_status.setStyleSheet("color: #aaa; font-size: 12px;")

    def _on_apply(self):
        self._save_params()
        self.accept()

    def _make_slider(self, label, min_v, max_v, default):
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
        val.setStyleSheet("color: #ccc; min-width: 28px; font-size: 11px;")
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider.valueChanged.connect(lambda v: val.setText(str(v)))
        l.addWidget(slider)
        l.addWidget(val)
        w.slider = slider
        w.value_label = val
        return w

    def _get_slider(self, w):
        return w.slider.value()

    def _set_slider(self, w, value):
        w.slider.setValue(value)
        w.value_label.setText(str(value))

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Delete:
            self._scene.remove_selected_roi()
        else:
            super().keyPressEvent(event)


def _btn_style(bg, hover):
    return f"""
        QPushButton {{ background: {bg}; color: #fff; border: 1px solid #555;
            padding: 5px 14px; font-size: 12px; font-family: "Microsoft YaHei"; border-radius: 3px; }}
        QPushButton:hover {{ background: {hover}; }}
    """


def _group_style():
    return """
        QGroupBox { color: #e0e0e0; border: 1px solid #3e3e42; border-radius: 4px;
            margin-top: 10px; padding-top: 16px; font-size: 12px; font-weight: bold; font-family: "Microsoft YaHei"; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        QLabel { color: #aaa; font-size: 11px; font-family: "Microsoft YaHei"; }
    """