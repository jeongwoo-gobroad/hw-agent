"""Resolve chat photo queries against saved names/topics, never guessed identities."""
from datetime import datetime
import re
from . import photos, db

ALIASES = {'people':['사람','인물'], 'animals':['동물','고양이','강아지','개 사진','새 사진'],
           'buildings':['건물','건축','도시','다리','타워','사찰'], 'documents':['서류','문서','영수증'],
           'cards':['카드','신용카드','명함'], 'food':['음식','식사','요리'], 'nature':['자연','풍경','바다','산 사진']}


def requested(message):
    return bool(re.search(r'사진|동영상|라이브\s*포토',message) and re.search(r'찾|검색|보여|모아|몇|개수',message))


def search(message, plan):
    visible_names = [p for p in photos.people() if p['name'] and p['name'] in message]
    topic_message = message
    for person in visible_names: topic_message = topic_message.replace(person['name'], '')
    topics = [key for key,words in ALIASES.items() if any(re.search(r'(?<![가-힣])'+re.escape(word),topic_message) for word in words)]
    topic = topics[0] if topics else plan.get('photo_topic','')
    if topic not in ALIASES: topic = ''
    named = [p for p in photos.people() if p['name'] and p['name'] in message]
    if not named and plan.get('person_name'):
        named = [p for p in photos.people() if p['name']==plan['person_name']]
    if len(named)>1:
        return {'text':'이름이 여러 얼굴 묶음과 일치합니다. 사진 관리에서 이름을 구분해 주세요.', 'photos':[], 'photo_total':0}
    person = named[0]['id'] if named else 0
    unknown = re.search(r'(\S+?)(?:이|가)?\s*(?:나온|찍힌|등장하는)\s*사진', message)
    if not person and not topic and (unknown or plan.get('person_name')):
        return {'text':'그 이름으로 저장된 얼굴 묶음이 없습니다. 사진 관리 → 사람들에서 먼저 이름을 붙여 주세요.', 'photos':[], 'photo_total':0}
    def timestamp(value, end=False):
        try: return datetime.strptime(value,'%Y-%m-%d').timestamp()+(86399 if end else 0)
        except (TypeError,ValueError): return None
    after,before=timestamp(plan.get('after')),timestamp(plan.get('before'),True)
    if after is not None and before is not None and after>before:
        return {'text':'촬영 시작일이 종료일보다 늦습니다. 날짜 범위를 확인해 주세요.','photos':[],'photo_total':0}
    result = photos.items(topic=topic, person=person, after=after,before=before,
                          exclude=any(word in message for word in ['제외','범위 밖']),
                          kind='video' if '동영상' in message else '')
    condition = (named[0]['name']+' · ' if named else '')+(photos.TOPICS[topic][0]+' 주제' if topic else '사진 보관함')
    text=f'{condition}에서 {result["total"]}개를 찾았습니다. 최대 8개를 표시합니다.'
    if result['total']==0: text=condition+'에 일치하는 처리된 사진이 없습니다. 색인 진행 상태와 이름·주제를 확인해 주세요.'
    if not topic and not person and any(word in message for word in ['나온','찍힌','등장']):
        text='현재는 등록된 사람 이름·주제·촬영 날짜로 검색합니다. 사진 관리의 주제 또는 사람 이름을 지정해 주세요.'
        result={'items':[],'total':0}
    return {'text':text,'photos':result['items'][:8],'photo_total':result['total'],
            'photo_filters':{'topic':topic,'person':person,'after':after,'before':before}}
