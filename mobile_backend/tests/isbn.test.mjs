import test from 'node:test';
import assert from 'node:assert/strict';
import {valid,canonical} from '../web/isbn.mjs';
test('ISBN-10/13 equivalent, X check digit and Unicode',()=>{
  assert.equal(canonical('ISBN-10: 0-306-40615-2'),'9780306406157');
  assert.equal(canonical('080442957X'),'9780804429573');
  assert.equal(canonical('９７８‐０‐３０６‐４０６１５‐７'),'9780306406157');
});
test('invalid barcode payloads are not repaired or treated as ISBN',()=>{
  for(const input of ['9780306406158','1234567890123','https://example.org/9780306406157','978O306406157','abc']){
    assert.equal(valid(input),false);assert.throws(()=>canonical(input));
  }
});
