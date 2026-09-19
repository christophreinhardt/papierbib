"""Real Chromium + WebKit flows at an iPhone viewport, using synthetic images only.
Run from repository root: python -m mobile_backend.tests.browser_smoke
"""
import io
from pathlib import Path
import socket
import tempfile
import threading
import time

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright, expect
import uvicorn
from mobile_backend.config import Settings
from mobile_backend.server import create_app

PASSWORD = 'test-only-browser-password'

def main():
    with tempfile.TemporaryDirectory() as tmp:
        sock=socket.socket()
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
        origin=f'http://127.0.0.1:{port}'
        app=create_app(Settings(password=PASSWORD,origin=origin,secure_cookie=False,
                                database=Path(tmp)/'browser.sqlite3'))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='warning'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        if not server.started:raise RuntimeError('Testserver startet nicht.')
        photo=Image.new('RGB',(640,480),'#f4edcf')
        draw=ImageDraw.Draw(photo)
        draw.rectangle((40,40,600,440),outline='black',width=8)
        draw.text((100,150),'TESTBUCH / ISBN 9780306406157',fill='black')
        data=io.BytesIO();photo.save(data,format='JPEG')
        out=Path('test-results/mobile');out.mkdir(parents=True,exist_ok=True)
        try:
            with sync_playwright() as p:
                for engine in ('chromium','webkit'):
                    browser=getattr(p,engine).launch(headless=True)
                    context=browser.new_context(**p.devices['iPhone 13'],service_workers='allow')
                    page=context.new_page()
                    errors=[];uploads=[]
                    page.on('pageerror',lambda e: errors.append(str(e)))
                    page.on('request',lambda r: uploads.append(r.url) if r.method=='POST' and '/captures?' in r.url else None)
                    page.goto(origin)
                    page.locator('#password').fill(PASSWORD)
                    page.locator('#loginForm button').click()
                    expect(page.locator('#loginPanel')).to_be_hidden()
                    assert 'papierbib_session' not in page.evaluate('document.cookie')
                    page.locator('#projectName').fill('Browsertest '+engine)
                    page.locator('#projectForm button').click()
                    expect(page.locator('#status')).to_have_text('Projekt angelegt.')
                    page.locator('#file').set_input_files({'name':'test.jpg','mimeType':'image/jpeg','buffer':data.getvalue()})
                    expect(page.locator('#editorPanel')).to_be_visible()
                    assert not uploads, 'Foto vor Zustimmung hochgeladen'
                    page.locator('#rotateRight').click()
                    expect(page.locator('#cropSize')).to_contain_text('Drehung 90')
                    page.locator('#rotation').fill('17.5')
                    page.locator('#rotation').dispatch_event('input')
                    expect(page.locator('#cropSize')).to_contain_text('Drehung 17.5')
                    page.locator('#rotateRight').click()
                    expect(page.locator('#cropSize')).to_contain_text('Drehung 107.5')
                    page.locator('#rotation').fill('90')
                    page.locator('#rotation').dispatch_event('input')
                    expect(page.locator('#cropSize')).to_contain_text('Drehung 90')
                    # Browser-generated pointer events test corner resizing in CSS coordinates.
                    canvas=page.locator('#editor')
                    canvas.scroll_into_view_if_needed()
                    bounds=canvas.bounding_box()
                    x,y=bounds['x'],bounds['y']
                    page.mouse.move(x+1,y+1)
                    page.mouse.down()
                    page.mouse.move(x+bounds['width']*.1,y+bounds['height']*.1,steps=6)
                    page.mouse.up()
                    assert float(page.locator('#cropX').input_value()) > 0
                    # Accessible exact geometry controls also work without gestures.
                    for id,value in [('cropW','70'),('cropH','60'),('cropX','10'),('cropY','10')]:
                        page.locator('#'+id).fill(value)
                        page.locator('#'+id).dispatch_event('change')
                    page.locator('#zoom').fill('1.5')
                    page.locator('#zoom').dispatch_event('input')
                    page.locator('#save').click()
                    expect(page.locator('#status')).to_contain_text('Zum Übertragen bitte')
                    assert not uploads
                    page.locator('#persist').check()
                    page.locator('#save').click()
                    expect(page.locator('#status')).to_contain_text('Gespeichert.',timeout=15000)
                    assert len(uploads)==1
                    project=page.locator('#projects').input_value()
                    rows=app.state.store.captures(project)
                    assert len(rows)==1
                    assert rows[0]['crops'][0]['width']==336
                    assert rows[0]['crops'][0]['height']==384, rows[0]['crops'][0]
                    original=app.state.store.original(rows[0]['photo_id'])[0]
                    assert original==data.getvalue()
                    page.locator('#gallery button').first.click()
                    expect(page.locator('#status')).to_contain_text('Original geöffnet')
                    page.locator('#reset').click()
                    page.locator('#persist').check()
                    page.locator('#save').click()
                    expect(page.locator('#status')).to_contain_text('Gespeichert.',timeout=15000)
                    assert len(app.state.store.captures(project)[0]['crops'])==2
                    page.screenshot(path=str(out/(engine+'-iphone.png')),full_page=True)
                    page.reload()
                    expect(page.locator('#loginPanel')).to_be_hidden()
                    expect(page.locator('#gallery img')).to_have_count(1)
                    page.wait_for_function('navigator.serviceWorker.controller !== null')
                    cached=page.evaluate('(async()=>{let out=[];for(const k of await caches.keys())for(const r of await (await caches.open(k)).keys())out.push(r.url);return out})()')
                    assert not any('/api/' in url for url in cached)
                    if engine=='chromium':
                        context.set_offline(True)
                    else:
                        # WebKit on Windows errors internally on set_offline + reload.
                        # Stop the real origin instead to test an unavailable server.
                        server.should_exit=True
                        thread.join(timeout=10)
                        sock.close()
                    page.reload()
                    expect(page.locator('#offline')).to_be_visible()
                    page.locator('#file').set_input_files({'name':'offline.jpg','mimeType':'image/jpeg','buffer':data.getvalue()})
                    expect(page.locator('#editorPanel')).to_be_visible()
                    assert not errors, errors
                    context.set_offline(False)
                    context.close();browser.close()
                    print(engine+': PASS — login, crop, consent, revisions, reload, offline shell')
        finally:
            server.should_exit=True
            thread.join(timeout=10)
            sock.close()

if __name__=='__main__':
    main()
