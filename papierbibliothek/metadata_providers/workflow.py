from copy import deepcopy

from .base import MetadataRecord, ProviderError
from .cache import MetadataCache
from .matching import apply_match, reconcile
from ..models import now


def search_book(store,project,book_id,providers,cancel,progress,offline=False,
                threshold=.88,auto_apply=False):
    book=next((x for x in project.books if x.book_id==book_id),None)
    if not book:raise ProviderError('Der Buchdatensatz fehlt.')
    stages=[]
    if book.isbn13 or book.isbn10:stages.append({'isbn':book.isbn13 or book.isbn10})
    if book.title and book.author:stages.append({'title':book.title,'author':book.author})
    if book.title:stages.append({'title':book.title,'author':book.author,'publisher':book.publisher})
    stages=[stage for index,stage in enumerate(stages) if stage not in stages[:index]]
    if not stages:raise ProviderError('Für die Suche wird mindestens ISBN oder Titel benötigt.')
    cache=MetadataCache(store); records=[]; errors=[]
    for provider in providers:
        if cancel.is_set():return {'cancelled':True}
        provider_found=[]
        for number,query in enumerate(stages,1):
            if cancel.is_set():return {'cancelled':True}
            progress(f'{provider.name}: Suchstufe {number}/{len(stages)} …')
            cached=cache.get(provider.name,query,offline)
            if cached is not None:
                try: provider_found=[MetadataRecord(**x).validate() for x in cached]
                except (TypeError,ProviderError): provider_found=[];errors.append(provider.name+': ungültiger Cache-Eintrag verworfen.')
            elif offline:
                continue
            else:
                try:
                    provider_found=provider.search(**query)
                    serialized=[x.to_dict() for x in provider_found]
                    try: cache.put(provider.name,query,serialized)
                    except OSError: errors.append(provider.name+': Treffer gefunden, Cache konnte aber nicht gespeichert werden.')
                except ProviderError as exc:
                    errors.append(str(exc));break
            if provider_found:
                records.extend(provider_found);break
        if offline and not provider_found:errors.append(provider.name+': nicht im Cache.')
    if cancel.is_set():return {'cancelled':True}
    result=reconcile(book,records,threshold)
    candidate=deepcopy(project); target=next(x for x in candidate.books if x.book_id==book_id)
    target.provider_matches=result['matches']; target.status=result['status']; target.updated_at=now()
    auto_applied=False
    if auto_apply and result['status']=='matched' and result['matches']:
        applied=apply_match(target,result['matches'][0])
        candidate.books=[applied if x.book_id==book_id else x for x in candidate.books]
        auto_applied=True
    store.save(candidate)
    return {'project':candidate,'metadata_book_id':book_id,'errors':errors,
            'reason':result['reason'],'auto_applied':auto_applied}


def search_books(store,project,book_ids,providers,cancel,progress,offline=False,threshold=.88,pause=.15):
    current=project; errors=[]; searched=0
    for index,book_id in enumerate(book_ids,1):
        if cancel.is_set():break
        progress(f'Buch {index}/{len(book_ids)} wird abgeglichen …')
        try:
            result=search_book(store,current,book_id,providers,cancel,progress,offline,threshold)
        except ProviderError as exc:
            errors.append(str(exc));continue
        if result.get('cancelled'):break
        current=result['project'];searched+=1
        errors.extend(result['errors'])
        if pause and index<len(book_ids) and cancel.wait(pause):break
    return {'project':current,'batch_metadata':True,'searched':searched,'errors':errors,
            'cancelled':cancel.is_set()}
