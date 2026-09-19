export const fullBox = () => ({x:0,y:0,width:1,height:1});
export const clamp = (v, low, high) => Math.max(low, Math.min(high, v));
export function constrain(box) {
  const width = clamp(Number(box.width) || 0.01, 0.005, 1);
  const height = clamp(Number(box.height) || 0.01, 0.005, 1);
  return {x:clamp(Number(box.x)||0,0,1-width),y:clamp(Number(box.y)||0,0,1-height),width,height};
}
export function boxFromPoints(a,b) {
  return constrain({x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),width:Math.abs(a.x-b.x),height:Math.abs(a.y-b.y)});
}
export function rotatedSize(width,height,rotation) {
  return rotation % 180 ? {width:height,height:width} : {width,height};
}
export class CropEditor {
  constructor(canvas, preview, onChange) {
    this.canvas=canvas; this.preview=preview; this.onChange=onChange;
    this.rotation=0; this.box=fullBox(); this.drag=null;
    canvas.addEventListener('pointerdown',e=>this.start(e));
    canvas.addEventListener('pointermove',e=>this.move(e));
    canvas.addEventListener('pointerup',()=>{this.drag=null;});
    canvas.addEventListener('pointercancel',()=>{this.drag=null;});
  }
  load(image, spec={rotation:0,...fullBox()}) {
    this.image=image; this.rotation=spec.rotation; this.box=constrain(spec); this.rebuild();
  }
  rebuild() {
    const size=rotatedSize(this.image.naturalWidth,this.image.naturalHeight,this.rotation);
    const scale=Math.min(1,2200/Math.max(size.width,size.height));
    this.base=document.createElement('canvas');
    this.base.width=Math.round(size.width*scale); this.base.height=Math.round(size.height*scale);
    const ctx=this.base.getContext('2d');
    ctx.translate(this.base.width/2,this.base.height/2); ctx.rotate(this.rotation*Math.PI/180);
    ctx.drawImage(this.image,-this.image.naturalWidth*scale/2,-this.image.naturalHeight*scale/2,this.image.naturalWidth*scale,this.image.naturalHeight*scale);
    this.canvas.width=this.base.width; this.canvas.height=this.base.height; this.draw();
  }
  rotate(delta) { this.rotation=(this.rotation+delta+360)%360; this.box=fullBox(); this.rebuild(); }
  reset() { this.rotation=0; this.box=fullBox(); this.rebuild(); }
  setBox(box) { this.box=constrain(box); this.draw(); }
  spec() { return {rotation:this.rotation,...this.box}; }
  point(event) {
    const r=this.canvas.getBoundingClientRect();
    return {x:clamp((event.clientX-r.left)/r.width,0,1),y:clamp((event.clientY-r.top)/r.height,0,1)};
  }
  start(event) {
    if(!this.image || this.drag) return;
    event.preventDefault(); this.canvas.setPointerCapture(event.pointerId);
    const p=this.point(event), b=this.box, r=this.canvas.getBoundingClientRect();
    const corners=[[b.x,b.y,b.x+b.width,b.y+b.height],[b.x+b.width,b.y,b.x,b.y+b.height],[b.x,b.y+b.height,b.x+b.width,b.y],[b.x+b.width,b.y+b.height,b.x,b.y]];
    const corner=corners.find(c=>Math.hypot((p.x-c[0])*r.width,(p.y-c[1])*r.height)<30);
    if(corner) this.drag={id:event.pointerId,mode:'resize',anchor:{x:corner[2],y:corner[3]}};
    else if(p.x>b.x && p.x<b.x+b.width && p.y>b.y && p.y<b.y+b.height)
      this.drag={id:event.pointerId,mode:'move',anchor:p,box:{...b}};
    else this.drag={id:event.pointerId,mode:'resize',anchor:p};
  }
  move(event) {
    if(!this.drag || this.drag.id!==event.pointerId)return;
    const p=this.point(event),d=this.drag;
    this.box=d.mode==='move'?constrain({...d.box,x:d.box.x+p.x-d.anchor.x,y:d.box.y+p.y-d.anchor.y}):boxFromPoints(d.anchor,p);
    this.draw();
  }
  draw() {
    const c=this.canvas,ctx=c.getContext('2d'),b=this.box,w=c.width,h=c.height;
    ctx.clearRect(0,0,w,h);ctx.drawImage(this.base,0,0);
    ctx.fillStyle='#00182099';ctx.fillRect(0,0,w,h);
    ctx.drawImage(this.base,b.x*w,b.y*h,b.width*w,b.height*h,b.x*w,b.y*h,b.width*w,b.height*h);
    ctx.strokeStyle='#e8b854';ctx.lineWidth=Math.max(2,w/350);ctx.strokeRect(b.x*w,b.y*h,b.width*w,b.height*h);
    const radius=Math.max(5,12*w/Math.max(c.clientWidth,300));
    ctx.fillStyle='#fff';
    for(const [x,y] of [[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]]){ctx.beginPath();ctx.arc(x*w,y*h,radius,0,Math.PI*2);ctx.fill();}
    const size=rotatedSize(this.image.naturalWidth,this.image.naturalHeight,this.rotation);
    const previewScale=Math.min(1,800/(b.width*w),400/(b.height*h));
    this.preview.width=Math.max(1,Math.round(b.width*w*previewScale));
    this.preview.height=Math.max(1,Math.round(b.height*h*previewScale));
    this.preview.getContext('2d').drawImage(this.base,b.x*w,b.y*h,b.width*w,b.height*h,0,0,this.preview.width,this.preview.height);
    this.onChange(this.spec(),{width:Math.round(b.width*size.width),height:Math.round(b.height*size.height)});
  }
}
