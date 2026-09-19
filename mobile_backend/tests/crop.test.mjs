import test from 'node:test';
import assert from 'node:assert/strict';
import {constrain,boxFromPoints,rotatedSize} from '../web/crop.mjs';
test('dragging in reverse creates a positive crop',()=>{
  assert.deepEqual(boxFromPoints({x:.8,y:.8},{x:.2,y:.2}),{x:.2,y:.2,width:.6000000000000001,height:.6000000000000001});
});
test('moving never loses the crop outside the image',()=>{
  assert.deepEqual(constrain({x:5,y:-5,width:.5,height:.25}),{x:.5,y:0,width:.5,height:.25});
});
test('rotation swaps axes and returns original size after half turn',()=>{
  assert.deepEqual(rotatedSize(4000,3000,90),{width:3000,height:4000});
  assert.deepEqual(rotatedSize(4000,3000,180),{width:4000,height:3000});
});
test('free rotation changes bounds while exact right angles remain stable',()=>{
  const tilted=rotatedSize(1600,900,17);
  assert.ok(tilted.width>1600 && tilted.height>900);
  assert.deepEqual(rotatedSize(1600,900,90),{width:900,height:1600});
});
