"""Character routes remain behind the existing local management authentication."""
import re
from .library import CharacterLibrary
from ..brain.memory import MemoryStore
from ..brain.operations import OperationError


def handle(server,post,path,query,data):
    library=CharacterLibrary(getattr(server,'character_root',None),management_db=server.db_path,
                             llm_factory=getattr(server,'character_llm_factory',None))
    if path=='/characters' and not post:return 200,library.catalog()
    if path=='/characters/models' and not post:
        from ..conversation.models import profiles
        return 200,[p.public() for p in profiles().values()]
    if path=='/characters/shared-facts' and not post:
        facts=library.shared_facts()
        return 200,{'facts':facts.list('local-owner'),'audit':facts.audit('local-owner')}
    if path=='/characters/shared-facts' and post:
        try:
            allowed={'key','value','characters','fact_id','revoke'}
            if not isinstance(data,dict) or set(data)-allowed or type(data.get('revoke',False)) is not bool:
                raise ValueError('Invalid request')
            fact_id=library.shared_facts().update('local-owner',**data)
            return 200,{'fact_id':fact_id}
        except (ValueError,TypeError):raise OperationError(422,'invalid_shared_fact') from None
    if path=='/characters/shared-facts/undo' and post:
        try:
            if set(data)!={'fact_id'}:raise ValueError('Invalid request')
            library.shared_facts().undo('local-owner',data['fact_id'])
            return 200,{'undone':True}
        except (ValueError,TypeError):raise OperationError(422,'invalid_shared_fact_undo') from None
    match=re.fullmatch(r'/characters/([a-z][a-z0-9-]{0,39})(/.*)',path)
    if not match:raise OperationError(404,'character_not_found')
    key,route=match.groups()
    try:library.card(key)
    except ValueError:raise OperationError(404,'character_not_found') from None
    if not post and route=='/portrait':return 200,library.portrait(key)
    if not post and route=='/history':return 200,library.history(key)
    if not post and route=='/traces':return 200,library.traces(key)
    if not post and route=='/model':return 200,library.model_profile(key).public()
    if post and route=='/model':
        try:
            if set(data)!={'profile_id'}:raise ValueError('Invalid request')
            return 200,library.select_model(key,data['profile_id'])
        except (ValueError,KeyError,TypeError):raise OperationError(422,'invalid_model_selection') from None
    if post and route=='/chat':
        if set(data)!={'text'} or not isinstance(data['text'],str) or not 1<=len(data['text'].strip())<=4000:
            raise OperationError(422,'invalid_character_message')
        return 200,library.chat(key,data['text'].strip())
    if route.startswith('/config/'):
        rest=route[len('/config'):]
        allowed = (not post and rest in ('/persona','/persona/history','/audit')) or (
            post and rest=='/persona/draft') or (not post and re.fullmatch(r'/operations/\d+',rest)) or (
            post and re.fullmatch(r'/operations/\d+/confirm',rest))
        if not allowed:raise OperationError(403,'character_config_route_forbidden')
        memory=MemoryStore(str(library.config_path(key)),embedder=None)
        try:
            from ..web_api import V1API
            return V1API(server,memory,None).handle(post,rest,query,data)
        finally:memory.close()
    raise OperationError(404,'character_route_not_found')
