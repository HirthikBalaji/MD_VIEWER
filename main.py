"""
Python Markdown Viewer
A feature-rich Markdown editor and viewer application built with Python and PyQt6.

Features:
- Live preview rendering of Markdown.
- Syntax highlighting for code blocks using Pygments.
- File operations: Open, Save, Save As.
- Export to HTML and PDF.
- Search functionality with highlighting.
- Dark mode and font size adjustments.
- AI-powered summarization and explanation via the Google Gemini API in a dedicated tab.
"""

import sys
import os
import markdown2
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.formatters import HtmlFormatter
import google.generativeai as genai

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QSplitter, QFileDialog, QMessageBox, QLineEdit,
    QPushButton, QLabel, QInputDialog, QTabWidget
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QKeySequence


class MarkdownViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Python Markdown Viewer")
        self.setGeometry(100, 100, 1200, 800)

        self.current_file_path = None
        self.api_key_set = False
        self.gemini_api_key = None

        # --- UI Setup ---
        self.setup_ui()
        self.create_menus()
        self.create_search_bar()
        self.load_styles()

        # Timer for debouncing the live preview update
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.update_preview)

        self.editor.textChanged.connect(self.on_text_changed)

        # Initial empty preview
        self.update_preview()

    def setup_ui(self):
        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Search bar area
        self.search_bar_widget = QWidget()
        search_layout = QHBoxLayout(self.search_bar_widget)
        search_layout.setContentsMargins(0, 0, 0, 0)
        self.search_bar_widget.setVisible(False)  # Initially hidden
        main_layout.addWidget(self.search_bar_widget)

        # Main Tab Widget
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # --- Tab 1: Markdown Editor ---
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Type your Markdown here...")
        self.editor.setStyleSheet(
            "font-family: 'Courier New'; font-size: 14px; color: #333; background-color: #fdfdfd;")
        editor_layout.addWidget(self.editor)
        self.tabs.addTab(editor_widget, "Editor")

        # --- Tab 2: HTML Preview ---
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        self.preview = QWebEngineView()
        preview_layout.addWidget(self.preview)
        self.tabs.addTab(preview_widget, "Preview")

        # --- Tab 3: AI Assistant ---
        ai_widget = QWidget()
        ai_layout = QVBoxLayout(ai_widget)

        ai_layout.addWidget(QLabel("Content to Analyze:"))
        self.ai_input_text = QTextEdit()
        self.ai_input_text.setReadOnly(True)
        ai_layout.addWidget(self.ai_input_text)

        self.ai_action_button = QPushButton("Summarize / Explain Content Above")
        self.ai_action_button.clicked.connect(self.run_ai_generation)
        ai_layout.addWidget(self.ai_action_button)

        ai_layout.addWidget(QLabel("AI Response:"))
        self.ai_output_text = QTextEdit()
        self.ai_output_text.setReadOnly(True)
        ai_layout.addWidget(self.ai_output_text)

        self.tabs.addTab(ai_widget, "AI Assistant")

        self.statusBar()

    def create_menus(self):
        menu_bar = self.menuBar()

        # --- File Menu ---
        file_menu = menu_bar.addMenu("&File")

        open_action = QAction("&Open", self, triggered=self.open_file)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        file_menu.addAction(open_action)

        save_action = QAction("&Save", self, triggered=self.save_file)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self, triggered=self.save_file_as)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self, triggered=self.close)
        file_menu.addAction(exit_action)

        # --- Edit Menu ---
        edit_menu = menu_bar.addMenu("&Edit")

        find_action = QAction("&Find", self, triggered=self.toggle_search_bar)
        find_action.setShortcut(QKeySequence.StandardKey.Find)
        edit_menu.addAction(find_action)

        # --- View Menu ---
        view_menu = menu_bar.addMenu("&View")

        self.dark_mode_action = QAction("Toggle &Dark Mode", self, triggered=self.toggle_dark_mode, checkable=True)
        view_menu.addAction(self.dark_mode_action)

        font_size_menu = view_menu.addMenu("Font Size")
        increase_font_action = QAction("Increase", self, triggered=lambda: self.adjust_font_size(2))
        increase_font_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        decrease_font_action = QAction("Decrease", self, triggered=lambda: self.adjust_font_size(-2))
        decrease_font_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        font_size_menu.addAction(increase_font_action)
        font_size_menu.addAction(decrease_font_action)

        # --- Export Menu ---
        export_menu = menu_bar.addMenu("&Export")

        export_html_action = QAction("Export to &HTML", self, triggered=self.export_to_html)
        export_menu.addAction(export_html_action)

        export_pdf_action = QAction("Export to &PDF", self, triggered=self.export_to_pdf)
        export_menu.addAction(export_pdf_action)

        # --- AI Menu ---
        ai_menu = menu_bar.addMenu("&AI Tools")
        summarize_action = QAction("&Send Selection to AI Assistant", self, triggered=self.prepare_ai_tab)
        summarize_action.setShortcut("Ctrl+Shift A")
        ai_menu.addAction(summarize_action)

    def create_search_bar(self):
        layout = self.search_bar_widget.layout()

        layout.addWidget(QLabel("Find:"))
        self.search_input = QLineEdit()
        self.search_input.returnPressed.connect(self.search_text)
        layout.addWidget(self.search_input)

        search_button = QPushButton("Find Next")
        search_button.clicked.connect(self.search_text)
        layout.addWidget(search_button)

        close_search_button = QPushButton("Close")
        close_search_button.clicked.connect(self.toggle_search_bar)
        layout.addWidget(close_search_button)

    def load_styles(self):
        # Generate CSS for Pygments syntax highlighting (default theme)
        self.pygments_css = HtmlFormatter(style='default').get_style_defs('.codehilite')

        # Basic CSS for markdown elements
        self.base_css = """
            body { font-family: sans-serif; line-height: 1.6; padding: 20px; }
            h1, h2, h3, h4, h5, h6 { line-height: 1.2; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 8px; }
            th { background-color: #f2f2f2; }
            blockquote { border-left: 4px solid #ccc; padding-left: 10px; color: #666; }
            code { background-color: #f9f9f9; padding: 2px 4px; border-radius: 4px; }
            .codehilite { background: #f8f8f8; border: 1px solid #ccc; padding: 10px; border-radius: 4px; overflow-x: auto;}
            img { max-width: 100%; height: auto; }
        """

        self.dark_mode_css = """
            body { background-color: #2b2b2b; color: #dcdcdc; }
            h1, h2, h3, h4, h5, h6 { color: #ffffff; }
            table { border-color: #555; }
            th, td { border-color: #555; }
            th { background-color: #3a3a3a; }
            blockquote { border-left-color: #555; color: #aaa; }
            code { background-color: #3c3c3c; color: #dcdcdc; }
            a { color: #87ceeb; }
        """
        self.pygments_dark_css = HtmlFormatter(style='monokai').get_style_defs('.codehilite')

        self.current_css = self.base_css + self.pygments_css

        self.html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-g">
            <style>
                {css}
            </style>
        </head>
        <body>
            {content}
        </body>
        </html>
        """

    def on_text_changed(self):
        # Debounce the update
        self.update_timer.stop()
        self.update_timer.start(300)

    def update_preview(self, html_content=None):
        if html_content is None:
            markdown_text = self.editor.toPlainText()
            # Use a custom formatter for code blocks to integrate Pygments
            html_content = markdown2.markdown(
                markdown_text,
                extras=["fenced-code-blocks", "tables", "highlightjs-classes", "code-friendly"]
            )

        full_html = self.html_template.format(css=self.current_css, content=html_content)

        # To handle file paths for local images, we set a base URL
        base_url = QUrl.fromLocalFile(os.getcwd() + os.sep)
        if self.current_file_path:
            base_url = QUrl.fromLocalFile(os.path.dirname(self.current_file_path) + os.sep)

        self.preview.setHtml(full_html, baseUrl=base_url)

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Markdown File", "",
                                                   "Markdown Files (*.md *.mdown);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.editor.setPlainText(f.read())
                self.current_file_path = file_path
                self.setWindowTitle(f"Python Markdown Viewer - {os.path.basename(file_path)}")
                self.statusBar().showMessage(f"Opened {file_path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not open file: {e}")

    def save_file(self):
        if self.current_file_path:
            try:
                with open(self.current_file_path, 'w', encoding='utf-8') as f:
                    f.write(self.editor.toPlainText())
                self.statusBar().showMessage(f"Saved to {self.current_file_path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file: {e}")
        else:
            self.save_file_as()

    def save_file_as(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Markdown File", "",
                                                   "Markdown Files (*.md *.mdown);;All Files (*)")
        if file_path:
            self.current_file_path = file_path
            self.setWindowTitle(f"Python Markdown Viewer - {os.path.basename(file_path)}")
            self.save_file()

    def export_to_html(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to HTML", "", "HTML Files (*.html *.htm)")
        if file_path:
            try:
                markdown_text = self.editor.toPlainText()
                html_content = markdown2.markdown(markdown_text, extras=["fenced-code-blocks", "tables"])
                full_html = self.html_template.format(css=self.current_css, content=html_content)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(full_html)
                self.statusBar().showMessage(f"Exported to {file_path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not export HTML: {e}")

    def export_to_pdf(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to PDF", "", "PDF Files (*.pdf)")
        if not file_path:
            return

        def handle_pdf_creation(success):
            if success:
                self.statusBar().showMessage(f"Exported to {file_path}", 3000)
                QMessageBox.information(self, "Success", f"PDF successfully exported to {file_path}")
            else:
                self.statusBar().showMessage("PDF export failed.", 3000)
                QMessageBox.critical(self, "Error", "Could not export PDF.")
        try:
            self.preview.page().printToPdf(file_path)
            handle_pdf_creation(True)
        except:
            handle_pdf_creation(False)

    def toggle_search_bar(self):
        self.search_bar_widget.setVisible(not self.search_bar_widget.isVisible())
        if self.search_bar_widget.isVisible():
            self.search_input.setFocus()

    def search_text(self):
        query = self.search_input.text()
        if query:
            # Search in the editor, not the preview
            self.editor.find(query)

    def toggle_dark_mode(self):
        if self.dark_mode_action.isChecked():
            self.current_css = self.base_css + self.dark_mode_css + self.pygments_dark_css
            editor_style = "font-family: 'Courier New'; font-size: 14px; color: #dcdcdc; background-color: #2b2b2b;"
            ai_style = "color: #dcdcdc; background-color: #2b2b2b;"
        else:
            self.current_css = self.base_css + self.pygments_css
            editor_style = "font-family: 'Courier New'; font-size: 14px; color: #333; background-color: #fdfdfd;"
            ai_style = "color: #333; background-color: #fdfdfd;"

        self.editor.setStyleSheet(editor_style)
        self.ai_input_text.setStyleSheet(ai_style)
        self.ai_output_text.setStyleSheet(ai_style)
        self.update_preview()

    def adjust_font_size(self, delta):
        # This is a simple implementation using JS.
        js_code = f"document.body.style.fontSize = (parseInt(window.getComputedStyle(document.body).fontSize) + {delta}) + 'px';"
        self.preview.page().runJavaScript(js_code)

        # Adjust editor font size too
        font = self.editor.font()
        new_size = font.pointSize() + (delta // 2)
        if new_size > 4:  # Prevent font from getting too small
            font.setPointSize(new_size)
            self.editor.setFont(font)
            self.ai_input_text.setFont(font)
            self.ai_output_text.setFont(font)

    def get_api_key(self):
        if self.api_key_set and self.gemini_api_key:
            return True

        text, ok = QInputDialog.getText(self, 'Gemini API Key', 'Please enter your Google Gemini API key:')

        if ok and text:
            self.gemini_api_key = text
            self.api_key_set = True
            try:
                genai.configure(api_key=self.gemini_api_key)
                # Test the key with a simple request
                genai.get_model('models/gemini-2.5-flash')
                return True
            except Exception as e:
                QMessageBox.warning(self, "API Key Error",
                                    f"The API key seems to be invalid.\nPlease check it and try again.\nError: {e}")
                self.api_key_set = False
                self.gemini_api_key = None
                return False
        return False

    def prepare_ai_tab(self):
        selected_text = self.editor.textCursor().selectedText()
        if not selected_text:
            QMessageBox.information(self, "AI Tool", "Please select some text in the 'Editor' tab first.")
            return

        self.ai_input_text.setPlainText(selected_text)
        self.ai_output_text.clear()
        self.tabs.setCurrentIndex(2)  # Switch to the AI Assistant tab

    def run_ai_generation(self):
        content_to_analyze = self.ai_input_text.toPlainText()
        if not content_to_analyze:
            QMessageBox.information(self, "AI Tool",
                                    "There is no content to analyze. Please send some text from the editor first.")
            return

        if not self.get_api_key():
            return

        self.statusBar().showMessage("Sending request to Gemini AI...")
        self.ai_output_text.setPlaceholderText("Generating response...")
        QApplication.processEvents()  # Update UI

        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
            prompt = f"""
            Please act as a helpful assistant. Analyze the following text or code snippet and provide a concise explanation or summary.
            If it's code, explain what it does. If it's text, summarize its main points.

            Content to analyze:
            ---
            {content_to_analyze}
            ---
            """
            response = model.generate_content(prompt)

            self.statusBar().clearMessage()
            self.ai_output_text.setPlainText(response.text)

        except Exception as e:
            self.statusBar().clearMessage()
            self.ai_output_text.setPlaceholderText("An error occurred.")
            QMessageBox.critical(self, "AI Error", f"An error occurred while contacting the AI service: {e}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    viewer = MarkdownViewer()
    viewer.show()
    sys.exit(app.exec())

