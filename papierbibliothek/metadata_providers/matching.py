from copy import deepcopy
from difflib import SequenceMatcher
import re
import unicodedata

from ..models import now
from ..isbn import to_isbn13
from .base import MetadataRecord, ProviderError


def norm(value):
    value=unicodedata.normalize('NFKD',value or '').casefold()
    return ' '.join(re.findall(r'\w+', ''.join(c for c in value if not unicodedata.combining(c))))


def similarity(a,b):
    if not a or not b:return None
    return SequenceMatcher(None,norm(a),norm(b)).ratio()


def canonical_isbn(record): return record.isbn13 or (to_isbn13(record.isbn10) if record.isbn10 else None)


def score_record(book,record):
    wanted=book.isbn13 or (to_isbn13(book.isbn10) if book.isbn10 else None)
    found=canonical_isbn(record)
    if wanted and found:return 1.0 if wanted==found else 0.0
    title=similarity(book.title,record.title)
    author=similarity(book.author,' & '.join(record.authors))
    publisher=similarity(book.publisher,record.publisher)
    parts=[(title,.65),(author,.3),(publisher,.05)]
    have=[(v,w) for v,w in parts if v is not None]
    return sum(v*w for v,w in have)/sum(w for v,w in have) if have else 0


def edition_key(record): return canonical_isbn(record) or '|'.join((norm(record.title),norm(' & '.join(record.authors)),str(record.publication_year or '')))


def reconcile(book,records,threshold=.88,probable=.72):
    normalized=[]
    for value in records:
        record=value if isinstance(value,MetadataRecord) else MetadataRecord(**value)
        record.validate(); normalized.append(record)
    groups={}
    for record in normalized:groups.setdefault(edition_key(record),[]).append(record)
    proposals=[]
    for key,items in groups.items():
        score=max(score_record(book,item) for item in items)
        fields={}
        conflicts=[]
        for field in ('title','subtitle','publisher','publication_year','language','isbn10','isbn13'):
            values={getattr(x,field) for x in items if getattr(x,field) is not None}
            if len(values)>1:conflicts.append(field)
            fields[field]=next(iter(values)) if len(values)==1 else None
        authors={' & '.join(x.authors) for x in items if x.authors}
        if len(authors)>1:conflicts.append('author')
        fields['author']=next(iter(authors)) if len(authors)==1 else None
        proposals.append({'edition_key':key,'score':round(score,6),'fields':fields,'conflicts':conflicts,
                          'sources':[x.to_dict() for x in items]})
    proposals.sort(key=lambda x:x['score'],reverse=True)
    if not proposals:return {'status':'needs_scan' if not (book.title or book.isbn10 or book.isbn13) else 'needs_manual_review','matches':[],'reason':'Keine Treffer.'}
    top=proposals[0]; gap=top['score']-(proposals[1]['score'] if len(proposals)>1 else 0)
    exact=bool(book.isbn10 or book.isbn13) and top['score']==1
    unique=(exact or gap>=.08) and not top['conflicts']
    status='matched' if unique and top['score']>=threshold else 'probable_match' if top['score']>=probable else 'needs_manual_review'
    return {'status':status,'matches':proposals[:20], 'reason':'Eindeutiger Treffer.' if status=='matched' else 'Bestätigung oder Korrektur erforderlich.'}


def apply_match(book,proposal):
    if not isinstance(proposal,dict) or proposal.get('conflicts') or not isinstance(proposal.get('fields'),dict):
        raise ProviderError('Widersprüchlicher oder ungültiger Treffer kann nicht übernommen werden.')
    candidate=deepcopy(book)
    for key,value in proposal['fields'].items():
        if value is not None:setattr(candidate,key,value)
    candidate.provider_matches=deepcopy(proposal['sources'])
    candidate.confidence['overall']=proposal['score']
    candidate.status='matched' if proposal['score']>=.88 else 'probable_match'
    candidate.updated_at=now(); candidate.validate(); return candidate
