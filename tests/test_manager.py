"""Exercise live-action decisions against a minimal Home Assistant substitute."""
import asyncio
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import patch

pkgpath = Path(__file__).parents[1] / 'custom_components' / 'energy_manager'


def _module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


for name in ["homeassistant", "homeassistant.core", "homeassistant.helpers",
             "homeassistant.helpers.event", "homeassistant.helpers.storage", "homeassistant.util", "homeassistant.util.dt"]:
    _module(name)

sys.modules['homeassistant.core'].HomeAssistant = type('HomeAssistant', (), {})
sys.modules['homeassistant.helpers.event'].async_track_time_interval = lambda *a: lambda: None


class Store:
    def __init__(self, *args):
        self.saved = {}

    async def async_load(self):
        return self.saved

    async def async_save(self, data):
        self.saved = data


sys.modules['homeassistant.helpers.storage'].Store = Store
sys.modules['homeassistant.util.dt'].utcnow = lambda: datetime(2026, 10, 14, 11, 0, tzinfo=timezone.utc)
sys.modules['homeassistant.util.dt'].as_local = lambda dt: dt
sys.modules['homeassistant.util'].dt = sys.modules['homeassistant.util.dt']

pkg = types.ModuleType('energy_manager')
pkg.__path__ = [str(pkgpath)]
sys.modules['energy_manager'] = pkg
for name in ['const', 'policy', 'manager']:
    spec = importlib.util.spec_from_file_location('energy_manager.'+name, pkgpath / (name+'.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

from energy_manager.manager import EnergyManager
from energy_manager.const import default_loads


class State:
    def __init__(self, state, unit='W'):
        self.state = str(state)
        self.attributes = {'unit_of_measurement':unit}


class States(dict):
    def get(self, entity):
        return super().get(entity)

    def is_state(self, entity, expected):
        state=self.get(entity)
        return bool(state and state.state==expected)


class Services:
    def __init__(self, hass):
        self.hass=hass
        self.calls=[]

    def has_service(self, domain, service):
        return True

    async def async_call(self, domain, service, data, blocking=False, target=None):
        self.calls.append((domain,service,data,target))
        if service in ('turn_on','turn_off'):
            self.hass.states[data['entity_id']] = State('on' if service=='turn_on' else 'off')
        elif domain=='input_number' and service=='set_value':
            self.hass.states[data['entity_id']] = State(data['value'],'A')


class Hass:
    def __init__(self):
        self.states=States({
            'sensor.fotovoltaico_pcc_total_power':State(1600),
            'sensor.fotovoltaico_battery_power':State(1800),
            'sensor.boiler_power':State(0),
            'sensor.wallbox_power':State(0),
            'input_number.corrente_wallbox':State(6,'A'),
            'input_number.wallbox_kw_per_amp':State(0.69),
            'switch.boiler':State('off'),
            'switch.prese_lavanderia':State('off'),
            'input_boolean.wallbox':State('off')
        })
        self.services=Services(self)


class Entry:
    entry_id='test'
    data={}
    options={'loads': default_loads(),
             'switch_on_stable_s':0, 'switch_off_stable_s':0,
             'switch_min_on_s':0, 'switch_min_off_s':0,
             'ev_min_on_s':0,'ev_min_off_s':0,
             'boiler_force_at':'15:30','boiler_cutoff':'16:00',
             'termo_grid_backup':False}


async def _exercise():
    h=Hass()
    m=EnergyManager(h, Entry())
    await m.async_initialize()
    await m.async_tick()
    # First pass establishes stable start; second pass switches on.
    await m.async_tick()
    assert h.states.is_state('switch.boiler','on'), m.snapshot
    assert not h.states.is_state('switch.prese_lavanderia','on')
    # Meter export falls because boiler uses solar; it must STAY ON.
    h.states['sensor.fotovoltaico_pcc_total_power']=State(400)
    h.states['sensor.boiler_power']=State(1200)
    await m.async_tick()
    assert h.states.is_state('switch.boiler','on'), m.snapshot
    # Boiler must switch off after cutoff despite continued sunshine.
    with patch.object(sys.modules['homeassistant.util.dt'], 'utcnow',
                      lambda: datetime(2026,10,14,16,5,tzinfo=timezone.utc)):
        await m.async_tick()
    assert h.states.is_state('switch.boiler','off'), m.snapshot
    # Manual ON overrides 16:00 cutoff. Manual OFF overrides it again.
    await m.async_set_mode('boiler','on')
    assert h.states.is_state('switch.boiler','on')
    await m.async_set_mode('boiler','off')
    assert h.states.is_state('switch.boiler','off')
    # EV manual ON uses REST service, not just helper toggle.
    await m.async_set_mode('wallbox','on')
    assert ('rest_command','evse_start',{},None) in h.services.calls
    assert h.states.is_state('input_boolean.wallbox','on')
    await m.async_set_mode('wallbox','off')
    assert ('rest_command','evse_stop',{},None) in h.services.calls


def test_live_actuation_model():
    asyncio.run(_exercise())

async def _exercise_termo_grid_fallback():
    h=Hass()
    h.states['sensor.fotovoltaico_pcc_total_power']=State(-300)
    h.states['sensor.fotovoltaico_battery_power']=State(0)
    opts=dict(Entry.options)
    opts['termo_grid_backup']=True
    e=type('EntryWithGrid',(),{'entry_id':'grid','data':{},'options':opts})()
    m=EnergyManager(h,e)
    await m.async_initialize()
    m.boiler_done_date='2026-10-14'
    with patch.object(sys.modules['homeassistant.util.dt'],'utcnow',
                      lambda: datetime(2026,10,14,16,30,tzinfo=timezone.utc)):
        await m.async_tick()
    assert h.states.is_state('switch.prese_lavanderia','on')
    assert h.states.is_state('switch.boiler','off')


def test_towel_warmer_fallback_to_grid_after_boiler_ready():
    asyncio.run(_exercise_termo_grid_fallback())
