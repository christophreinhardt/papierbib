from copy import deepcopy

from qt.core import (QDialog,QVBoxLayout,QHBoxLayout,QTableWidget,QTableWidgetItem,
                     QHeaderView,QLabel,QPushButton,QMessageBox,Qt)

from ..metadata_providers.matching import apply_match
from ..metadata_providers.base import ProviderError


class MetadataDialog(QDialog):
    def __init__(self,book,parent=None):
        super().__init__(parent); self.book=deepcopy(book)
        self.setWindowTitle('Online-Treffer vergleichen'); self.resize(1100,620)
        layout=QVBoxLayout(self)
        note=QLabel('Online-Treffer sind Vorschläge. Erst „Ausgewählten Treffer übernehmen“ ändert Metadaten.\n'
                    'Widersprüche werden nicht automatisch übernommen. Quellen und Abrufzeitpunkte bleiben gespeichert.')
        note.setWordWrap(True); layout.addWidget(note)
        self.table=QTableWidget(0,8)
        self.table.setHorizontalHeaderLabels(['Bewertung','Titel','Autor(en)','Verlag','Jahr','ISBN','Quellen','Konflikte'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table,1)
        for match in book.provider_matches:
            if not isinstance(match,dict) or 'fields' not in match:continue
            row=self.table.rowCount();self.table.insertRow(row); f=match['fields']
            values=(f"{match.get('score',0):.0%}",f.get('title'),f.get('author'),f.get('publisher'),f.get('publication_year'),
                    f.get('isbn13') or f.get('isbn10'),' + '.join(x.get('provider','') for x in match.get('sources',[])),
                    ', '.join(match.get('conflicts',[])))
            for column,value in enumerate(values):
                item=QTableWidgetItem(str(value or '')); item.setData(Qt.ItemDataRole.UserRole,match); self.table.setItem(row,column,item)
            if match.get('conflicts'):
                for column in range(8):self.table.item(row,column).setBackground(Qt.GlobalColor.yellow)
        if self.table.rowCount():self.table.selectRow(0)
        row=QHBoxLayout();layout.addLayout(row)
        use=QPushButton('Ausgewählten Treffer übernehmen');use.clicked.connect(self.accept_match);row.addWidget(use)
        later=QPushButton('Später prüfen');later.clicked.connect(self.reject);row.addWidget(later);row.addStretch()

    def accept_match(self):
        row=self.table.currentRow();item=self.table.item(row,0)
        if not item:
            QMessageBox.warning(self,'Treffer wählen','Bitte einen Treffer auswählen.');return
        match=item.data(Qt.ItemDataRole.UserRole)
        if match.get('conflicts'):
            QMessageBox.warning(self,'Widerspruch','Dieser zusammengeführte Treffer enthält widersprüchliche Felder. Bitte eine andere Ausgabe wählen oder manuell erfassen.');return
        if QMessageBox.question(self,'Metadaten übernehmen','Titel, Autor, Verlag, Jahr, Sprache und ISBN dieses Treffers übernehmen?') != QMessageBox.StandardButton.Yes:return
        try:self.book=apply_match(self.book,match)
        except ProviderError as exc:QMessageBox.warning(self,'Treffer prüfen',str(exc));return
        super().accept()
