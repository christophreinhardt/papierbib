import {canonical} from './isbn.mjs';
import {BarcodeScanner} from './scanner.mjs';
const $=id=>document.getElementById(id);
const fields=['title','subtitle','authors','editors','publisher','publication_year','language','edition','extent','publication_place','notes'];

export class Recognition {
  constructor({api,json,notify,project,crop,context,stopCamera,lock,isLocked,kind,onNewBook}){
    Object.assign(this,{api,json,notify,project,crop,context,stopCamera,lock,isLocked,kind,onNewBook});
    this.scanner=new BarcodeScanner();this.dirty=false;this.busy=false;this.record={};this.vision=null;this.bookId=crypto.randomUUID();this.link={};
    this.bind('recognize',()=>this.recognize());
    this.bind('lookup',()=>this.lookup());
    this.bind('confirmBook',()=>this.save('confirmed'));
    this.bind('draftBook',()=>this.save('draft'));
    this.bind('rescanBook',()=>this.save('needs_scan'));
    this.bind('newBook',async()=>{if(this.mayReplace()){this.reset();await this.onNewBook?.();}});
    this.bind('visionAnalyze',()=>this.analyzeVision());
    $('bookIsbn').addEventListener('input',()=>{
      this.dirty=true;this.record={};$('matches').replaceChildren();
      // Changing ISBN invalidates old edition metadata, not the user's notes.
      for(const key of fields)if(key!=='notes')$('book_'+key).value='';
    });
    for(const key of fields)$('book_'+key).addEventListener('input',()=>{this.dirty=true;});
  }
  bind(id,fn){$(id).addEventListener('click',async()=>{
    if(this.busy||this.isLocked())return;
    this.busy=true;this.lock(true);$('reviewPanel').inert=true;
    try{await fn();}catch(error){this.notify(error.message,true);}
    finally{this.busy=false;this.lock(false);$('reviewPanel').inert=false;}
  });}
  mayReplace(){return !this.dirty||confirm('Ungespeicherte Metadaten verwerfen?');}
  reset(){
    this.record={};this.vision=null;this.bookId=crypto.randomUUID();this.link={};this.dirty=false;
    $('bookIsbn').value='';for(const key of fields)$('book_'+key).value='';
    $('matches').replaceChildren();$('isbnCandidates').replaceChildren();$('reviewInfo').textContent='ISBN eingeben oder einen bestätigten Fotoausschnitt erkennen lassen.';
  }
  populate(record){
    this.record={...record};
    for(const key of fields)$('book_'+key).value=Array.isArray(record[key])?record[key].join('\n'):(record[key]??'');
    this.dirty=true;
  }
  async visionStatus(){
    const select=$('visionProvider'),info=$('visionInfo');
    try{
      const status=await (await this.api('/api/vision/status')).json();
      select.replaceChildren();
      for(const provider of status.configured)select.add(new Option(provider+' · '+status.models[provider],provider));
      select.value=status.default_provider||status.configured[0]||'';
      select.disabled=!status.configured.length;$('visionAnalyze').disabled=!status.configured.length;
      info.textContent=status.configured.length?'Für Buchrücken und Titelblatt verfügbar. API-Schlüssel bleiben ausschließlich im Homeserver.':'Kein KI-Provider konfiguriert. OPENAI_API_KEY oder GEMINI_API_KEY nur in Portainer setzen.';
      this.kindChanged();
    }catch(error){select.disabled=true;$('visionAnalyze').disabled=true;info.textContent='KI-Provider konnte nicht geprüft werden.';}
  }
  kindChanged(){
    const compatible=['spine','titlepage'].includes(this.kind());
    $('visionMenu').hidden=!compatible;
    $('visionPanel').hidden=!compatible;$('isbnAction').hidden=this.kind()!=='isbn';
    $('visionAnalyze').disabled=!compatible || !$('visionProvider').value;
    if(compatible)$('visionInfo').textContent=$('visionProvider').value
      ? 'KI-Anbieter auswählen, Foto zuschneiden und anschließend kostenpflichtig auswerten.'
      : 'Kein KI-Provider konfiguriert. OPENAI_API_KEY oder GEMINI_API_KEY nur in Portainer setzen.';
  }
  async analyzeVision(){
    const kind=this.kind();
    if(!['spine','titlepage'].includes(kind))throw new Error('Für KI-Auswertung bitte Aufnahmeart „Buchrücken“ oder „Titelblatt“ wählen.');
    if(!confirm('Kostenpflichtige KI-Auswertung starten? Nur der aktuelle Zuschnitt wird an den gewählten Anbieter gesendet. Die Nutzung kann Kosten verursachen.'))return;
    this.stopCamera();const image=await this.crop();
    const blob=await new Promise(resolve=>image.toBlob(resolve,'image/jpeg',0.96));image.width=image.height=1;
    if(!blob)throw new Error('Zuschnitt konnte nicht erzeugt werden.');
    this.notify('KI wertet den bestätigten Zuschnitt aus …');
    const provider=$('visionProvider').value;
    const response=await this.api('/api/vision/analyze?'+new URLSearchParams({kind,provider,consent:'true'}),{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'},timeout:60000});
    const data=(await response.json()).result;
    this.vision={result:{raw_text:data.raw_text,title:data.title,subtitle:data.subtitle,authors:data.authors,publisher:data.publisher,language:data.language,publication_year:data.publication_year,isbn10:data.isbn10,isbn13:data.isbn13,confidence:data.confidence},provider:data.provider,model:data.model,analyzed_at:data.analyzed_at};
    this.record={};this.link=this.context();
    if(data.isbn13)$('bookIsbn').value=data.isbn13;
    this.populate(data);
    $('reviewInfo').textContent='KI-Vorschlag von '+data.provider+' · '+data.model+'. Alle Felder prüfen, bei ISBN optional lobid suchen und erst dann speichern.';
    this.notify('KI-Vorschlag übernommen. Bitte Angaben prüfen.',false);
    $('reviewPanel').scrollIntoView({behavior:'smooth',block:'start'});
  }
  async accept(value,automatic=false){
    if(!this.mayReplace())return;
    this.reset();$('bookIsbn').value=canonical(value);this.dirty=true;
    $('reviewPanel').scrollIntoView({behavior:'smooth',block:'start'});
    if(automatic)await this.lookup();
  }
  async recognize(){
    if(!this.mayReplace())return;
    this.stopCamera();
    const image=await this.crop(); // Explicit editor action; never send the original.
    this.reset();this.link=this.context();
    this.notify('Bestätigten Ausschnitt lokal nach einem Barcode durchsuchen …');
    let value=null;
    try{value=await this.scanner.decode(image);}catch{/* OCR remains available if the local decoder fails. */}
    let numbers=value?[value]:[];
    if(!numbers.length){
      this.notify('Kein gültiger Barcode. ISBN-only-OCR auf dem Homeserver …');
      const blob=await new Promise(resolve=>image.toBlob(resolve,'image/jpeg',0.97));
      image.width=image.height=1;
      if(!blob)throw new Error('Zuschnitt konnte nicht erzeugt werden.');
      const result=await (await this.api('/api/isbn/ocr?crop_confirmed=true',{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'}})).json();
      numbers=result.isbns;
    }else image.width=image.height=1;
    $('reviewPanel').scrollIntoView({behavior:'smooth',block:'start'});
    $('isbnCandidates').replaceChildren();
    for(const n of numbers){
      const button=document.createElement('button');button.textContent=n;
      button.onclick=()=>{$('bookIsbn').value=n;$('bookIsbn').dispatchEvent(new Event('input'));};$('isbnCandidates').append(button);
    }
    if(numbers.length===1){$('bookIsbn').value=numbers[0];this.dirty=true;}
    const note=numbers.length?'ISBN erkannt. Nummer prüfen, dann „Bei lobid suchen“ wählen.':'Keine gültige ISBN erkannt. Enger zuschneiden, besser fotografieren oder ISBN manuell eingeben.';
    $('reviewInfo').textContent=note;this.notify(note,!numbers.length);
  }
  async lookup(){
    const isbn=canonical($('bookIsbn').value);$('bookIsbn').value=isbn;this.dirty=true;
    this.notify('ISBN wird bei lobid gesucht …');$('matches').replaceChildren();
    const data=await (await this.json('/api/isbn/lookup',{isbn})).json();
    $('reviewInfo').textContent=data.error||(data.matches.length?data.matches.length+' lobid-Treffer. Ausgabe vergleichen und ausdrücklich übernehmen.':'Kein passender lobid-Treffer. ISBN bleibt erhalten; als Entwurf speichern.');
    for(const match of data.matches){
      const article=document.createElement('article');article.className='match';
      const label=document.createElement('p');label.textContent=[match.title,match.subtitle,(match.authors||[]).join('; '),match.publisher,match.publication_year,match.edition].filter(Boolean).join(' · ');
      const button=document.createElement('button');button.textContent='Diesen Treffer übernehmen';
      button.onclick=()=>{this.populate(match);this.notify('Treffer übernommen. Angaben prüfen und speichern.');};
      article.append(label,button);$('matches').append(article);
    }
    this.notify($('reviewInfo').textContent,Boolean(data.error));
  }
  async save(status){
    if(!this.project())throw new Error('Bitte anmelden und ein Projekt wählen.');
    const entered=$('bookIsbn').value.trim(),isbn=entered?canonical(entered):null,data={book_id:this.bookId,...this.link,status,isbn13:isbn};
    for(const key of fields){
      const value=$('book_'+key).value.trim();
      data[key]=['authors','editors'].includes(key)?value.split('\n').map(v=>v.trim()).filter(Boolean):key==='publication_year'?(value?Number(value):null):(value||null);
    }
    data.source_url=this.record.source_url||null;data.fetched_at=this.record.fetched_at||null;
    data.vision=this.vision;
    if(status==='confirmed'&&!data.title)throw new Error('Zum Bestätigen einen Titel eingeben oder als Entwurf speichern.');
    const existing=await (await this.api('/api/projects/'+this.project()+'/books')).json();
    if(isbn&&existing.some(x=>x.isbn13===isbn&&x.book_id!==this.bookId)&&!confirm('Diese ISBN ist im Projekt bereits gespeichert. Ein weiteres Exemplar anlegen?'))return;
    await this.json('/api/projects/'+this.project()+'/books',data);this.dirty=false;
    await this.refresh();this.notify('Buch gespeichert'+(status==='draft'?' (Entwurf).':status==='needs_scan'?' (erneut erfassen).':'.'));
  }
  async refresh(){
    $('books').replaceChildren();if(!this.project())return;
    const rows=await (await this.api('/api/projects/'+this.project()+'/books')).json();
    for(const row of rows){
      const article=document.createElement('article');article.className='match';
      const text=document.createElement('p');text.textContent=(row.title||'Ohne Titel')+(row.isbn13?' · '+row.isbn13:' · ohne ISBN')+' · '+({confirmed:'Bestätigt',draft:'Entwurf',needs_scan:'Erneut erfassen'}[row.status]||row.status);
      const button=document.createElement('button');button.textContent='Buch bearbeiten';
      button.onclick=()=>{
        if(this.busy||!this.mayReplace())return;
        this.reset();this.bookId=row.book_id;this.link={photo_id:row.photo_id,crop_id:row.crop_id};
        $('bookIsbn').value=row.isbn13||'';this.vision=row.vision||null;this.populate(row);this.dirty=false;
        $('reviewPanel').scrollIntoView({behavior:'smooth',block:'start'});
      };
      article.append(text,button);$('books').append(article);
    }
  }
}
