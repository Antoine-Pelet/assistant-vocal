from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
from core.contexte import ExecutionContext,use
from conversation.manager import ConversationManager
from conversation.turn import ConversationTurn
from security import confirmations


class SharedConversationTests(unittest.TestCase):
    def test_local_and_satellite_use_same_prompt_and_provider(self):
        manager=ConversationManager();provider=Mock(nom='Ollama',hote='http://127.0.0.1:11434')
        provider.repondre.return_value=SimpleNamespace(stop_reason='end',content=[SimpleNamespace(type='text',text='Bonjour.')])
        with patch('core.llm.llm',return_value=provider),patch('core.routage_intentions.decider_prioritaire',return_value=None),patch('core.memoire.contexte',return_value=(1,{})):
            for source in ['local','satellite']:
                ctx=ExecutionContext(source=source,room_id='bureau')
                result=manager.handle(ConversationTurn('Bonjour',ctx))
                self.assertEqual(result['reponse'],'Bonjour.')
                self.assertIn('bureau',provider.repondre.call_args.args[0])
                self.assertIn('Ton nom est Red',provider.repondre.call_args.args[0])
        self.assertEqual(provider.repondre.call_count,2)

    def test_pending_is_shared_implementation_but_isolated_by_session(self):
        from core import registre
        tool=SimpleNamespace(nom='test_shared',confirmation=True,annonce=lambda args:'Je vais agir.',fonction=Mock(return_value='fait'))
        a=ExecutionContext(source='local');b=ExecutionContext(source='satellite')
        manager=ConversationManager()
        decision=SimpleNamespace(type='outil',outil='test_shared',arguments={})
        with patch.object(confirmations,'_EN_ATTENTE',{}),patch.object(registre,'get',return_value=tool),patch.object(registre,'est_autorise',return_value=False),patch('core.routage_intentions.decider_prioritaire',return_value=decision):
            self.assertTrue(manager.handle(ConversationTurn('agir',a))['attente_confirmation'])
            with use(b):self.assertEqual(registre.executer_confirme(),'')
            with use(a):self.assertEqual(registre.executer_confirme(),'fait')
        tool.fonction.assert_called_once()

    def test_satellite_never_inherits_unlocked_local_memory(self):
        manager=ConversationManager();ctx=ExecutionContext(source='satellite')
        with patch('core.memoire.contexte',return_value=(1,{})) as memory:
            manager.refresh(manager.session(ctx),protected=True)
        memory.assert_called_once_with(protegees=False)

    def test_disconnect_drops_history_and_pending(self):
        manager=ConversationManager();ctx=ExecutionContext(source='satellite')
        session=manager.session(ctx);session.history.append({'role':'user','content':'test'})
        manager.close(ctx)
        self.assertEqual(session.history,[]);self.assertEqual(manager._sessions,{})
