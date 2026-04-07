"""Tests for start.py — launcher that starts uvicorn backend and Vite frontend."""

import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import start


class TestStartMain:
    """Tests for start.main() using mocked subprocess.Popen."""

    def _make_proc(self, poll_sequence=None):
        """Build a mock Popen process.

        poll_sequence: list of return values for successive poll() calls.
        Defaults to [None, None, 0] so the while-loop runs twice then exits.
        """
        proc = MagicMock()
        if poll_sequence is None:
            poll_sequence = [None, None, 0]
        proc.poll.side_effect = poll_sequence
        return proc

    def test_main_spawns_two_processes(self):
        """main() must call Popen exactly twice — backend and frontend."""
        backend = self._make_proc([0])
        frontend = self._make_proc([0])

        with patch("start.subprocess.Popen", side_effect=[backend, frontend]) as mock_popen, \
             patch("start.time.sleep"):
            start.main()

        assert mock_popen.call_count == 2

    def test_main_backend_uses_uvicorn(self):
        """Backend Popen call must include 'uvicorn' in the command."""
        backend = self._make_proc([0])
        frontend = self._make_proc([0])

        with patch("start.subprocess.Popen", side_effect=[backend, frontend]) as mock_popen, \
             patch("start.time.sleep"):
            start.main()

        backend_cmd = mock_popen.call_args_list[0][0][0]
        assert "uvicorn" in backend_cmd

    def test_main_frontend_uses_npm(self):
        """Frontend Popen call must include 'run' and 'dev' in the command."""
        backend = self._make_proc([0])
        frontend = self._make_proc([0])

        with patch("start.subprocess.Popen", side_effect=[backend, frontend]) as mock_popen, \
             patch("start.time.sleep"):
            start.main()

        frontend_cmd = mock_popen.call_args_list[1][0][0]
        assert "dev" in frontend_cmd

    def test_main_terminates_processes_on_exit(self):
        """main() must call terminate() on every process in the finally block."""
        backend = self._make_proc([0])
        frontend = self._make_proc([0])

        with patch("start.subprocess.Popen", side_effect=[backend, frontend]), \
             patch("start.time.sleep"):
            start.main()

        backend.terminate.assert_called_once()
        frontend.terminate.assert_called_once()

    def test_main_waits_after_terminate(self):
        """main() must call wait() on every process after terminate()."""
        backend = self._make_proc([0])
        frontend = self._make_proc([0])

        with patch("start.subprocess.Popen", side_effect=[backend, frontend]), \
             patch("start.time.sleep"):
            start.main()

        backend.wait.assert_called_once()
        frontend.wait.assert_called_once()

    def test_main_keyboard_interrupt_triggers_cleanup(self):
        """KeyboardInterrupt during the wait loop must still clean up all processes."""
        backend = self._make_proc()
        frontend = self._make_proc()

        # Make time.sleep raise KeyboardInterrupt to simulate Ctrl+C
        with patch("start.subprocess.Popen", side_effect=[backend, frontend]), \
             patch("start.time.sleep", side_effect=KeyboardInterrupt):
            start.main()

        backend.terminate.assert_called_once()
        frontend.terminate.assert_called_once()

    def test_main_kills_process_when_terminate_raises(self):
        """If terminate() raises an exception, kill() must be called instead."""
        backend = self._make_proc([0])
        frontend = self._make_proc([0])

        # Make backend.terminate raise so the except branch runs kill()
        backend.terminate.side_effect = OSError("process already dead")

        with patch("start.subprocess.Popen", side_effect=[backend, frontend]), \
             patch("start.time.sleep"):
            start.main()

        backend.kill.assert_called_once()
        # Frontend still terminates normally
        frontend.terminate.assert_called_once()

    def test_main_win32_uses_npm_cmd(self):
        """On win32 the npm command must be 'npm.cmd'."""
        backend = self._make_proc([0])
        frontend = self._make_proc([0])

        with patch("start.subprocess.Popen", side_effect=[backend, frontend]) as mock_popen, \
             patch("start.time.sleep"), \
             patch("start.sys.platform", "win32"):
            start.main()

        frontend_cmd = mock_popen.call_args_list[1][0][0]
        assert frontend_cmd[0] == "npm.cmd"

    def test_main_non_win32_uses_npm(self):
        """On non-win32 the npm command must be 'npm' (not 'npm.cmd')."""
        backend = self._make_proc([0])
        frontend = self._make_proc([0])

        with patch("start.subprocess.Popen", side_effect=[backend, frontend]) as mock_popen, \
             patch("start.time.sleep"), \
             patch("start.sys.platform", "linux"):
            start.main()

        frontend_cmd = mock_popen.call_args_list[1][0][0]
        assert frontend_cmd[0] == "npm"

    def test_main_sleep_called_while_all_procs_alive(self):
        """time.sleep(1) must be called each iteration of the polling loop."""
        backend = self._make_proc([None, None, 0])
        frontend = self._make_proc([None, None, 0])

        with patch("start.subprocess.Popen", side_effect=[backend, frontend]), \
             patch("start.time.sleep") as mock_sleep:
            start.main()

        # sleep was called at least once during the wait loop
        assert mock_sleep.call_count >= 1
        mock_sleep.assert_called_with(1)

    def test_main_exits_when_process_terminates(self):
        """Loop exits as soon as any process returns a non-None poll() value."""
        # poll() returns 0 immediately → loop body never executes sleep
        backend = self._make_proc([0])
        frontend = self._make_proc([0])

        with patch("start.subprocess.Popen", side_effect=[backend, frontend]), \
             patch("start.time.sleep") as mock_sleep:
            start.main()

        # With both returning 0 on first poll, sleep should not be called
        mock_sleep.assert_not_called()

    def test_main_backend_cwd_is_root(self):
        """Backend process must be started with cwd=ROOT."""
        backend = self._make_proc([0])
        frontend = self._make_proc([0])

        with patch("start.subprocess.Popen", side_effect=[backend, frontend]) as mock_popen, \
             patch("start.time.sleep"):
            start.main()

        backend_kwargs = mock_popen.call_args_list[0][1]
        assert backend_kwargs["cwd"] == start.ROOT

    def test_main_frontend_cwd_is_frontend_dir(self):
        """Frontend process must be started with cwd=FRONTEND."""
        backend = self._make_proc([0])
        frontend = self._make_proc([0])

        with patch("start.subprocess.Popen", side_effect=[backend, frontend]) as mock_popen, \
             patch("start.time.sleep"):
            start.main()

        frontend_kwargs = mock_popen.call_args_list[1][1]
        assert frontend_kwargs["cwd"] == start.FRONTEND
