import os
import re
import sys
import collections
from code import InteractiveInterpreter

from Qt import QtCore, QtWidgets, QtGui

from openpype.style import load_stylesheet


class StdOEWrap:
    def __init__(self):
        self._origin_stdout_write = None
        self._origin_stderr_write = None
        self._listening = False
        self.lines = collections.deque()

        if not sys.stdout:
            sys.stdout = open(os.devnull, "w")

        if not sys.stderr:
            sys.stderr = open(os.devnull, "w")

        if self._origin_stdout_write is None:
            self._origin_stdout_write = sys.stdout.write

        if self._origin_stderr_write is None:
            self._origin_stderr_write = sys.stderr.write

        self._listening = True
        sys.stdout.write = self._stdout_listener
        sys.stderr.write = self._stderr_listener

    def stop_listen(self):
        self._listening = False

    def _stdout_listener(self, text):
        if self._listening:
            self.lines.append(text)
        if self._origin_stdout_write is not None:
            self._origin_stdout_write(text)

    def _stderr_listener(self, text):
        if self._listening:
            self.lines.append(text)
        if self._origin_stderr_write is not None:
            self._origin_stderr_write(text)


class PythonCodeEditor(QtWidgets.QPlainTextEdit):
    execute_requested = QtCore.Signal()

    def __init__(self, parent):
        super(PythonCodeEditor, self).__init__(parent)

        self._indent = 4

    def _tab_shift_right(self):
        cursor = self.textCursor()
        selected_text = cursor.selectedText()
        if not selected_text:
            cursor.insertText(" " * self._indent)
            return

        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()
        cursor.setPosition(sel_end)
        end_line = cursor.blockNumber()
        cursor.setPosition(sel_start)
        while True:
            cursor.movePosition(QtGui.QTextCursor.StartOfLine)
            text = cursor.block().text()
            spaces = len(text) - len(text.lstrip(" "))
            new_spaces = spaces % self._indent
            if not new_spaces:
                new_spaces = self._indent

            cursor.insertText(" " * new_spaces)
            if cursor.blockNumber() == end_line:
                break

            cursor.movePosition(QtGui.QTextCursor.NextBlock)

    def _tab_shift_left(self):
        tmp_cursor = self.textCursor()
        sel_start = tmp_cursor.selectionStart()
        sel_end = tmp_cursor.selectionEnd()

        cursor = QtGui.QTextCursor(self.document())
        cursor.setPosition(sel_end)
        end_line = cursor.blockNumber()
        cursor.setPosition(sel_start)
        while True:
            cursor.movePosition(QtGui.QTextCursor.StartOfLine)
            text = cursor.block().text()
            spaces = len(text) - len(text.lstrip(" "))
            if spaces:
                spaces_to_remove = (spaces % self._indent) or self._indent
                if spaces_to_remove > spaces:
                    spaces_to_remove = spaces

                cursor.setPosition(
                    cursor.position() + spaces_to_remove,
                    QtGui.QTextCursor.KeepAnchor
                )
                cursor.removeSelectedText()

            if cursor.blockNumber() == end_line:
                break

            cursor.movePosition(QtGui.QTextCursor.NextBlock)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Backtab:
            self._tab_shift_left()
            event.accept()
            return

        if event.key() == QtCore.Qt.Key_Tab:
            if event.modifiers() == QtCore.Qt.NoModifier:
                self._tab_shift_right()
            event.accept()
            return

        if (
            event.key() == QtCore.Qt.Key_Return
            and event.modifiers() == QtCore.Qt.ControlModifier
        ):
            self.execute_requested.emit()
            event.accept()
            return

        super(PythonCodeEditor, self).keyPressEvent(event)


class PythonTabWidget(QtWidgets.QWidget):
    before_execute = QtCore.Signal(str)

    def __init__(self, parent):
        super(PythonTabWidget, self).__init__(parent)

        code_input = PythonCodeEditor(self)

        execute_btn = QtWidgets.QPushButton("Execute", self)
        execute_btn.setToolTip("Execute command (Ctrl + Enter)")

        btns_layout = QtWidgets.QHBoxLayout()
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.addStretch(1)
        btns_layout.addWidget(execute_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(code_input, 1)
        layout.addLayout(btns_layout, 0)

        execute_btn.clicked.connect(self._on_execute_clicked)
        code_input.execute_requested.connect(self.execute)

        self._code_input = code_input
        self._interpreter = InteractiveInterpreter()

    def _on_execute_clicked(self):
        self.execute()

    def execute(self):
        code_text = self._code_input.toPlainText()
        self.before_execute.emit(code_text)
        self._interpreter.runcode(code_text)


class TabNameDialog(QtWidgets.QDialog):
    def __init__(self, parent):
        super(TabNameDialog, self).__init__(parent)

        self.setWindowTitle("Enter tab name")

        name_label = QtWidgets.QLabel("Tab name:", self)
        name_input = QtWidgets.QLineEdit(self)

        inputs_layout = QtWidgets.QHBoxLayout()
        inputs_layout.addWidget(name_label)
        inputs_layout.addWidget(name_input)

        ok_btn = QtWidgets.QPushButton("Ok", self)
        cancel_btn = QtWidgets.QPushButton("Cancel", self)
        btns_layout = QtWidgets.QHBoxLayout()
        btns_layout.addStretch(1)
        btns_layout.addWidget(ok_btn)
        btns_layout.addWidget(cancel_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(inputs_layout)
        layout.addStretch(1)
        layout.addLayout(btns_layout)

        ok_btn.clicked.connect(self._on_ok_clicked)
        cancel_btn.clicked.connect(self._on_cancel_clicked)

        self._name_input = name_input
        self._ok_btn = ok_btn
        self._cancel_btn = cancel_btn

        self._result = None

    def set_tab_name(self, name):
        self._name_input.setText(name)

    def result(self):
        return self._result

    def showEvent(self, event):
        super(TabNameDialog, self).showEvent(event)
        btns_width = max(
            self._ok_btn.width(),
            self._cancel_btn.width()
        )

        self._ok_btn.setMinimumWidth(btns_width)
        self._cancel_btn.setMinimumWidth(btns_width)

    def _on_ok_clicked(self):
        self._result = self._name_input.text()
        self.accept()

    def _on_cancel_clicked(self):
        self._result = None
        self.reject()


class PythonInterpreterWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(PythonInterpreterWidget, self).__init__(parent)

        self.ansi_escape = re.compile(
            r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]"
        )

        self._tabs = []

        self._stdout_err_wrapper = StdOEWrap()

        output_widget = QtWidgets.QTextEdit(self)
        output_widget.setObjectName("PythonInterpreterOutput")
        output_widget.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        output_widget.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)

        tab_widget = QtWidgets.QTabWidget(self)
        tab_widget.setTabsClosable(False)
        tab_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

        add_tab_btn = QtWidgets.QPushButton("+", tab_widget)
        tab_widget.setCornerWidget(add_tab_btn, QtCore.Qt.TopLeftCorner)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(output_widget)
        layout.addWidget(tab_widget)

        timer = QtCore.QTimer()
        timer.setInterval(200)
        timer.start()

        timer.timeout.connect(self._on_timer_timeout)
        add_tab_btn.clicked.connect(self._on_add_clicked)
        tab_widget.customContextMenuRequested.connect(
            self._on_tab_context_menu
        )
        tab_widget.tabCloseRequested.connect(self._on_tab_close_req)

        self._add_tab_btn = add_tab_btn
        self._output_widget = output_widget
        self._tab_widget = tab_widget
        self._timer = timer

        self.setStyleSheet(load_stylesheet())

        self.add_tab("Python")

    def _on_tab_context_menu(self, point):
        tab_bar = self._tab_widget.tabBar()
        tab_idx = tab_bar.tabAt(point)
        last_index = tab_bar.count() - 1
        if tab_idx < 0 or tab_idx > last_index:
            return

        menu = QtWidgets.QMenu(self._tab_widget)
        menu.addAction("Rename")
        global_point = self._tab_widget.mapToGlobal(point)
        result = menu.exec_(global_point)
        if result is None:
            return

        if result.text() == "Rename":
            dialog = TabNameDialog(self)
            dialog.set_tab_name(self._tab_widget.tabText(tab_idx))
            dialog.exec_()
            tab_name = dialog.result()
            if tab_name:
                self._tab_widget.setTabText(tab_idx, tab_name)

    def _on_tab_close_req(self, tab_index):
        widget = self._tab_widget.widget(tab_index)
        if widget in self._tabs:
            self._tabs.remove(widget)
        self._tab_widget.removeTab(tab_index)

        if self._tab_widget.count() == 1:
            self._tab_widget.setTabsClosable(False)

    def _on_timer_timeout(self):
        if self._stdout_err_wrapper.lines:
            tmp_cursor = QtGui.QTextCursor(self._output_widget.document())
            tmp_cursor.movePosition(QtGui.QTextCursor.End)
            while self._stdout_err_wrapper.lines:
                line = self._stdout_err_wrapper.lines.popleft()

                tmp_cursor.insertText(self.ansi_escape.sub("", line))

    def _on_add_clicked(self):
        dialog = TabNameDialog(self)
        dialog.exec_()
        tab_name = dialog.result()
        if tab_name:
            self.add_tab(tab_name)

    def _on_before_execute(self, code_text):
        document = self._output_widget.document()
        tmp_cursor = QtGui.QTextCursor(document)
        tmp_cursor.movePosition(QtGui.QTextCursor.End)
        tmp_cursor.insertText("{}\nExecuting command:\n".format(20 * "-"))

        code_block_format = QtGui.QTextFrameFormat()
        code_block_format.setBackground(QtGui.QColor(27, 27, 27))
        code_block_format.setPadding(4)

        tmp_cursor.insertFrame(code_block_format)
        char_format = tmp_cursor.charFormat()
        char_format.setForeground(
            QtGui.QBrush(QtGui.QColor(114, 224, 198))
        )
        tmp_cursor.setCharFormat(char_format)
        tmp_cursor.insertText(code_text)

        # Create new cursor
        tmp_cursor = QtGui.QTextCursor(document)
        tmp_cursor.movePosition(QtGui.QTextCursor.End)
        tmp_cursor.insertText("{}\n".format(20 * "-"))

    def add_tab(self, tab_name, index=None):
        widget = PythonTabWidget(self)
        widget.before_execute.connect(self._on_before_execute)
        if index is None:
            if self._tab_widget.count() > 1:
                index = self._tab_widget.currentIndex() + 1
            else:
                index = 0

        self._tabs.append(widget)
        self._tab_widget.insertTab(index, widget, tab_name)
        self._tab_widget.setCurrentIndex(index)

        if self._tab_widget.count() > 1:
            self._tab_widget.setTabsClosable(True)
