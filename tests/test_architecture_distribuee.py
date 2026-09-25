"""Contrats locaux et isolation de contexte, sans appareil, micro ou serveur réseau."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core import config, registre
from core.contexte import ExecutionContext, bind, current, use
from core.devices import Device, DeviceError, Devices
from core.evenements import Event, LocalEventBus
from core.maison import devices, room_for_satellite
from integrations import hue
from services import AudioData
from services.existing import ExistingSTT, ExistingTTS, ExistingLLM
from tools import lumieres


def contexte(room, session=None):
    return ExecutionContext(user_id="test", session_id=session or room,
                            room_id=room, satellite_id="red_"+room, device_id="red_"+room)


def lumiere(ident, integration="fake", address="external-1"):
    return Device(ident, "light", integration, address,
                  frozenset({"turn_on", "turn_off", "set_brightness", "set_color"}), ident)


class ContextTests(unittest.TestCase):
    def test_nesting_restored_even_after_error(self):
        before=current()
        with use(contexte("salon")):
            with self.assertRaises(ValueError), use(contexte("bureau")):
                self.assertEqual(current().room_id,"bureau")
                raise ValueError()
            self.assertEqual(current().room_id,"salon")
        self.assertEqual(current(),before)

    def test_worker_receives_origin_context(self):
        with ThreadPoolExecutor(2) as pool:
            with use(contexte("salon")):
                first=pool.submit(bind(current))
            with use(contexte("bureau")):
                second=pool.submit(bind(current))
            self.assertEqual(first.result().room_id,"salon")
            self.assertEqual(second.result().room_id,"bureau")

    def test_async_requests_do_not_mix_contexts(self):
        async def worker(room):
            with use(contexte(room)):
                await asyncio.sleep(0)
                return current().room_id
        async def run():
            return await asyncio.gather(worker("salon"),worker("bureau"))
        self.assertEqual(asyncio.run(run()),["salon","bureau"])

    def test_default_room_has_no_guess(self):
        with patch.object(config,'_CONFIG',{}):
            self.assertIsNone(current().room_id)
            self.assertEqual(current().device_id,'main_pc')

    def test_satellite_context_uses_server_room_and_distinct_session(self):
        from core.satellite import _Session,_contexte_session
        one,two=_Session(),_Session()
        one.satellite=two.satellite='Red_salon'
        one.piece=two.piece='ancienne_piece'
        with patch.object(config,'_CONFIG',{'rooms':{'salon':{'satellite':'Red_salon'}}}):
            c=_contexte_session(one)
            self.assertEqual(c.room_id,'salon')
            self.assertEqual(c.user_id,'anonymous')
            self.assertNotEqual(c.session_id,_contexte_session(two).session_id)

    def test_ambiguous_satellite_is_rejected(self):
        with patch.object(config,'_CONFIG',{'rooms':{'a':{'satellite':'s'},'b':{'satellite':'s'}}}):
            with self.assertRaises(DeviceError):room_for_satellite('s')

    def test_real_local_entry_accepts_context_without_hardware(self):
        import jarvis14 as red
        seen=[]
        with patch.object(red,'_traiter_memoire_confidentielle',side_effect=lambda *a:seen.append(current()) or True):
            red.traiter(None,None,[],None,None,question='ouvre une zone',context=contexte('bureau'))
        self.assertEqual(seen,[contexte('bureau')])


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.adapter=Mock();self.adapter.execute.return_value=True
        self.bus=LocalEventBus();self.events=[];self.bus.subscribe(self.events.append)
        self.catalogue=Devices([lumiere('salon.light'),lumiere('bureau.light')],
            {'salon':{'devices':{'light':'salon.light'}},'bureau':{'devices':{'light':'bureau.light'}}},
            {'fake':self.adapter},self.bus)

    def test_ici_resolves_origin_not_server(self):
        for room in ('salon','bureau'):
            with use(contexte(room)):
                d=self.catalogue.resolve('ici')
                self.catalogue.turn_off(d.id)
                self.assertEqual(d.id,room+'.light')
                self.assertEqual(self.adapter.execute.call_args.args[-1].room_id,room)
        self.assertEqual([e.context.room_id for e in self.events],['salon','bureau'])

    def test_missing_room_never_acts_on_all_devices(self):
        with use(ExecutionContext()),self.assertRaisesRegex(DeviceError,'quelle pièce'):
            self.catalogue.resolve('ici')
        self.adapter.execute.assert_not_called()

    def test_business_tool_uses_independent_adapter(self):
        with patch.object(lumieres,'devices',return_value=self.catalogue),use(contexte('salon')):
            self.assertIn('eteinte',lumieres.allumer_lumiere('ici',False))
        d,action,args,ctx=self.adapter.execute.call_args.args
        self.assertEqual((d.id,action,args,ctx.room_id),('salon.light','turn_off',{},'salon'))

    def test_replace_adapter_without_changing_module(self):
        replacement=Mock();replacement.execute.return_value=True
        self.catalogue.register_integration('fake',replacement)
        self.catalogue.turn_on('salon.light')
        replacement.execute.assert_called_once()
        self.adapter.execute.assert_not_called()

    def test_unknown_device_and_capability_fail_closed(self):
        with self.assertRaises(DeviceError):self.catalogue.turn_on('absent')
        with self.assertRaises(DeviceError):self.catalogue.perform('salon.light','unlock')
        self.adapter.execute.assert_not_called()

    def test_uninstalled_integration_is_explicit(self):
        c=Devices([lumiere('salon.light','home_assistant')])
        with self.assertRaisesRegex(DeviceError,'non installée'):
            c.turn_on('salon.light')

    def test_dotted_config_ids_and_room_links(self):
        conf={'devices':{'salon.light':{'integration':'hue','address':'3'}},
              'rooms':{'salon':{'devices':{'light':'salon.light'}}}}
        with patch.object(config,'_CONFIG',conf):
            d=devices().resolve('salon')
        self.assertEqual((d.id,d.address),('salon.light','3'))

    def test_invalid_room_mapping_has_no_legacy_fallback(self):
        fallback=Mock()
        c=Devices(rooms={'salon':{'devices':{'light':'missing'}}},legacy_resolver=fallback)
        with self.assertRaises(DeviceError):c.resolve('salon')
        fallback.assert_not_called()

    def test_group_targets_configured_lights(self):
        with patch.object(lumieres,'devices',return_value=self.catalogue):
            result=lumieres.regler_luminosite('toutes',25)
        self.assertIn('salon.light',result);self.assertIn('bureau.light',result)
        self.assertEqual(self.adapter.execute.call_count,2)

    def test_failed_adapter_does_not_report_success_or_expose_error(self):
        self.adapter.execute.side_effect=RuntimeError('secret-token')
        with self.assertRaisesRegex(DeviceError,'injoignable') as failure:
            self.catalogue.turn_on('salon.light')
        self.assertNotIn('secret-token',str(failure.exception))
        self.assertEqual(self.events,[])

    def test_contextual_route_does_not_depend_on_alexa(self):
        from core.routage_intentions import decider_prioritaire
        with patch.object(config,'_CONFIG',{'rooms':{'salon':{}}}):
            route=decider_prioritaire('Éteins la lumière ici')
        self.assertEqual(route.outil,'allumer_lumiere')
        self.assertEqual(route.arguments,{'piece':'ici','allumer':False})


class HueCompatibilityTests(unittest.TestCase):
    def test_legacy_discovery_and_group_translation(self):
        with patch.dict(hue._PIECES_HUE,{'salon':('3','Salon')},clear=True), \
                patch.object(hue,'_hue_requete',return_value=[{'success':{}}]) as request:
            c=Devices(integrations={'hue':hue.HueIntegration()},legacy_resolver=hue.HueIntegration().resolve_legacy)
            c.perform(c.resolve('le salon'),'set_brightness',{'percent':50})
        request.assert_called_once_with('groups/3/action','PUT',{'on':True,'bri':127})

    def test_zero_brightness_and_named_color(self):
        d=lumiere('salon.light','hue','3');driver=hue.HueIntegration()
        with patch.object(hue,'_hue_requete',return_value=[{'success':{}}]) as request:
            driver.execute(d,'set_brightness',{'percent':0},contexte('salon'))
            self.assertEqual(request.call_args.args[-1],{'on':False})
            driver.execute(d,'set_color',{'color':'bleu'},contexte('salon'))
            self.assertEqual(request.call_args.args[-1],{'on':True,'hue':46920,'sat':254})

    def test_empty_hue_response_is_not_success(self):
        with patch.object(hue,'_hue_requete',return_value=[]):
            self.assertFalse(hue.HueIntegration().execute(lumiere('x','hue'),'turn_on',{},contexte('salon')))


class EventTests(unittest.TestCase):
    def test_portable_envelope_and_payload_snapshot(self):
        payload={'target_device_id':'salon.light'}
        e=Event.create('device.changed',payload,contexte('salon'))
        payload['secret']='must not follow'
        decoded=json.loads(e.to_json())
        for key in ('source','satellite_id','room_id','user_id','session_id','timestamp','payload','event_id','schema_version'):
            self.assertIn(key,decoded)
        self.assertNotIn('secret',decoded['payload'])
        e.payload['new']='also isolated'
        self.assertNotIn('new',e.payload)

    def test_no_python_objects_or_nan_in_transport(self):
        for payload in ({'object':object()},{'number':float('nan')}):
            with self.assertRaises((TypeError,ValueError)):Event.create('bad',payload)

    def test_one_bad_listener_does_not_break_action_or_other_listener(self):
        bus=LocalEventBus();got=[]
        bus.subscribe(Mock(side_effect=RuntimeError('private')))
        unsubscribe=bus.subscribe(got.append)
        event=Event.create('test')
        bus.publish(event);unsubscribe();bus.publish(event)
        self.assertEqual(got,[event]);self.assertEqual(bus.delivery_errors,2)


class ServiceTests(unittest.TestCase):
    def test_stt_receives_data_not_microphone_and_zeroes_work_buffer(self):
        captured=[]
        def transcribe(samples,**kwargs):
            captured.append(samples)
            self.assertEqual(current().room_id,'bureau')
            return [SimpleNamespace(text='bonjour')],None
        result=ExistingSTT(SimpleNamespace(transcribe=transcribe)).transcribe(AudioData(b'\xff\x7f'*8000),contexte('bureau'))
        self.assertEqual(result,'bonjour');self.assertFalse(captured[0].any())

    def test_tts_returns_pcm_without_playing_on_server(self):
        p=SimpleNamespace(synthetiser=lambda text:([1,-2,3],24000))
        audio=ExistingTTS(p).synthesize('bonjour',contexte('bureau'))
        self.assertEqual(audio,AudioData(b'\x01\x00\xfe\xff\x03\x00',24000))
        self.assertIsNone(ExistingTTS(SimpleNamespace(synthetiser=lambda _:None)).synthesize('a',contexte('bureau')))

    def test_llm_contract_preserves_provider_and_scopes_context(self):
        before=current();provider=Mock()
        provider.repondre.side_effect=lambda *args: current()
        self.assertEqual(ExistingLLM(provider).respond('s',[],[],contexte('bureau')),contexte('bureau'))
        self.assertEqual(current(),before)

    def test_invalid_audio_format_is_rejected(self):
        with self.assertRaises(ValueError):AudioData(b'\x00')
        with self.assertRaises(ValueError):AudioData(b'',sample_rate=0)
        with self.assertRaises(ValueError):ExistingSTT(Mock()).transcribe(AudioData(b'',48000),current())


class ConfirmationContextTests(unittest.TestCase):
    def test_one_session_cannot_confirm_other_session(self):
        o=SimpleNamespace(nom='test',annonce=None,fonction=lambda:current().room_id)
        with patch.object(registre,'_EN_ATTENTE',{}):
            with use(contexte('salon')):
                registre.mettre_en_attente(o,{})
            with use(contexte('bureau')):
                self.assertIsNone(registre.annonce_en_attente())
                self.assertEqual(registre.executer_confirme(),'')
                registre.mettre_en_attente(o,{})
                self.assertEqual(registre.executer_confirme(),'bureau')
            # Même session, origine spatiale changée : conserve la cible proposée.
            with use(replace(contexte('salon'),room_id='autre')):
                self.assertEqual(registre.executer_confirme(),'salon')
                self.assertEqual(registre.executer_confirme(),'')


if __name__=='__main__':unittest.main()
