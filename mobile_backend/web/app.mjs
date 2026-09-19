import {CropEditor, fullBox} from './crop.mjs';
import {Recognition} from './recognition.mjs';
import {BarcodeScanner} from './scanner.mjs';
const $=id=>document.getElementById(id);
const state={blob:null,url:null,photoId:null,cropId:null,stream:null,dirty:false,busy:false,project:'',scanEpoch:0,shutterTimer:null};
const liveScanner=new BarcodeScanner();
function message(text,error=false){$('status').textContent=text;$('status').classList.toggle('error',error);}
function network(){ $('offline').hidden=navigator.onLine; }
async function api(path,{method='GET',body,headers={},timeout=45000}={}){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
  try{
    const response=await fetch(path,{method,body,headers:{'X-Papierbib':'1',...headers},credentials:'same-origin',signal:controller.signal});
    if(!response.ok){
      if(response.status===401){$('loginPanel').hidden=false;$('logout').hidden=true;}
      const data=await response.json().catch(()=>({}));
      const error=new Error(data.detail || 'Anfrage fehlgeschlagen ('+response.status+').');
      error.httpStatus=response.status;throw error;
    }
    return response;
  }catch(error){
    if(error.name==='AbortError')throw new Error('Zeitlimit erreicht. Vor erneutem Speichern bitte die Fotoliste prüfen.');
    if(error instanceof TypeError){
      $('offline').hidden=false;
      throw new Error('Homeserver nicht erreichbar. Die Aufnahme bleibt in diesem Tab.');
    }
    throw error;
  }finally{clearTimeout(timer);}
}
const json=(path,data)=>api(path,{method:'POST',body:JSON.stringify(data),headers:{'Content-Type':'application/json'}});
function action(id,fn,event='click'){
  $(id).addEventListener(event,async e=>{
    e.preventDefault();
    if(state.busy)return;
    try{await fn(e);}catch(error){message(error.message,true);}
  });
}
function mayReplace(){return (!state.dirty || confirm('Die ungespeicherte Aufnahme bzw. Änderung verwerfen?'))&&recognition.mayReplace();}
function stopCamera(){
  state.scanEpoch++;liveScanner.stop();
  clearTimeout(state.shutterTimer);state.shutterTimer=null;
  state.stream?.getTracks().forEach(t=>t.stop());state.stream=null;
  $('video').srcObject=null;$('cameraFrame').hidden=true;$('shoot').hidden=true;$('shoot').disabled=true;
  $('stop').disabled=true;$('camera').disabled=false;
}
async function camera(){
  if(!recognition.mayReplace())return;
  if(!navigator.mediaDevices?.getUserMedia)throw new Error('Die Kamera benötigt Safari und HTTPS. Alternativ „iPhone-Kamera / Foto“ verwenden.');
  stopCamera();
  state.stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'environment'},width:{ideal:4096},height:{ideal:3072}}});
  const track=state.stream.getVideoTracks()[0],caps=track.getCapabilities?.();
  if(caps?.width?.max && caps?.height?.max){
    try{await track.applyConstraints({width:{ideal:caps.width.max},height:{ideal:caps.height.max}});}catch{}
  }
  $('video').srcObject=state.stream;$('cameraFrame').hidden=false;
  try{await $('video').play();}catch(error){stopCamera();throw error;}
  $('shoot').disabled=false;$('stop').disabled=false;$('camera').disabled=true;
  const settings=track.getSettings();
  $('resolution').textContent='Live-Kamera: '+(settings.width||'?')+' × '+(settings.height||'?')+' Pixel. Native Fotoaufnahme über „iPhone-Kamera / Foto“.';
  if($('kind').value==='isbn'){
    $('shoot').hidden=true;$('scanHint').hidden=false;$('scanHint').textContent='Barcode wird lokal gesucht …';
    const epoch=state.scanEpoch;
    state.shutterTimer=setTimeout(()=>{
      if(state.stream&&state.scanEpoch===epoch){$('shoot').hidden=false;$('scanHint').textContent='Kein Barcode gefunden – jetzt fotografieren oder weiter scannen.';}
    },6000);
    scanLive(epoch);
  }else{
    $('shoot').hidden=false;$('scanHint').hidden=true;
  }
}
async function autoCamera(){
  if(state.stream||!$('loginPanel').hidden)return;
  try{await camera();}
  catch(error){message('Kamera nicht automatisch gestartet. Bitte „Kamera starten“ berühren.',false);}
}
async function scanLive(epoch){
  if(epoch!==state.scanEpoch||!state.stream||$('kind').value!=='isbn')return;
  try{
    $('resolution').textContent='Barcode-Suche läuft lokal in der Live-Kamera …';
    const isbn=state.busy?null:await liveScanner.decode($('video'));
    if(epoch!==state.scanEpoch)return;
    if(isbn){
      stopCamera();state.busy=true;recognition.busy=true;$('reviewPanel').inert=true;
      try{await recognition.accept(isbn,true);}finally{state.busy=false;recognition.busy=false;$('reviewPanel').inert=false;}
      return;
    }
  }catch(error){
    // A single bad camera frame must never disable continuous scanning.
    message('Barcode in diesem Kamerabild nicht lesbar – Suche läuft weiter.',false);
  }
  setTimeout(()=>scanLive(epoch),300);
}
const editor=new CropEditor($('editor'),$('cropPreview'),(spec,size)=>{
  for(const [id,key] of [['cropX','x'],['cropY','y'],['cropW','width'],['cropH','height']])$(id).value=(spec[key]*100).toFixed(1);
  $('cropSize').textContent='Zuschnitt ca. '+size.width+' × '+size.height+' Pixel · Drehung '+spec.rotation+'°';
  $('rotation').value=spec.rotation;$('rotationValue').textContent=spec.rotation+'°';
  state.dirty=true;
  state.cropId=null;
});
const recognition=new Recognition({api,json,notify:message,project:()=>state.project,
  crop:()=>editor.capture(),context:()=>({photo_id:state.photoId,crop_id:state.cropId}),stopCamera,
  lock:value=>{state.busy=value;$('editorPanel').inert=value;},isLocked:()=>state.busy,kind:()=>$('kind').value,
  onNewBook:async()=>{discard();await autoCamera();}
});
async function loadBlob(blob,photoId=null,spec={rotation:0,...fullBox()}){
  if(blob.size>20*1024*1024)throw new Error('Bitte ein Foto bis 20 MiB wählen.');
  if(!['image/jpeg','image/png','image/webp'].includes(blob.type))throw new Error('Bitte JPEG, PNG oder WebP wählen. HEIC vorher als JPEG exportieren.');
  const url=URL.createObjectURL(blob),img=new Image();img.src=url;
  try{await img.decode();}catch{URL.revokeObjectURL(url);throw new Error('Dieses Foto kann der Browser nicht öffnen. Bitte JPEG verwenden.');}
  if(img.naturalWidth*img.naturalHeight>50000000){URL.revokeObjectURL(url);throw new Error('Maximal 50 Megapixel pro Foto.');}
  if(state.url)URL.revokeObjectURL(state.url);
  state.blob=blob;state.url=url;state.photoId=photoId;
  state.cropId=null;
  $('editorPanel').hidden=false;$('persist').checked=false;$('zoom').value=1;$('editor').style.width='100%';
  editor.load(img,spec);state.dirty=!photoId;
  $('save').textContent=photoId?'Neue Zuschnitt-Version speichern':'Original und Zuschnitt speichern';
  message(photoId?'Original geöffnet. Änderungen werden als neue Zuschnitt-Version gespeichert.':'Foto bereit. Bitte Ausschnitt auswählen und bei Bedarf speichern.');
  $('editorPanel').scrollIntoView({behavior:'smooth',block:'start'});
}
async function shoot(){
  if(!mayReplace())return;
  const v=$('video');if(!v.videoWidth)throw new Error('Kamerabild noch nicht bereit.');
  const canvas=document.createElement('canvas');canvas.width=v.videoWidth;canvas.height=v.videoHeight;
  canvas.getContext('2d').drawImage(v,0,0);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',0.96));
  canvas.width=canvas.height=1;
  if(!blob)throw new Error('Aufnahme fehlgeschlagen.');
  stopCamera();await loadBlob(blob);
}
function discard(){
  if(state.url)URL.revokeObjectURL(state.url);
  state.blob=null;state.url=null;state.photoId=null;state.dirty=false;
  state.cropId=null;
  editor.image=null;editor.base=null;$('editor').width=1;$('cropPreview').width=1;
  $('editorPanel').hidden=true;$('persist').checked=false;
}
async function projects(){
  const rows=await (await api('/api/projects')).json(),previous=state.project;
  $('projects').replaceChildren(new Option('Projekt wählen',''));
  for(const row of rows)$('projects').add(new Option(row.name,row.project_id));
  state.project=rows.some(x=>x.project_id===previous)?previous:(rows[0]?.project_id||'');
  $('projects').value=state.project;
  $('activeProject').textContent=state.project?$('projects').selectedOptions[0].textContent:'Kein Projekt';
  $('exportCalibre').disabled=$('exportCsv').disabled=!state.project;
  await gallery();await recognition.refresh();
}
async function downloadExport(kind){
  if(!state.project)throw new Error('Bitte zuerst im Menü ein Projekt wählen.');
  const calibre=kind==='calibre',filename=calibre?'projekt.json':'papierbibliothek.csv';
  const response=await api('/api/projects/'+state.project+'/export/'+kind);
  const blob=await response.blob(),file=new File([blob],filename,{type:blob.type});
  if(navigator.share&&navigator.canShare?.({files:[file]})){
    try{await navigator.share({files:[file],title:calibre?'Papierbibliothek für Calibre':'Papierbibliothek CSV'});}
    catch(error){if(error.name!=='AbortError')throw error;else return;}
  }else{
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  message(calibre?'Calibre-Projekt exportiert. Datei als projekt.json in einen eigenen Ordner legen und im Plugin öffnen.':'CSV exportiert.');
}
async function gallery(){
  const container=$('gallery');
  if(!state.project){container.textContent='Noch kein Projekt geöffnet.';return;}
  const rows=await (await api('/api/projects/'+state.project+'/captures')).json();
  container.replaceChildren();
  if(!rows.length){container.textContent='Noch keine gespeicherten Fotos.';return;}
  for(const photo of rows){
    const article=document.createElement('article');article.className='photo';
    const img=document.createElement('img');img.loading='lazy';img.alt='Gespeicherter Zuschnitt';
    const info=document.createElement('p');
    info.textContent=({isbn:'ISBN / Barcode',spine:'Buchrücken',titlepage:'Titelblatt',shelf:'Regalfoto'}[photo.capture_type])+' · '+photo.width+' × '+photo.height+' · '+new Date(photo.created_at).toLocaleString('de-DE');
    const versions=document.createElement('select');versions.setAttribute('aria-label','Zuschnitt-Version');
    for(const [i,crop] of photo.crops.entries())versions.add(new Option('Version '+(photo.crops.length-i)+' · '+crop.width+' × '+crop.height,crop.crop_id));
    const update=()=>{img.src='/api/crops/'+versions.value+'/image';};versions.addEventListener('change',update);update();
    const button=document.createElement('button');button.textContent='Original öffnen / bearbeiten';
    button.onclick=async()=>{
      if(state.busy||!mayReplace())return;
      try{
        const blob=await (await api('/api/captures/'+photo.photo_id+'/original')).blob();
        $('kind').value=photo.capture_type;
        await loadBlob(blob,photo.photo_id,photo.crops.find(c=>c.crop_id===versions.value).transform);
        state.cropId=versions.value;
      }catch(error){message(error.message,true);}
    };
    article.append(img,info,versions,button);container.append(article);
  }
}
async function save(){
  if(!state.blob)throw new Error('Zuerst ein Foto aufnehmen.');
  if(!$('persist').checked)throw new Error('Zum Übertragen bitte „Original und Zuschnitt auf meinem Homeserver speichern“ aktivieren.');
  if(!state.project)throw new Error('Bitte zuerst anmelden und ein Projekt wählen.');
  state.busy=true;$('save').disabled=true;$('editorPanel').inert=true;
  try{
    message('Original und Zuschnitt werden gespeichert …');
    const spec=editor.spec();
    const response=state.photoId
      ? await json('/api/captures/'+state.photoId+'/crops',spec)
      : await api('/api/projects/'+state.project+'/captures?'+new URLSearchParams({...spec,kind:$('kind').value,store_images:'true'}),{method:'POST',body:state.blob,headers:{'Content-Type':state.blob.type}});
    const saved=await response.json();state.photoId=saved.photo_id;state.cropId=saved.crop_id;state.dirty=false;$('persist').checked=false;
    $('save').textContent='Neue Zuschnitt-Version speichern';
    await gallery();message('Gespeichert. Bei ISBN „Ausschnitt bestätigen und ISBN erkennen“ wählen; Buchrücken und Titelblatt über „Kostenpflichtig auswerten“ prüfen.');
  }finally{state.busy=false;$('save').disabled=false;$('editorPanel').inert=false;}
}
action('loginForm',async()=>{
  const password=$('password').value;$('password').value='';
  await json('/api/login',{password});$('loginPanel').hidden=true;$('logout').hidden=false;
  await projects();await recognition.visionStatus();message('Angemeldet. Kamera wird gestartet …');await autoCamera();
},'submit');
action('logout',async()=>{
  if(!mayReplace())return;
  await json('/api/logout',{});stopCamera();discard();recognition.reset();state.project='';$('books').replaceChildren();
  $('gallery').replaceChildren();$('projects').replaceChildren(new Option('Bitte anmelden',''));
  $('activeProject').textContent='Kein Projekt';$('exportCalibre').disabled=$('exportCsv').disabled=true;
  $('loginPanel').hidden=false;$('logout').hidden=true;message('Abgemeldet.');
});
action('projectForm',async()=>{
  const created=await (await json('/api/projects',{name:$('projectName').value})).json();
  if(state.dirty||recognition.dirty){message('Projekt angelegt. Zum Wechseln zuerst die aktuelle Aufnahme und Metadaten speichern.');return;}
  discard();recognition.reset();state.project=created.project_id;$('projectName').value='';await projects();$('appMenu').close();message('Projekt angelegt.');await autoCamera();
},'submit');
action('projects',async()=>{
  if(!mayReplace()){$('projects').value=state.project;return;}
  discard();recognition.reset();state.project=$('projects').value;
  $('activeProject').textContent=state.project?$('projects').selectedOptions[0].textContent:'Kein Projekt';
  $('exportCalibre').disabled=$('exportCsv').disabled=!state.project;
  await gallery();await recognition.refresh();$('appMenu').close();await autoCamera();
},'change');
action('camera',camera);action('shoot',shoot);action('stop',stopCamera);action('save',save);
action('menuButton',()=>{$('appMenu').showModal?$('appMenu').showModal():$('appMenu').setAttribute('open','');});
action('menuClose',()=>{$('appMenu').close?$('appMenu').close():$('appMenu').removeAttribute('open');});
action('exportCalibre',()=>downloadExport('calibre'));action('exportCsv',()=>downloadExport('csv'));
action('discard',()=>{if(mayReplace()){discard();message('Ungespeicherte Aufnahme verworfen.');}});
action('refresh',async()=>{await gallery();await recognition.refresh();});
action('kind',async()=>{stopCamera();recognition.kindChanged();await autoCamera();},'change');
for(const id of ['file','nativeCamera'])action(id,async()=>{
  const file=$(id).files[0];$(id).value='';
  if(file && mayReplace()){stopCamera();await loadBlob(file);}
},'change');
action('rotateLeft',()=>editor.rotate(-90));action('rotateRight',()=>editor.rotate(90));action('reset',()=>editor.reset());
action('rotation',()=>editor.setRotation(Number($('rotation').value)),'input');
action('zoom',()=>{$('editor').style.width=(Number($('zoom').value)*100)+'%';},'input');
for(const id of ['cropX','cropY','cropW','cropH'])action(id,()=>{
  editor.setBox({x:Number($('cropX').value)/100,y:Number($('cropY').value)/100,width:Number($('cropW').value)/100,height:Number($('cropH').value)/100});
},'change');
window.addEventListener('pagehide',stopCamera);
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopCamera();});
window.addEventListener('beforeunload',event=>{if(state.dirty||recognition.dirty){event.preventDefault();event.returnValue='';}});
window.addEventListener('online',network);window.addEventListener('offline',network);network();
async function initialize(){
  try{await api('/api/session');$('loginPanel').hidden=true;$('logout').hidden=false;await projects();await recognition.visionStatus();await autoCamera();}
  catch(error){
    if(error.httpStatus===401)message('Bitte anmelden. Fotos können bereits lokal zugeschnitten werden.');
    else message(error.message,true);
  }
  if('serviceWorker' in navigator && window.isSecureContext){
    try{
      const reg=await navigator.serviceWorker.register('/sw.js');
      const changed=()=>{$('update').hidden=!(reg.waiting && navigator.serviceWorker.controller);};
      changed();reg.addEventListener('updatefound',()=>reg.installing?.addEventListener('statechange',changed));
      action('update',()=>{
        if(!mayReplace())return;
        state.dirty=false;recognition.dirty=false;
        if(reg.waiting)reg.waiting.postMessage('activate');
        else location.reload();
      });
      const hadController=Boolean(navigator.serviceWorker.controller);
      navigator.serviceWorker.addEventListener('controllerchange',()=>{if(hadController && !state.dirty && !recognition.dirty)location.reload();});
    }catch{message('Offline-Oberfläche konnte nicht installiert werden. Online-Nutzung ist möglich.');}
  }
}
initialize();
