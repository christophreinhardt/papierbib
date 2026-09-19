"""Exercise the built Compose container with fake credentials on loopback only."""
import io
import subprocess
import time
import httpx
from PIL import Image, ImageDraw, ImageFont
from uuid import uuid4

def wait_ready(client):
    for _ in range(60):
        try:
            if client.get('/api/health').status_code==200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(.5)
    raise RuntimeError('Testcontainer wird nicht bereit.')

def main():
    with httpx.Client(base_url='http://127.0.0.1:18888',timeout=10) as client:
        wait_ready(client)
        assert client.get('/api/health').json()['version']=='0.4.0'
        assert client.get('/').status_code==200
        headers={'Origin':'https://papierbib.test','X-Papierbib':'1'}
        login=client.post('/api/login',headers=headers,json={'password':'only-for-isolated-container-test'})
        assert login.status_code==200,login.text
        # Simulate the HTTPS terminator forwarding this private cookie over loopback.
        headers['Cookie']='papierbib_session='+login.cookies['papierbib_session']
        project=client.post('/api/projects',headers=headers,json={'name':'Container-Test'}).json()['project_id']
        data=io.BytesIO();Image.new('RGB',(160,120),'white').save(data,format='PNG')
        result=client.post(f'/api/projects/{project}/captures?kind=isbn&store_images=true',
                           headers=headers,content=data.getvalue())
        assert result.status_code==201,result.text
        photo=result.json()['photo_id']
        assert client.get(f'/api/captures/{photo}/original',headers=headers).content==data.getvalue()
        # Actual Tesseract in the image, not mocked; synthetic digits only.
        text=Image.new('RGB',(1600,220),'white')
        ImageDraw.Draw(text).text((40,65),'ISBN 978-0-306-40615-7',font=ImageFont.load_default(size=72),fill='black')
        buf=io.BytesIO();text.save(buf,format='PNG')
        recognized=client.post('/api/isbn/ocr?crop_confirmed=true',headers=headers,content=buf.getvalue(),timeout=30)
        assert recognized.status_code==200,recognized.text
        assert recognized.json()['isbns']==['9780306406157'],recognized.text
        saved=client.post(f'/api/projects/{project}/books',headers=headers,json=dict(book_id=str(uuid4()),isbn13='9780306406157',status='draft'))
        assert saved.status_code==200,saved.text
        subprocess.run(['docker','restart','papierbib-phase1-test'],check=True,capture_output=True)
        wait_ready(client)
        assert client.get(f'/api/captures/{photo}/original',headers=headers).content==data.getvalue()
        assert len(client.get(f'/api/projects/{project}/books',headers=headers).json())==1
        assert client.get('/api/captures/'+photo+'/original').status_code==401
        print('PASS: Compose container, real ISBN OCR, draft, non-root volume writes, crop, original, restart persistence and authentication')

if __name__=='__main__':
    main()
