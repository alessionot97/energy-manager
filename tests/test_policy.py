"""Test the calculations without a Home Assistant installation."""
from datetime import datetime
from pathlib import Path
import importlib.util

path = Path(__file__).parents[1] / "custom_components" / "energy_manager" / "policy.py"
spec = importlib.util.spec_from_file_location("policy", path)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def test_battery_charging_is_not_surplus():
    assert policy.net_surplus(370, 2030) == 370


def test_battery_discharging_is_not_free_power():
    assert policy.net_surplus(100, -500) == -400


def test_consumption_avoids_self_shutdown():
    assert policy.recompute_capacity(300, 2000, 1200) == 1500


def test_ev_minimum_real_three_phase():
    assert policy.current_target(3200, 690, 6, 16, 250) == 0
    assert policy.current_target(4400, 690, 6, 16, 250) == 6
    assert policy.current_target(12000, 690, 6, 16, 250) == 16


def test_boiler_cutoff():
    assert not policy.after(datetime(2026, 10, 14, 15, 59), "16:00")
    assert policy.after(datetime(2026, 10, 14, 16), "16:00")


def test_time_window():
    assert policy.within(datetime(2026, 10, 14, 17), "16:00", "20:00")
    assert not policy.within(datetime(2026, 10, 14, 20), "16:00", "20:00")
