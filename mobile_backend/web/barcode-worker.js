/* All decoding runs locally in an interruptible worker, including Safari. */
importScripts('/vendor/zxing-0.23.0.min.js');
self.onmessage=({data:{pixels,width,height}})=>{
  try{
    const rgba=new Uint8ClampedArray(pixels),gray=new Uint8ClampedArray(width*height);
    for(let i=0;i<gray.length;i++)gray[i]=(rgba[i*4]+2*rgba[i*4+1]+rgba[i*4+2])/4;
    const hints=new Map([
      [ZXing.DecodeHintType.POSSIBLE_FORMATS,[ZXing.BarcodeFormat.EAN_13,ZXing.BarcodeFormat.CODE_128,ZXing.BarcodeFormat.CODE_39,ZXing.BarcodeFormat.QR_CODE]],
      [ZXing.DecodeHintType.TRY_HARDER,true]
    ]);
    for(let turn=0;turn<2;turn++){
      let values=gray,w=width,h=height;
      if(turn){
        values=new Uint8ClampedArray(gray.length);w=height;h=width;
        for(let y=0;y<height;y++)for(let x=0;x<width;x++)values[x*height+height-1-y]=gray[y*width+x];
      }
      const reader=new ZXing.MultiFormatReader();
      try{
        const source=new ZXing.RGBLuminanceSource(values,w,h);
        const result=reader.decode(new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(source)),hints);
        self.postMessage({value:result.getText()});return;
      }catch(error){
        if(!['NotFoundException','ChecksumException','FormatException'].includes(error.constructor.name)&&
           !(error instanceof ZXing.NotFoundException)&&!(error instanceof ZXing.ChecksumException)&&!(error instanceof ZXing.FormatException))throw error;
      }finally{reader.reset();}
    }
    self.postMessage({value:null});
  }catch{self.postMessage({error:'Barcode-Decoder konnte dieses Bild nicht verarbeiten.'});}
};
