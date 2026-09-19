const $ = (id) => document.getElementById(id);
const state = { mode: 'isbn', stream: null, image: null, detector: null, db: null };
const API = 'https://lobid.org/resources/search';

function digits(value) { return String(value || '').replace(/[^0-9Xx]/g, '').toUpperCase(); }
function isbn13(value) {
  const clean = digits(value);
  if (/^97[89]\d{10}$/.test(clean)) return clean;
  if (/^\d{9}[\dX]$/.test(clean)) return '978' + clean.slice(0, 9) + isbnCheck('978' + clean.slice(0, 9));
  return null;
}
function isbnCheck(prefix) {
  let sum = 0;
  for (let i = 0; i < prefix.length; i++) sum += Number(prefix[i]) * (i % 2 ? 3 : 1);
  return String((10 - sum % 10) % 10);
}
function validIsbn(value) {
  const clean = digits(value);
  if (/^97[89]\d{10}$/.test(clean)) return clean.slice(0, 12).split('').reduce((s, d, i) => s + Number(d) * (i % 2 ? 3 : 1), 0) % 10 === (10 - Number(clean[12])) % 10 ? clean : null;
  if (/^\d{9}[\dX]$/.test(clean)) {
    const sum = clean.split('').reduce((s, d, i) => s + (d === 'X' ? 10 : Number(d)) * (10 - i), 0);
    return sum % 11 === 0 ? isbn13(clean) : null;
  }
  return null;
}
function status(message, error = false) { $('resultStatus').textContent = message; $('resultStatus').style.color = error ? '#a42f22' : ''; }
function cameraStatus(message, error = false) { $('cameraStatus').textContent = message; $('cameraStatus').style.color = error ? '#a42f22' : ''; }

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('papierbibliothek-mobile', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('books', { keyPath: 'id' });
    request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
  });
}
async function allBooks() { const db = state.db; return new Promise((resolve, reject) => { const r = db.transaction('books').objectStore('books').getAll(); r.onsuccess = () => resolve(r.result.sort((a,b) => b.createdAt.localeCompare(a.createdAt))); r.onerror = () => reject(r.error); }); }
async function putBook(book) { return new Promise((resolve, reject) => { const r = state.db.transaction('books','readwrite').objectStore('books').put(book); r.onsuccess = resolve; r.onerror = () => reject(r.error); }); }
async function deleteBook(id) { return new Promise((resolve, reject) => { const r = state.db.transaction('books','readwrite').objectStore('books').delete(id); r.onsuccess = resolve; r.onerror = () => reject(r.error); }); }

function cameraConstraints() {
  return { audio:false, video:{ facingMode:{ ideal:'environment' }, width:{ ideal:4096 }, height:{ ideal:4096 } } };
}
async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error('Dieser Browser stellt keine Kamera-API bereit. Bitte Safari über HTTPS verwenden.');
  state.stream = await navigator.mediaDevices.getUserMedia(cameraConstraints());
  const track = state.stream.getVideoTracks()[0]; const caps = track.getCapabilities?.();
  if (caps?.width?.max && caps?.height?.max) {
    try { await track.applyConstraints({ width:{ exact:caps.width.max }, height:{ exact:caps.height.max } }); } catch (_) { /* some iOS versions reject exact sensor modes */ }
  }
  $('preview').srcObject = state.stream; $('startCamera').disabled = true; $('stopCamera').disabled = false; $('capture').disabled = false;
  const settings = track.getSettings(); cameraStatus(`Kamera aktiv · ${settings.width || '?'} × ${settings.height || '?'} Pixel · Modus: ${modeLabel()}`);
  if ('BarcodeDetector' in window) { try { state.detector = new BarcodeDetector({ formats:['ean_13','ean_8','upc_a','code_128'] }); } catch (_) {} }
}
function stopCamera() { state.stream?.getTracks().forEach(track => track.stop()); state.stream = null; $('preview').srcObject = null; $('startCamera').disabled = false; $('stopCamera').disabled = true; $('capture').disabled = true; }
function modeLabel() { return { isbn:'ISBN / Barcode', spine:'Buchrücken', titlepage:'Titelblatt' }[state.mode]; }
async function capture() {
  const video = $('preview'); if (!video.videoWidth) return cameraStatus('Noch kein Kamerabild verfügbar.', true);
  const canvas = $('canvas'); canvas.width = video.videoWidth; canvas.height = video.videoHeight; canvas.getContext('2d').drawImage(video,0,0);
  state.image = canvas.toDataURL('image/jpeg', .92); $('still').src = state.image; $('still').hidden = false;
  cameraStatus(`Aufnahme gespeichert · ${canvas.width} × ${canvas.height} Pixel · ${modeLabel()}`);
  if (state.mode === 'isbn') {
    await scanBarcode(canvas);
  }
}
async function scanBarcode(canvas) {
  try {
    let values = [];
    if (state.detector) {
      values = (await state.detector.detect(canvas)).map(item => item.rawValue);
    } else {
      // Safari on iOS does not expose BarcodeDetector in many versions.
      const { BrowserMultiFormatReader } = await import(
        'https://cdn.jsdelivr.net/npm/@zxing/browser@0.1.5/+esm');
      const reader = new BrowserMultiFormatReader();
      const result = await reader.decodeFromImageUrl(canvas.toDataURL('image/jpeg', .95));
      if (result) values.push(result.getText());
    }
    const value = values.map(validIsbn).find(Boolean);
    if (value) { $('isbn').value = value; await lookup(); }
    else {
      cameraStatus('Kein Barcode erkannt - OCR wird versucht ...');
      await ocr();
    }
  } catch (_) {
    cameraStatus('Barcode konnte nicht gelesen werden - OCR wird versucht ...');
    await ocr();
  }
}
function parseLobid(item) {
  const title = item.title || ''; const author = (item.contribution || []).map(x => x.agent?.label || x.agent?.name || '').filter(Boolean).join(' & ');
  const pub = item.publication?.[0] || {}; const isbn = (item.isbn || []).map(x => typeof x === 'string' ? x : x.value).find(Boolean) || '';
  const publisher = pub.publishedBy?.label || pub.publishedBy?.name || ''; const year = String(pub.startDate || '').slice(0,4);
  return { title, author, publisher, year, isbn, source:'lobid', sourceUrl:item.id || '' };
}
async function lookup() {
  const normalized = validIsbn($('isbn').value); const title = $('title').value.trim(); const author = $('author').value.trim();
  if (!normalized && !title) return status('Bitte eine gültige ISBN oder mindestens einen Titel eingeben.', true);
  const query = normalized ? `isbn:${normalized}` : `title:${title}${author ? ` AND contribution.agent.label:"${author.replaceAll('"','') }"` : ''}`;
  status('lobid wird abgefragt …'); $('lookup').disabled = true;
  try {
    const response = await fetch(`${API}?q=${encodeURIComponent(query)}&format=json`, { headers:{ Accept:'application/json' } });
    if (!response.ok) throw new Error(`lobid antwortete mit HTTP ${response.status}`);
    const data = await response.json(); const rows = (data.member || data.items || []).map(parseLobid);
    const exact = normalized ? rows.find(row => validIsbn(row.isbn) === normalized) : rows[0];
    if (!exact) { $('isbn').value = normalized || $('isbn').value; status('Kein eindeutiger lobid-Treffer. Die Eingaben können trotzdem gespeichert werden.', true); return; }
    if (exact.title) $('title').value = exact.title; if (exact.author) $('author').value = exact.author; if (exact.publisher) $('publisher').value = exact.publisher; if (exact.year) $('year').value = exact.year; if (exact.isbn) $('isbn').value = exact.isbn;
    status(`Treffer übernommen: ${exact.title} · lobid`);
  } catch (error) { status(`Onlineabfrage fehlgeschlagen: ${error.message}. Eingaben können trotzdem gespeichert werden.`, true); }
  finally { $('lookup').disabled = false; }
}
async function preprocessForOcr(dataUrl) {
  return await new Promise((resolve) => {
    const image = new Image();
    image.onload = () => {
      const max = 2400; const scale = Math.min(1, max / Math.max(image.naturalWidth, image.naturalHeight));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.filter = 'grayscale(1) contrast(1.35)';
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL('image/png'));
    };
    image.onerror = () => resolve(dataUrl);
    image.src = dataUrl;
  });
}
async function ocr() {
  if (!state.image) return status('Zuerst ein Buchrücken- oder Titelblattfoto aufnehmen.', true);
  status('OCR-Bibliothek wird geladen …'); $('ocr').disabled = true;
  try {
    if (!window.Tesseract) await new Promise((resolve, reject) => { const s=document.createElement('script'); s.src='https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js'; s.onload=resolve; s.onerror=()=>reject(new Error('Tesseract konnte nicht geladen werden')); document.head.append(s); });
    const imageForOcr = await preprocessForOcr(state.image);
    const result = await window.Tesseract.recognize(imageForOcr, 'deu+eng', { logger: m => { if (m.status && m.progress) status(`OCR: ${m.status} ${Math.round(m.progress*100)} %`); } });
    const text = result.data.text.trim();
    const candidate = (text.match(/[0-9Xx][0-9Xx -]{9,20}/g) || []).map(validIsbn).find(Boolean);
    if (candidate) { $('isbn').value = candidate; status(`OCR abgeschlossen · ISBN ${candidate} erkannt. Bitte prüfen und lobid suchen.`); }
    else status('Keine ISBN erkannt. Bitte ein schärferes ISBN-Foto aufnehmen.', true);
  } catch (error) { status(`OCR fehlgeschlagen: ${error.message}`, true); } finally { $('ocr').disabled = false; }
}
async function analyzeWithBackend() {
  if (!state.image) return status('Zuerst ein Foto aufnehmen.', true);
  const base = $('backendUrl').value.trim().replace(/\/$/, '');
  const token = $('backendToken').value.trim();
  if (!base || !token) return status('Backend-URL und Zugriffstoken eintragen.', true);
  localStorage.setItem('papierbib-backend-url', base);
  sessionStorage.setItem('papierbib-backend-token', token);
  const endpoint = state.mode === 'spine' ? 'book-spine' : 'title-page';
  const response = await fetch(`${base}/api/vision/${endpoint}`, { method:'POST', headers:{ Authorization:`Bearer ${token}` }, body:(() => { const form = new FormData(); form.append('image', dataUrlBlob(state.image), 'capture.jpg'); return form; })() });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `Backend HTTP ${response.status}`);
  const result = await response.json();
  if (result.title) $('title').value = result.title;
  if (result.author) $('author').value = result.author;
  if (result.publisher) $('publisher').value = result.publisher;
  if (result.year) $('year').value = result.year;
  if (result.isbn13 || result.isbn10) $('isbn').value = result.isbn13 || result.isbn10;
  const hasUsefulResult = Boolean(result.title || result.author || result.publisher || result.year || result.isbn10 || result.isbn13);
  if (hasUsefulResult) status(`KI-Auswertung abgeschlossen (${result.source || 'Backend'}). Bitte prüfen.`);
  else { status('KI lieferte keine verwertbaren Angaben. ISBN-OCR wird versucht ...'); await ocr(); }
}
function dataUrlBlob(value) {
  const [meta, encoded] = value.split(',');
  const binary = atob(encoded); const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: meta.match(/data:([^;]+)/)?.[1] || 'image/jpeg' });
}
async function save() {
  const normalized = validIsbn($('isbn').value); if ($('isbn').value.trim() && !normalized) return status('Die eingegebene ISBN ist ungültig.', true);
  const book = { id:crypto.randomUUID(), captureType:state.mode, isbn:normalized || null, title:$('title').value.trim() || null, author:$('author').value.trim() || null, publisher:$('publisher').value.trim() || null, year:$('year').value.trim() || null, rawText:$('rawText').value.trim() || null, image:state.image || null, source:'lobid', status:normalized || $('title').value.trim() ? 'needs_manual_review' : 'needs_scan', createdAt:new Date().toISOString() };
  await putBook(book); clearForm(); await render(); status('Datensatz lokal gespeichert.');
}
function clearForm() { ['isbn','title','author','publisher','year','rawText'].forEach(id => $(id).value=''); $('still').hidden=true; $('still').removeAttribute('src'); state.image=null; }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
async function render() { const rows=await allBooks(); $('count').textContent=rows.length; $('books').innerHTML=rows.map(book => `<tr><td>${escapeHtml(book.isbn || '—')}</td><td>${escapeHtml(book.title || '—')}</td><td>${escapeHtml(book.author || '—')}</td><td>${escapeHtml(book.source)} · ${escapeHtml(book.status)}</td><td><button data-delete="${book.id}" aria-label="Datensatz löschen">Löschen</button></td></tr>`).join(''); document.querySelectorAll('[data-delete]').forEach(button => button.onclick=async()=>{await deleteBook(button.dataset.delete); await render();}); }
function download(name, type, content) { const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([content],{type})); a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(a.href),1000); }
async function exportJson() { download(`papierbibliothek-${new Date().toISOString().slice(0,10)}.json`,'application/json',JSON.stringify({schema_version:1,books:await allBooks()},null,2)); }
async function exportCsv() { const rows=await allBooks(); const fields=['isbn','title','author','publisher','year','captureType','source','status','rawText','createdAt']; const cell=v=>`"${String(v ?? '').replaceAll('"','""')}"`; download(`papierbibliothek-${new Date().toISOString().slice(0,10)}.csv`,'text/csv;charset=utf-8','\ufeff'+[fields.join(';'),...rows.map(r=>fields.map(f=>cell(r[f])).join(';'))].join('\n')); }
function setMode(mode) { state.mode=mode; document.querySelectorAll('.mode').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode)); if (state.stream) cameraStatus(`Kamera aktiv · Modus: ${modeLabel()}`); }

document.querySelectorAll('.mode').forEach(button=>button.onclick=()=>setMode(button.dataset.mode)); $('startCamera').onclick=()=>startCamera().catch(error=>cameraStatus(error.message,true)); $('stopCamera').onclick=stopCamera; $('capture').onclick=()=>capture().catch(error=>cameraStatus(error.message,true)); $('lookup').onclick=lookup; $('ocr').onclick=ocr; $('aiAnalyze').onclick=async()=>{ try { await analyzeWithBackend(); } catch (error) { status(`KI-Auswertung fehlgeschlagen: ${error.message}. ISBN-OCR wird versucht ...`,true); await ocr(); } }; $('save').onclick=()=>save().catch(error=>status(`Speichern fehlgeschlagen: ${error.message}`,true)); $('exportJson').onclick=exportJson; $('exportCsv').onclick=exportCsv; $('clearAll').onclick=async()=>{ if(confirm('Alle lokal gespeicherten Datensätze löschen?')) { const db=state.db; const tx=db.transaction('books','readwrite'); tx.objectStore('books').clear(); tx.oncomplete=render; } }; $('helpButton').onclick=()=>$('helpDialog').showModal(); $('closeHelp').onclick=()=>$('helpDialog').close(); window.addEventListener('pagehide',stopCamera);
$('backendUrl').value = localStorage.getItem('papierbib-backend-url') || ''; $('backendToken').value = sessionStorage.getItem('papierbib-backend-token') || '';
state.db = await openDb(); await render();
