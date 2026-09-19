from qt.core import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,
                     QHeaderView,QAbstractItemView,QComboBox,QCheckBox,QPushButton,QInputDialog,Qt)


class ImportDialog(QDialog):
    def __init__(self,rows,parent=None):
        super().__init__(parent);self.rows=rows;self.plans=[]
        self.setWindowTitle('Calibre-Importvorschau');self.resize(1120,650)
        layout=QVBoxLayout(self)
        note=QLabel('Es werden nur angehakte Zeilen verarbeitet. Treffer mit vorhandener ISBN werden standardmäßig übersprungen. '
                    'Eine Aktualisierung muss je Datensatz ausdrücklich gewählt werden; leere Projektfelder überschreiben keine Calibre-Werte.')
        note.setWordWrap(True);layout.addWidget(note)
        self.table=QTableWidget(len(rows),7)
        self.table.setHorizontalHeaderLabels(['Importieren','Titel','Autor(en)','ISBN','Status','Vorhandene Calibre-IDs','Aktion'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table,1)
        self.actions=[]
        for row,data in enumerate(rows):
            choose=QTableWidgetItem();choose.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable)
            choose.setCheckState(Qt.CheckState.Checked if not data['duplicates'] and data['status'] in ('matched','manual_confirmed') else Qt.CheckState.Unchecked)
            self.table.setItem(row,0,choose)
            for column,key in enumerate(('title','author','isbn','status'),1):
                self.table.setItem(row,column,QTableWidgetItem(str(data.get(key) or '')))
            self.table.setItem(row,5,QTableWidgetItem(', '.join(map(str,data['duplicates']))))
            action=QComboBox()
            if data['duplicates']:
                action.addItem('Überspringen',('skip',None))
                for book_id in data['duplicates']:action.addItem('Vorhandenen Datensatz '+str(book_id)+' aktualisieren',('update',book_id))
            else:action.addItem('Neuen Calibre-Datensatz anlegen',('create',None))
            action.addItem('Andere Calibre-ID zuordnen und aktualisieren …',('manual_update',None))
            self.actions.append(action);self.table.setCellWidget(row,6,action)
        self.cover=QCheckBox('Verfügbares Online-Cover herunterladen und übernehmen (zusätzliche Netzwerkübertragung)')
        layout.addWidget(self.cover)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        start=QPushButton('Auswahl verbindlich importieren');start.clicked.connect(self.accept);buttons.addWidget(start)
        cancel=QPushButton('Abbrechen');cancel.clicked.connect(self.reject);buttons.addWidget(cancel);buttons.addStretch()

    def accept(self):
        plans=[]
        for row,data in enumerate(self.rows):
            if self.table.item(row,0).checkState()!=Qt.CheckState.Checked:continue
            action,calibre_id=self.actions[row].currentData()
            if action=='skip':continue
            if action=='manual_update':
                calibre_id,ok=QInputDialog.getInt(self,'Calibre-Datensatz zuordnen',
                      'Vorhandene numerische Calibre-ID:',min=1,max=2147483647)
                if not ok:return
                action='update'
            plans.append({'book_id':data['book_id'],'action':action,'calibre_book_id':calibre_id})
        if not plans:return
        self.plans=plans
        super().accept()
