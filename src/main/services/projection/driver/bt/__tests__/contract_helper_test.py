"""Contract tests — aa_handler.py helper functions.

These tests assert the load-bearing assumptions from §6.5 and M12 that the
hub layer depends on. They test *upstream's* behaviour, not ours.

Guards: §6.5 N10c, M12

Run with:
    cd src/main/services/projection/driver/bt
    pytest __tests__/contract_helper_test.py -v
"""
import json
import os
import sys
from unittest.mock import patch

import pytest

# conftest.py installs dbus/gi stubs before this import runs
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# aa_handler reads env vars at import time; set safe defaults
os.environ.setdefault('LIVI_PORT', '5277')

from aa_handler import _set_wired_phones, _wired_phones  # noqa: E402


class TestSetWiredPhones:
    """_set_wired_phones replaces wholesale (§6.5 N10c — the destructive-setter trap)."""

    def test_replaces_wholesale_not_additive(self):
        """Setting a new list must replace the old set entirely, not merge."""
        _set_wired_phones(json.dumps(['AA:BB:CC:DD:EE:FF', '11:22:33:44:55:66']))
        import aa_handler
        assert aa_handler._wired_phones == {'AA:BB:CC:DD:EE:FF', '11:22:33:44:55:66'}

        _set_wired_phones(json.dumps(['AA:BB:CC:DD:EE:FF']))
        assert aa_handler._wired_phones == {'AA:BB:CC:DD:EE:FF'}
        # The second id must NOT survive the replacement
        assert '11:22:33:44:55:66' not in aa_handler._wired_phones

    def test_empty_string_clears_the_set(self):
        _set_wired_phones(json.dumps(['AA:BB:CC:DD:EE:FF']))
        import aa_handler
        assert len(aa_handler._wired_phones) > 0

        _set_wired_phones('')
        assert aa_handler._wired_phones == set()

    def test_empty_list_clears_the_set(self):
        _set_wired_phones(json.dumps(['AA:BB:CC:DD:EE:FF']))
        _set_wired_phones(json.dumps([]))
        import aa_handler
        assert aa_handler._wired_phones == set()

    def test_uppercases_all_ids(self):
        _set_wired_phones(json.dumps(['aa:bb:cc:dd:ee:ff', 'Inst-001']))
        import aa_handler
        assert aa_handler._wired_phones == {'AA:BB:CC:DD:EE:FF', 'INST-001'}

    def test_filters_out_falsy_values(self):
        _set_wired_phones(json.dumps(['', None, 'AA:BB:CC:DD:EE:FF', 0]))
        import aa_handler
        assert aa_handler._wired_phones == {'AA:BB:CC:DD:EE:FF'}

    def test_invalid_json_clears_the_set(self):
        _set_wired_phones(json.dumps(['AA:BB:CC:DD:EE:FF']))
        _set_wired_phones('not valid json')
        import aa_handler
        assert aa_handler._wired_phones == set()


# M12: _is_admission_blocked and _dock_policy do not exist in upstream yet.
# These tests are skipped until the hub layer adds them.
class TestIsAdmissionBlocked:
    """_is_admission_blocked is true for a dock-denied id AND still true for a wired id (M12)."""

    @pytest.mark.skip(reason='M12: _is_admission_blocked does not exist in upstream yet')
    def test_blocks_dock_denied_id(self):
        from aa_handler import _is_admission_blocked
        assert _is_admission_blocked('DOCK-DENIED-ID') is True

    @pytest.mark.skip(reason='M12: _is_admission_blocked does not exist in upstream yet')
    def test_wired_id_is_also_blocked(self):
        """A wired phone must be blocked from the wireless AP admission."""
        from aa_handler import _is_admission_blocked
        _set_wired_phones(json.dumps(['AA:BB:CC:DD:EE:FF']))
        assert _is_admission_blocked('AA:BB:CC:DD:EE:FF') is True


class TestDockPolicy:
    """_dock_policy closes after the grace deadline (N10a)."""

    @pytest.mark.skip(reason='M12: _dock_policy does not exist in upstream yet')
    def test_closes_after_grace_deadline(self):
        from aa_handler import _dock_policy
        # After the grace deadline, the dock policy should close
        assert _dock_policy(grace_expired=True) == 'closed'
