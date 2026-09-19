import {valid,canonical} from './isbn.mjs';

export class BarcodeScanner {
  constructor(){this.worker=null;this.pending=null;}
  stop(){
    this.worker?.terminate();this.worker=null;
    if(this.pending){this.pending(null);this.pending=null;}
  }
  async decode(source){
    if(this.pending)return null;
    const w=source.videoWidth||source.naturalWidth||source.width,h=source.videoHeight||source.naturalHeight||source.height;
    if(!w||!h)return null;
    const scale=Math.min(1,1920/Math.max(w,h)),canvas=document.createElement('canvas');
    canvas.width=Math.round(w*scale);canvas.height=Math.round(h*scale);
    const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(source,0,0,canvas.width,canvas.height);
    // Safari/Chrome implementations with BarcodeDetector are usually faster on
    // live camera frames. ZXing below remains the local fallback everywhere.
    if('BarcodeDetector' in globalThis){
      try{
        const formats=await BarcodeDetector.getSupportedFormats?.()||[];
        const preferred=['ean_13','ean_8','code_128','code_39','qr_code'].filter(x=>formats.includes(x));
        if(preferred.length){
          const detector=new BarcodeDetector({formats:preferred});
          // Native decoders can use an unscaled video frame; this matters for
          // small EAN bars on current iPhone cameras. Canvas stays the fallback.
          let detected=[];
          try{detected=await detector.detect(source);}catch{detected=await detector.detect(canvas);}
          for(const item of detected){if(valid(item.rawValue))return canonical(item.rawValue);}
        }
      }catch{/* browser implementation failed; do not abandon ZXing */}
    }
    const frame=ctx.getImageData(0,0,canvas.width,canvas.height);
    return new Promise((resolve,reject)=>{
      this.worker ||= new Worker('/barcode-worker.js');
      const timer=setTimeout(()=>{this.stop();},4000);
      this.pending=value=>{clearTimeout(timer);resolve(value);};
      this.worker.onerror=()=>{clearTimeout(timer);this.worker?.terminate();this.worker=null;this.pending=null;reject(new Error('Lokaler Barcode-Scanner nicht verfügbar. Foto aufnehmen oder ISBN eingeben.'));};
      this.worker.onmessage=({data})=>{
        clearTimeout(timer);this.pending=null;
        if(data.error){reject(new Error(data.error));return;}
        resolve(valid(data.value)?canonical(data.value):null);
      };
      this.worker.postMessage({pixels:frame.data.buffer,width:frame.width,height:frame.height},[frame.data.buffer]);
      canvas.width=canvas.height=1;
    });
  }
}
