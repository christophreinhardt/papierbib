/* All decoding runs locally in an interruptible worker, including Safari. */
importScripts('/vendor/zxing-0.23.0.min.js');
self.onmessage=({data:{pixels,width,height}})=>{
  try{
    const rgba=new Uint8ClampedArray(pixels);
    const hints=new Map([
      [ZXing.DecodeHintType.POSSIBLE_FORMATS,[ZXing.BarcodeFormat.EAN_13,ZXing.BarcodeFormat.CODE_128,ZXing.BarcodeFormat.CODE_39,ZXing.BarcodeFormat.QR_CODE]],
      [ZXing.DecodeHintType.TRY_HARDER,true]
    ]);
    const variants=[
      {left:0,top:0,width,height},
      // Typical book EAN: wide, low in the frame. The other crops retain
      // barcodes held vertically or offset from the centre.
      {left:0,top:Math.floor(height*.15),width,height:Math.ceil(height*.7)},
      {left:Math.floor(width*.15),top:0,width:Math.ceil(width*.7),height}
    ];
    for(const variant of variants){
      const values=new Int32Array(variant.width*variant.height);
      for(let y=0;y<variant.height;y++)for(let x=0;x<variant.width;x++){
        const offset=((variant.top+y)*width+variant.left+x)*4;
        // RGBLuminanceSource expects packed ARGB for Int32Array input.
        values[y*variant.width+x]=(255<<24)|(rgba[offset]<<16)|(rgba[offset+1]<<8)|rgba[offset+2];
      }
      const reader=new ZXing.MultiFormatReader();
      try{
        const source=new ZXing.RGBLuminanceSource(values,variant.width,variant.height);
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
