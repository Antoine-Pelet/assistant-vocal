"""Contrats publics, permissions et ajout de modules sans modification du coeur."""
import ast
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core import registre
from core.capabilities import CapabilityRegistry, CapabilityRequest
from core.capability_errors import CapabilityExecutionError
from core.contexte import ExecutionContext, use
from core.evenements import LocalEventBus
from core.legacy_tools import LegacyToolAdapter
from core.module import ModuleManifest
from core.module_manager import ModuleAPI, ModuleManager
from security import confirmations

ROOT = Path(__file__).resolve().parents[1]


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        self.tools_patch = patch.dict(registre._REGISTRE, {}, clear=True)
        self.tools_patch.start()
        self.wait_patch = patch.object(confirmations, '_EN_ATTENTE', {})
        self.wait_patch.start()
        self.registry = CapabilityRegistry()
        runtime = SimpleNamespace(capabilities=self.registry, events=LocalEventBus())
        self.api = ModuleAPI(runtime, ModuleManifest('testing', '1', 'Tests', '', name='Test'), {})

    def tearDown(self):
        self.api.close()
        self.wait_patch.stop()
        self.tools_patch.stop()

    def action(self, function, level='N1'):
        return self.api.capability(function, name='testing.action', description='Test public',
                                   security_level=level, aliases=('alias_action',),
                                   announcement=lambda args: 'Je vais agir.')

    def test_aliases_share_metadata_security_and_execution(self):
        cap = self.action(lambda text: text.upper())
        self.assertIs(self.registry.resolve('alias_action'), cap)
        self.assertIs(self.registry.resolve('testing_action'), cap)
        self.assertEqual(self.registry.execute('alias_action', {'text':'bonjour'}), 'BONJOUR')
        self.assertEqual(cap.metadata()['owner'], 'testing')
        self.assertEqual(cap.metadata()['security_level'], 'N1')

    def test_n3_never_runs_before_confirmation_even_with_persistent_authorization(self):
        function = Mock(return_value='fait')
        self.action(function, 'N3')
        with patch('security.authorization.est_autorise', return_value=True):
            self.registry.execute('alias_action')
            function.assert_not_called()
            self.assertEqual(confirmations.annonce_en_attente(), 'Je vais agir.')
            self.assertEqual(confirmations.executer_confirme(), 'fait')
        function.assert_called_once()
        self.assertEqual(confirmations.executer_confirme(), '')

    def test_n2_saved_authorization_applies_only_to_local_endpoint(self):
        function = Mock(return_value='fait')
        self.action(function, 'N2')
        with patch('security.authorization.est_autorise', return_value=True):
            with use(ExecutionContext(source='local')):
                self.assertEqual(self.registry.execute('testing.action'), 'fait')
            with use(ExecutionContext(source='satellite', session_id='remote')):
                self.registry.execute('testing.action')
                self.assertIsNotNone(confirmations.annonce_en_attente())
        function.assert_called_once()

    def test_module_stop_revokes_pending_and_resolved_capabilities(self):
        function = Mock(return_value='fait')
        cap = self.action(function, 'N3')
        cap.execute()
        self.api.close()
        self.assertIsNone(self.registry.resolve('alias_action'))
        self.assertNotEqual(confirmations.executer_confirme(), 'fait')
        function.assert_not_called()

    def test_exception_is_isolated_without_exposing_private_details(self):
        self.action(Mock(side_effect=RuntimeError('private-value')))
        with self.assertRaises(CapabilityExecutionError) as raised:
            self.registry.execute('testing.action')
        self.assertNotIn('private-value', str(raised.exception))
        self.api.capability(lambda: 'ok', name='testing.healthy', description='Healthy')
        self.assertEqual(self.registry.execute('testing.healthy'), 'ok')

    def test_bad_arguments_do_not_execute(self):
        called = []
        self.action(lambda required: called.append(required))
        for arguments in ({}, {'unknown': 1}, []):
            with self.assertRaises(CapabilityExecutionError):
                self.registry.execute('testing.action', arguments)
        self.assertEqual(called, [])

    def test_alias_collision_does_not_replace_registered_action(self):
        cap = self.action(lambda: 'original')
        with self.assertRaises(ValueError):
            self.api.capability(lambda: 'replacement', name='testing.other',
                                description='Other', aliases=('alias_action',))
        self.assertIs(self.registry.resolve('alias_action'), cap)

    def test_legacy_tools_keep_same_permissions(self):
        function = Mock(return_value='ok')
        registre.outil('old_tool', 'Old', permission_level='N3')(function)
        self.registry.legacy = LegacyToolAdapter(self.registry)
        self.registry.execute('old_tool')
        function.assert_not_called()
        self.assertEqual(confirmations.executer_confirme(), 'ok')

    def test_claimed_disabled_module_cannot_fall_back_to_legacy(self):
        def old(): return 'must not run'
        old.__module__ = 'tools.migrated'
        registre.outil('old_tool', 'Old')(old)
        self.registry.legacy = LegacyToolAdapter(self.registry)
        self.registry.claimed_tool_modules.add('migrated')
        self.assertIsNone(self.registry.resolve('old_tool'))

    def test_old_register_tool_api_is_also_executable(self):
        self.api.register_tool(lambda: 'ok', name='old_extension', description='Old extension')
        self.assertEqual(self.registry.execute('old_extension'), 'ok')

    def test_tool_execution_preserves_history_with_protected_memory_context(self):
        from conversation.manager import ConversationManager, Output
        self.action(lambda: 'fait')
        manager = ConversationManager()
        session = manager.session()
        session.memory_signature = (True, 'protected-context')
        session.history[:] = [{'role':'user','content':'agir'},
                              {'role':'assistant','content':[{'type':'tool_use','id':'call'}]}]
        before = list(session.history)
        runtime = SimpleNamespace(capabilities=self.registry, start=lambda:None)
        block = SimpleNamespace(type='tool_use', name='testing.action', input={}, id='call')
        with patch('assistant_vocal.runtime.runtime', runtime):
            result = manager.execute_tools(session,[block],Output(manager,session))
        self.assertEqual(result[0]['content'], 'fait')
        self.assertEqual(session.history, before)
        self.assertEqual(session.memory_signature, (True, 'protected-context'))


class ModuleAdditionTests(unittest.TestCase):
    def test_new_directory_exposes_intent_execution_and_admin_status(self):
        import modules
        source = '''from core.module import RedModule
from core.capabilities import CapabilityRequest
class Module(RedModule):
    def register(self, api):
        api.capability(lambda: "module ajouté", name="addition.hello", description="Test")
        api.route(lambda text, ctx: CapabilityRequest("addition.hello") if text == "bonjour addition" else None)
'''
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)/'addition'; folder.mkdir()
            (folder/'__init__.py').write_text('',encoding='utf8')
            (folder/'module.py').write_text(source,encoding='utf8')
            (folder/'manifest.json').write_text(json.dumps({'id':'addition','name':'Module ajouté','version':'1.2','description':'Test'}),encoding='utf8')
            broken = Path(temp)/'broken';broken.mkdir();(broken/'manifest.json').write_text('{invalid',encoding='utf8')
            runtime = SimpleNamespace(capabilities=CapabilityRegistry(),events=LocalEventBus(), started=True)
            manager = ModuleManager(runtime,temp,{'addition':{'enabled':True}})
            runtime.modules = manager
            with patch.object(modules,'__path__',[*modules.__path__,temp]):
                importlib.invalidate_caches()
                try:
                    manager.start()
                    request=runtime.capabilities.route('bonjour addition',ExecutionContext())
                    self.assertEqual(runtime.capabilities.execute(request.name,request.arguments),'module ajouté')
                    with patch('assistant_vocal.runtime.runtime',runtime):
                        from interfaces.admin.service import _modules
                        status = next(m for m in _modules()['modules'] if m['id']=='addition')
                    self.assertEqual((status['name'],status['version'],status['status'],status['capability_count']),('Module ajouté','1.2','ACTIVE',1))
                    self.assertEqual(manager.health()['broken']['status'],'ERROR')
                finally:
                    manager.stop()
                    for name in ('modules.addition','modules.addition.module'):sys.modules.pop(name,None)
            self.assertIsNone(runtime.capabilities.resolve('addition.hello'))

    def test_conversation_and_runtime_have_no_business_imports_or_decision_switch(self):
        for file in ('conversation/manager.py','assistant_vocal/runtime.py','assistant_vocal/app.py','audio/local.py'):
            text=(ROOT/file).read_text(encoding='utf8')
            tree=ast.parse(text)
            imports=[]
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):imports.append(node.module or '')
                if isinstance(node, ast.Import):imports.extend(a.name for a in node.names)
            self.assertFalse(any(n.startswith(('tools.', 'modules.hermes','modules.vision','modules.computer')) for n in imports),file)
            self.assertNotIn('decision.type',text,file)

    def test_astra_explicit_intent_requires_n3_confirmation(self):
        from assistant_vocal.runtime import runtime
        from tools import astra_pc
        runtime.start()
        with patch.object(confirmations,'_EN_ATTENTE',{}), patch.object(astra_pc,'executer_controle',return_value='terminé') as act:
            request=runtime.capabilities.route('Utilise Astra pour ouvrir les paramètres audio',ExecutionContext())
            self.assertEqual(request.name,'computer.execute_action')
            runtime.capabilities.execute(request.name,request.arguments)
            act.assert_not_called()
            self.assertIsNotNone(confirmations.annonce_en_attente())
            self.assertEqual(confirmations.executer_confirme(),'terminé')
            act.assert_called_once()

    def test_demo_hello_can_be_added_with_only_its_configuration(self):
        runtime=SimpleNamespace(capabilities=CapabilityRegistry(),events=LocalEventBus())
        runtime.capabilities.publish('events.local',runtime.events,'test')
        manager=ModuleManager(runtime,ROOT/'modules',{'demo':{'enabled':True}})
        try:
            manager.start()
            self.assertEqual(runtime.capabilities.execute('demo.hello'),'Bonjour depuis le module de démonstration.')
            self.assertEqual(runtime.capabilities.route('bonjour module démo',ExecutionContext()).name,'demo.hello')
        finally:manager.stop()


if __name__ == '__main__':unittest.main()
