from calibre.gui2.actions import InterfaceAction


class PapierbibliothekAction(InterfaceAction):
    name = 'Papierbibliothek'
    action_spec = ('Papierbibliothek', 'books.png', 'Regalfotos und Papierbücher erfassen', None)
    action_type = 'global'
    dont_add_to = frozenset(['context-menu-device'])

    def genesis(self):
        self.dialog = None
        self.qaction.triggered.connect(self.show_dialog)

    def show_dialog(self):
        from ..ui.main import MainDialog
        if self.dialog is None:
            self.dialog = MainDialog(self.gui, auto_open=True)
        elif self.dialog.project is None:
            self.dialog.open_last_project()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
