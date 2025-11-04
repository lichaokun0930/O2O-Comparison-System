"""
O2O 比价工具 - PyQt6 专业级 GUI
现代化界面设计
"""
import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QTextEdit, 
    QProgressBar, QGroupBox, QComboBox, QMessageBox, QFrame,
    QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor, QLinearGradient

class ComparisonWorker(QThread):
    """后台比价任务线程"""
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, store_a_file, store_b_file, model_choice):
        super().__init__()
        self.store_a_file = store_a_file
        self.store_b_file = store_b_file
        self.model_choice = model_choice
        
    def run(self):
        try:
            self.status.emit("正在导入比价模块...")
            self.progress.emit(10)
            
            # 设置环境变量
            import os
            os.environ['COMPARE_STORE_A_FILE'] = self.store_a_file
            os.environ['COMPARE_STORE_B_FILE'] = self.store_b_file
            os.environ['GUI_MODE'] = '1'
            
            # 设置模型模式
            if self.model_choice == 0:  # 平衡模式
                os.environ['EMBEDDING_MODEL'] = 'BAAI/bge-base-zh-v1.5'
                os.environ['RERANKER_MODEL'] = 'BAAI/bge-reranker-base'
                os.environ['MODEL_MODE'] = '平衡模式'
            else:  # 高精度模式
                os.environ['EMBEDDING_MODEL'] = 'BAAI/bge-large-zh-v1.5'
                os.environ['RERANKER_MODEL'] = 'BAAI/bge-reranker-large'
                os.environ['MODEL_MODE'] = '高精度模式'
            
            self.status.emit("正在加载数据文件...")
            self.progress.emit(30)
            
            # 动态导入主程序并运行
            from product_comparison_tool_local import main
            
            self.status.emit("正在进行比价分析...")
            self.progress.emit(50)
            
            # 执行主函数
            main()
            
            self.progress.emit(100)
            
            # 查找最新的报告文件
            from pathlib import Path
            import glob
            reports = glob.glob("reports/matched_products_comparison_final_*.xlsx")
            if reports:
                latest_report = max(reports, key=lambda x: Path(x).stat().st_mtime)
                self.finished.emit(latest_report)
            else:
                self.finished.emit("reports/")
            
        except Exception as e:
            self.error.emit(f"比价失败: {str(e)}")


class ModernButton(QPushButton):
    """超现代化按钮 - 带渐变和阴影"""
    def __init__(self, text, primary=False):
        super().__init__(text)
        self.setMinimumHeight(45)
        self.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Medium))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 3)
        self.setGraphicsEffect(shadow)
        
        if primary:
            self.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:1,
                        stop:0 #0078D4, 
                        stop:1 #0063B1
                    );
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 12px 30px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:1,
                        stop:0 #106EBE, 
                        stop:1 #005A9E
                    );
                }
                QPushButton:pressed {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:1,
                        stop:0 #005A9E, 
                        stop:1 #004578
                    );
                }
                QPushButton:disabled {
                    background: #E0E0E0;
                    color: #999999;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: white;
                    color: #333333;
                    border: 2px solid #E0E0E0;
                    border-radius: 8px;
                    padding: 10px 25px;
                }
                QPushButton:hover {
                    background: #F8F8F8;
                    border-color: #0078D4;
                    color: #0078D4;
                }
                QPushButton:pressed {
                    background: #E8E8E8;
                }
            """)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store_a_file = None
        self.store_b_file = None
        self.worker = None
        
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("O2O 商品比价分析工具 - 专业版")
        self.setGeometry(100, 100, 950, 750)
        
        # 设置超现代化样式
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #F0F4F8, 
                    stop:1 #E8EEF4
                );
            }
            QLabel {
                color: #2C3E50;
                font-family: "Microsoft YaHei UI";
            }
            QLineEdit {
                padding: 12px 15px;
                border: 2px solid #E0E6ED;
                border-radius: 6px;
                background-color: white;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border: 2px solid #0078D4;
                background-color: #FAFBFC;
            }
            QLineEdit:hover {
                border-color: #B0C4DE;
            }
            QGroupBox {
                font-weight: 600;
                font-size: 11pt;
                border: none;
                border-radius: 12px;
                margin-top: 15px;
                padding: 20px;
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 white,
                    stop:1 #FAFBFC
                );
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 20px;
                padding: 5px 15px;
                background-color: white;
                border-radius: 6px;
                color: #0078D4;
            }
            QComboBox {
                padding: 10px 15px;
                border: 2px solid #E0E6ED;
                border-radius: 6px;
                background-color: white;
                min-width: 250px;
                font-size: 10pt;
            }
            QComboBox:hover {
                border-color: #0078D4;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #666;
                margin-right: 10px;
            }
            QTextEdit {
                border: 2px solid #E0E6ED;
                border-radius: 8px;
                background-color: #FAFBFC;
                font-family: "Consolas", "Microsoft YaHei UI";
                font-size: 9pt;
                padding: 10px;
            }
            QProgressBar {
                border: none;
                border-radius: 6px;
                text-align: center;
                background-color: #E8EEF4;
                height: 28px;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0078D4,
                    stop:0.5 #00A4EF,
                    stop:1 #0078D4
                );
                border-radius: 5px;
            }
        """)
        
        # 中央窗口
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标题
        title = QLabel("O2O 商品比价分析工具")
        title.setFont(QFont("Microsoft YaHei UI", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #0078D4; margin: 10px 0;")
        layout.addWidget(title)
        
        # 文件选择区域
        file_group = QGroupBox("📁 数据文件选择")
        file_group.setFont(QFont("Microsoft YaHei UI", 11))
        
        # 添加卡片阴影效果
        shadow1 = QGraphicsDropShadowEffect()
        shadow1.setBlurRadius(20)
        shadow1.setColor(QColor(0, 0, 0, 25))
        shadow1.setOffset(0, 4)
        file_group.setGraphicsEffect(shadow1)
        
        file_layout = QVBoxLayout()
        file_layout.setSpacing(12)
        
        # 本店文件
        store_a_layout = QHBoxLayout()
        store_a_label = QLabel("本店数据:")
        store_a_label.setMinimumWidth(80)
        store_a_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.store_a_input = QLineEdit()
        self.store_a_input.setPlaceholderText("请选择本店商品数据文件...")
        self.store_a_input.setReadOnly(True)
        store_a_btn = ModernButton("浏览...")
        store_a_btn.clicked.connect(self.select_store_a)
        store_a_layout.addWidget(store_a_label)
        store_a_layout.addWidget(self.store_a_input)
        store_a_layout.addWidget(store_a_btn)
        
        # 竞对文件
        store_b_layout = QHBoxLayout()
        store_b_label = QLabel("竞对数据:")
        store_b_label.setMinimumWidth(80)
        store_b_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.store_b_input = QLineEdit()
        self.store_b_input.setPlaceholderText("请选择竞对商品数据文件...")
        self.store_b_input.setReadOnly(True)
        store_b_btn = ModernButton("浏览...")
        store_b_btn.clicked.connect(self.select_store_b)
        store_b_layout.addWidget(store_b_label)
        store_b_layout.addWidget(self.store_b_input)
        store_b_layout.addWidget(store_b_btn)
        
        file_layout.addLayout(store_a_layout)
        file_layout.addLayout(store_b_layout)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # 模型选择区域
        model_group = QGroupBox("🔧 模型配置")
        model_group.setFont(QFont("Microsoft YaHei UI", 11))
        
        # 添加卡片阴影效果
        shadow2 = QGraphicsDropShadowEffect()
        shadow2.setBlurRadius(20)
        shadow2.setColor(QColor(0, 0, 0, 25))
        shadow2.setOffset(0, 4)
        model_group.setGraphicsEffect(shadow2)
        
        model_layout = QHBoxLayout()
        
        model_label = QLabel("匹配模式:")
        model_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "平衡模式 (推荐)",
            "高精度模式 (最佳准确率)"
        ])
        self.model_combo.setCurrentIndex(0)  # 默认平衡模式
        self.model_combo.setFont(QFont("Microsoft YaHei UI", 10))
        
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_combo)
        model_layout.addStretch()
        model_group.setLayout(model_layout)
        layout.addWidget(model_group)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.start_btn = ModernButton("开始比价分析", primary=True)
        self.start_btn.setMinimumWidth(150)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start_comparison)
        button_layout.addWidget(self.start_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # 进度区域
        progress_group = QGroupBox("📊 运行状态")
        progress_group.setFont(QFont("Microsoft YaHei UI", 11))
        
        # 添加卡片阴影效果
        shadow3 = QGraphicsDropShadowEffect()
        shadow3.setBlurRadius(20)
        shadow3.setColor(QColor(0, 0, 0, 25))
        shadow3.setOffset(0, 4)
        progress_group.setGraphicsEffect(shadow3)
        
        progress_layout = QVBoxLayout()
        
        self.status_label = QLabel("等待开始...")
        self.status_label.setFont(QFont("Microsoft YaHei UI", 9))
        self.status_label.setStyleSheet("color: #666666;")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(25)
        self.progress_bar.setValue(0)
        
        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.progress_bar)
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # 日志区域
        log_group = QGroupBox("📝 运行日志")
        log_group.setFont(QFont("Microsoft YaHei UI", 11))
        
        # 添加卡片阴影效果
        shadow4 = QGraphicsDropShadowEffect()
        shadow4.setBlurRadius(20)
        shadow4.setColor(QColor(0, 0, 0, 25))
        shadow4.setOffset(0, 4)
        log_group.setGraphicsEffect(shadow4)
        
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        # 添加初始日志
        self.append_log("系统就绪，等待选择文件...")
        
    def select_store_a(self):
        """选择本店文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择本店数据文件",
            "",
            "Excel 文件 (*.xlsx *.xls);;所有文件 (*.*)"
        )
        if file_path:
            self.store_a_file = file_path
            self.store_a_input.setText(file_path)
            self.append_log(f"✓ 已选择本店文件: {Path(file_path).name}")
            self.check_ready()
            
    def select_store_b(self):
        """选择竞对文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择竞对数据文件",
            "",
            "Excel 文件 (*.xlsx *.xls);;所有文件 (*.*)"
        )
        if file_path:
            self.store_b_file = file_path
            self.store_b_input.setText(file_path)
            self.append_log(f"✓ 已选择竞对文件: {Path(file_path).name}")
            self.check_ready()
            
    def check_ready(self):
        """检查是否可以开始"""
        if self.store_a_file and self.store_b_file:
            self.start_btn.setEnabled(True)
            self.status_label.setText("✓ 准备就绪，可以开始比价")
            self.status_label.setStyleSheet("color: #107C10;")
        else:
            self.start_btn.setEnabled(False)
            
    def start_comparison(self):
        """开始比价"""
        self.start_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.append_log("\n" + "="*50)
        self.append_log("开始比价分析...")
        
        # 获取模型选择
        model_index = self.model_combo.currentIndex()
        
        # 创建工作线程
        self.worker = ComparisonWorker(
            self.store_a_file,
            self.store_b_file,
            model_index
        )
        
        # 连接信号
        self.worker.progress.connect(self.update_progress)
        self.worker.status.connect(self.update_status)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        
        # 启动线程
        self.worker.start()
        
    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)
        
    def update_status(self, message):
        """更新状态"""
        self.status_label.setText(message)
        self.append_log(message)
        
    def on_finished(self, result_file):
        """完成回调"""
        self.append_log(f"\n✓ 比价完成！")
        self.append_log(f"报告文件: {result_file}")
        self.status_label.setText("✓ 比价完成")
        self.status_label.setStyleSheet("color: #107C10;")
        self.start_btn.setEnabled(True)
        
        # 弹出成功提示
        QMessageBox.information(
            self,
            "比价完成",
            f"比价分析已完成！\n\n报告已保存至:\n{result_file}"
        )
        
    def on_error(self, error_msg):
        """错误回调"""
        self.append_log(f"\n✗ 错误: {error_msg}")
        self.status_label.setText("✗ 比价失败")
        self.status_label.setStyleSheet("color: #D13438;")
        self.start_btn.setEnabled(True)
        
        QMessageBox.critical(
            self,
            "比价失败",
            f"比价过程中发生错误:\n\n{error_msg}"
        )
        
    def append_log(self, message):
        """添加日志"""
        self.log_text.append(message)
        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )


def main():
    app = QApplication(sys.argv)
    
    # 设置应用程序字体
    app.setFont(QFont("Microsoft YaHei UI", 9))
    
    # 创建主窗口
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
