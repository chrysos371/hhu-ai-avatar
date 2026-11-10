"""A role has its own approved persona and owner conversation. No global active role."""
import base64
import json
from pathlib import Path
import sqlite3
import time
import uuid
from ..brain.admin_store import AdminStore
from ..brain.memory import MemoryStore, _database_lock
from ..conversation.engine import ConversationService
from ..conversation.protocol import TurnRequest

PROJECT = Path(__file__).resolve().parents[3]
CARDS = json.loads(Path(__file__).with_name('catalog.json').read_text())
CARD_MAP = {card['id']:card for card in CARDS}


class CharacterLibrary:
    def __init__(self, root=None, *, management_db=None, llm_factory=None):
        self.root = Path(root) if root is not None else PROJECT/'data/characters'
        self.management_db = management_db
        self.llm_factory = llm_factory

    def card(self, key):
        if key not in CARD_MAP:raise ValueError('Unknown character')
        return CARD_MAP[key]

    def directory(self, key):
        self.card(key)
        folder = self.root/'roles'/key
        if ((self.root/'roles').is_symlink() or folder.is_symlink()
                or not folder.resolve().is_relative_to(self.root.resolve())):
            raise ValueError('Invalid character directory')
        return folder

    def config_path(self, key):
        folder=self.directory(key)
        folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        path=folder/'persona.db'
        if path.is_symlink():raise ValueError('Invalid character database')
        with _database_lock(path):
            memory=MemoryStore(str(path),embedder=None)
            try:AdminStore(memory).migrate(self.card(key)['persona'])
            finally:memory.close()
        path.chmod(0o600)
        return path

    def art_index(self):
        path=self.root/'art-index.json'
        if not path.is_file():return {}
        return json.loads(path.read_text())

    def catalog(self):
        from ..config import config
        art=self.art_index()
        return [{'id':c['id'],'name':c['name'],'description':c['description'],
                 'accent':c['accent'],'has_portrait':bool(art.get(c['id'])),
                 'art': {k:v for k,v in (art.get(c['id']) or {}).items()
                         if k in ('creators','source_url','archive_url','license')},
                 'backend_model': self.model_profile(c['id']).model, 'model_profile': self.model_profile(c['id']).id,
                 'persona_origin':'项目自定义初始人设，可编辑；不是作者官方设定'} for c in CARDS]

    def portrait(self,key):
        self.card(key)
        info=self.art_index().get(key)
        if not info:return {'data_url':None}
        if info['file']!=key+'.jpg':raise ValueError('Invalid art path')
        folder=self.root/'art';path=folder/info['file']
        if folder.is_symlink() or path.is_symlink():raise ValueError('Invalid art path')
        if path.stat().st_size>1048576:raise ValueError('Portrait too large')
        raw=path.read_bytes()
        if not raw.startswith(b'\xff\xd8'):raise ValueError('Invalid portrait')
        return {'data_url':'data:image/jpeg;base64,'+base64.b64encode(raw).decode()}

    def history(self,key):
        path=self.directory(key)/'conversation/memory.db'
        if not path.is_file():return []
        if path.is_symlink() or path.parent.is_symlink():raise ValueError('Invalid conversation')
        conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)
        conn.row_factory=sqlite3.Row
        try:
            rows=conn.execute("SELECT id,role,content,created_at FROM memory_messages WHERE role IN ('user','assistant') ORDER BY id DESC LIMIT 80").fetchall()
            return [dict(r) for r in reversed(rows)]
        finally:conn.close()

    def traces(self, key):
        path=self.directory(key)/'conversation/memory.db'
        if not path.exists(): return []
        if path.is_symlink() or path.parent.is_symlink(): raise ValueError('Invalid conversation')
        conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)
        try:
            return [json.loads(r[0]) for r in conn.execute('SELECT data FROM qq_turn_traces ORDER BY created_at DESC LIMIT 40')]
        finally: conn.close()

    def model_profile(self, key):
        from ..conversation.models import profiles
        path = self.directory(key)/'model.json'
        if path.is_symlink(): raise ValueError('Invalid model selection')
        selected = json.loads(path.read_text())['profile_id'] if path.exists() else 'default'
        return profiles()[selected]

    def select_model(self, key, profile_id):
        from ..conversation.models import profiles
        if profile_id not in profiles(): raise ValueError('Unknown model profile')
        folder = self.directory(key)
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        from ..lab.common import atomic_text
        atomic_text(folder/'model.json', json.dumps({'profile_id':profile_id}))
        return self.model_profile(key).public()

    def shared_facts(self):
        from ..conversation.shared_memory import SharedFacts
        if self.root.is_symlink(): raise ValueError('Invalid character root')
        return SharedFacts(self.root/'shared-facts.db')

    def chat(self,key,text):
        path=self.config_path(key)
        directory=self.directory(key)/'conversation'
        if directory.is_symlink() or (directory/'memory.db').is_symlink():raise ValueError('Invalid conversation')
        # Preserve pre-refactor conversation keys; channel identity is now explicit.
        message=TurnRequest('web-character','web-character','private','local-owner',key,uuid.uuid4().hex,text,time.time(), storage_namespace='qq')
        with _database_lock(directory/'memory.db'):
            from ..conversation.models import create_llm
            profile_id = self.model_profile(key).id
            factory = self.llm_factory or (lambda: create_llm(profile_id))
            engine=ConversationService(management_db=self.management_db,persona_db=path,llm_factory=factory,
                                       shared_facts=self.shared_facts(), owner_id='local-owner', character_id=key,
                                       owns_llm=self.llm_factory is None)
            reply=engine.respond(message,directory)
            conn=sqlite3.connect(directory/'memory.db')
            try:
                row=conn.execute('SELECT data FROM qq_turn_traces WHERE receipt_key=?',(message.receipt_key,)).fetchone()
                trace=json.loads(row[0]) if row else {}
            finally:conn.close()
        return {'reply':reply,'character_id':key,'trace':trace}
