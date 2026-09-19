"""Real local barcode worker in Chromium/WebKit; external requests and OCR mocked."""
import io
from pathlib import Path
import socket
import tempfile
import threading
import time
from unittest.mock import patch

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright, expect
import uvicorn
from mobile_backend.config import Settings
from mobile_backend.server import create_app
from mobile_backend.lobid import ProviderError

PASSWORD='test-only-recognition-password'


def barcode():
    # Fixed standard EAN-13 modules for 9780306406157, independent of decoder.
    bits='10101110110001001010011101111010100111010111101010101110011100101010000110011010011101000100101'
    image=Image.new('RGB',(600,300),'white');draw=ImageDraw.Draw(image)
    for index,bit in enumerate(bits):
        if bit=='1':draw.rectangle((60+index*5,40,64+index*5,260),fill='black')
    data=io.BytesIO();image.save(data,format='PNG');return data.getvalue()


def main():
    with tempfile.TemporaryDirectory() as tmp, patch('mobile_backend.lobid.lookup') as lookup, patch('mobile_backend.ocr.recognize_isbns',return_value=['9780804429573']) as ocr:
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        origin=f'http://127.0.0.1:{port}'
        app=create_app(Settings(password=PASSWORD,origin=origin,secure_cookie=False,database=Path(tmp)/'test.sqlite3'))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='warning'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        try:
            with sync_playwright() as p:
                for engine in ('chromium','webkit'):
                    with app.state.store.connect() as db:db.execute('DELETE FROM metadata_cache')
                    lookup.side_effect=None
                    lookup.return_value=[dict(title='Testbuch – Müller',subtitle='Eine Prüfung',authors=['Müller, Anne'],editors=['Goethe'],publisher='Testverlag',publication_year=2026,
                                              isbn13='9780306406157',source_url='https://lobid.org/resources/TEST',fetched_at='2026-09-19T00:00:00Z')]
                    ocr.reset_mock()
                    browser=getattr(p,engine).launch()
                    context=browser.new_context(**p.devices['iPhone 13'])
                    page=context.new_page();errors=[];uploads=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('dialog',lambda dialog:dialog.accept())
                    page.on('request',lambda r:uploads.append(r.url) if r.method=='POST' and '/api/isbn/ocr' in r.url else None)
                    page.goto(origin);page.locator('#password').fill(PASSWORD);page.locator('#loginForm button').click()
                    expect(page.locator('#loginPanel')).to_be_hidden()
                    page.locator('#projectName').fill('Erkennung '+engine);page.locator('#projectForm button').click()
                    expect(page.locator('#status')).to_have_text('Projekt angelegt.')
                    project=page.locator('#projects').input_value()
                    page.locator('#file').set_input_files({'name':'barcode.png','mimeType':'image/png','buffer':barcode()})
                    expect(page.locator('#editorPanel')).to_be_visible()
                    page.locator('#recognize').click()
                    expect(page.locator('#bookIsbn')).to_have_value('9780306406157',timeout=15000)
                    ocr.assert_not_called();assert not uploads,'Barcode triggered OCR upload'
                    page.locator('#lookup').click()
                    expect(page.locator('#matches button')).to_have_count(1)
                    page.locator('#matches button').click()
                    expect(page.locator('#book_title')).to_have_value('Testbuch – Müller')
                    page.locator('#confirmBook').click()
                    expect(page.locator('#status')).to_have_text('Buch gespeichert.')
                    rows=app.state.store.books(project)
                    assert len(rows)==1 and rows[0]['status']=='confirmed'
                    assert app.state.store.captures(project)==[], 'Recognition persisted private photo without consent'
                    # New blank crop -> OCR fallback; verify cropped dimensions only.
                    blank=Image.new('RGB',(800,600),'white');buf=io.BytesIO();blank.save(buf,format='PNG')
                    page.locator('#file').set_input_files({'name':'isbn.png','mimeType':'image/png','buffer':buf.getvalue()})
                    expect(page.locator('#cropSize')).to_contain_text('800 × 600')
                    for key,value in [('cropW','50'),('cropH','50')]:
                        page.locator('#'+key).fill(value);page.locator('#'+key).dispatch_event('change')
                    page.locator('#recognize').click()
                    expect(page.locator('#bookIsbn')).to_have_value('9780804429573',timeout=15000)
                    assert len(uploads)==1
                    received=Image.open(io.BytesIO(ocr.call_args.args[0]))
                    assert received.size==(400,300), received.size
                    lookup.side_effect=ProviderError('offline')
                    page.locator('#lookup').click()
                    expect(page.locator('#reviewInfo')).to_contain_text('nicht verfügbar')
                    page.locator('#draftBook').click()
                    expect(page.locator('#status')).to_have_text('Buch gespeichert (Entwurf).')
                    rows=app.state.store.books(project)
                    assert len(rows)==2 and any(x['isbn13']=='9780804429573' and x['status']=='draft' for x in rows)
                    page.locator('#reviewPanel').screenshot(path=f'test-results/mobile/{engine}-recognition.png')
                    page.reload();expect(page.locator('#books article')).to_have_count(2)
                    assert not errors,errors
                    browser.close()
                    print(engine+': PASS — real barcode, no OCR on success, cropped OCR fallback, lookup review, offline ISBN draft, reload')
        finally:
            server.should_exit=True;thread.join(timeout=10);sock.close()


if __name__=='__main__':main()
