export function normalize(value){
  return String(value||'').normalize('NFKC').trim().toUpperCase().replace(/^ISBN(?:-1[03])?\s*:?\s*/,'').replace(/[\s\-‐‑‒–—]/g,'');
}
export function valid(value){
  const n=normalize(value);
  if(/^[0-9]{9}[0-9X]$/.test(n))return [...n].reduce((s,c,i)=>s+(10-i)*(c==='X'?10:Number(c)),0)%11===0;
  return /^97[89][0-9]{10}$/.test(n)&&[...n].reduce((s,c,i)=>s+Number(c)*(i%2?3:1),0)%10===0;
}
export function canonical(value){
  const n=normalize(value);
  if(!valid(n))throw new Error('Ungültige ISBN: Länge, Präfix oder Prüfziffer stimmt nicht.');
  if(n.length===13)return n;
  const prefix='978'+n.slice(0,9),sum=[...prefix].reduce((s,c,i)=>s+Number(c)*(i%2?3:1),0);
  return prefix+((10-sum%10)%10);
}
