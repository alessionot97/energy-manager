"""Scheduled commitments, weekdays, per-load conditions, and manual overrides."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import patch
import sys

from test_manager import EnergyManager, Entry, Hass, State


def extra_load(**overrides):
    item = {
        'id': 'ventilation', 'name': 'Ventilation', 'kind': 'switch',
        'entity_id': 'switch.ventilation', 'power_entity': '',
        'watts': 300, 'priority': 4,
        'schedule_enabled': True, 'schedule_start': '16:00', 'schedule_end': '20:00',
        'schedule_inside': 'on', 'schedule_outside': 'off',
        'schedule_weekdays': '0,1,2,3,4,5,6',
        'require_boiler_done': True,
    }
    item.update(overrides)
    return item


def fixtures(load):
    h = Hass()
    h.states['switch.ventilation'] = State('off')
    h.states['sensor.fotovoltaico_pcc_total_power'] = State(-500)
    opt = dict(Entry.options)
    opt['loads'] = [*opt['loads'], load]
    opt['termo_grid_backup'] = False
    e = type('ScheduledEntry', (), {'entry_id':'scheduled', 'data':{}, 'options':opt})()
    return h, EnergyManager(h, e)


async def case_schedule_and_manual():
    h, m = fixtures(extra_load())
    await m.async_initialize()
    m.boiler_done_date = '2026-10-14'  # Wednesday
    with patch.object(sys.modules['homeassistant.util.dt'], 'utcnow',
                      lambda: datetime(2026, 10, 14, 16, 30, tzinfo=timezone.utc)):
        await m.async_tick()
    assert h.states.is_state('switch.ventilation', 'on')  # grid-backed window
    with patch.object(sys.modules['homeassistant.util.dt'], 'utcnow',
                      lambda: datetime(2026, 10, 14, 20, 30, tzinfo=timezone.utc)):
        await m.async_tick()
    assert h.states.is_state('switch.ventilation', 'off')
    with patch.object(sys.modules['homeassistant.util.dt'], 'utcnow',
                      lambda: datetime(2026, 10, 14, 20, 30, tzinfo=timezone.utc)):
        await m.async_set_mode('ventilation', 'on')
        assert h.states.is_state('switch.ventilation', 'on')
        await m.async_set_mode('ventilation', 'off')
        assert h.states.is_state('switch.ventilation', 'off')


def test_schedule_and_manual_override():
    asyncio.run(case_schedule_and_manual())


async def case_weekday_and_condition():
    h, m = fixtures(extra_load(schedule_weekdays='0,1',
                              condition_entity='binary_sensor.presence',
                              condition_state='on'))
    await m.async_initialize()
    m.boiler_done_date = '2026-10-14'
    h.states['binary_sensor.presence'] = State('on')
    with patch.object(sys.modules['homeassistant.util.dt'], 'utcnow',
                      lambda: datetime(2026, 10, 14, 16, 30, tzinfo=timezone.utc)):
        await m.async_tick()
    assert h.states.is_state('switch.ventilation', 'off')  # Wednesday disabled
    h.states['binary_sensor.presence'] = State('off')
    m.loads[-1]['schedule_weekdays'] = '0,1,2,3,4,5,6'
    with patch.object(sys.modules['homeassistant.util.dt'], 'utcnow',
                      lambda: datetime(2026, 10, 14, 16, 30, tzinfo=timezone.utc)):
        await m.async_tick()
    assert h.states.is_state('switch.ventilation', 'off')  # binary condition false


def test_weekday_and_condition_block():
    asyncio.run(case_weekday_and_condition())


def test_cross_midnight_schedule():
    h, m = fixtures(extra_load(schedule_start='22:00', schedule_end='06:00',
                              require_boiler_done=False))
    assert m._scheduled_mode(m.loads[-1], datetime(2026,10,14,23,0))[0] == 'on'
    assert m._scheduled_mode(m.loads[-1], datetime(2026,10,15,1,0))[0] == 'on'
    assert m._scheduled_mode(m.loads[-1], datetime(2026,10,14,15,0))[0] == 'off'
