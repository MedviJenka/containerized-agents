import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from agent_service.rpc_client import OmpRpcClient


class OmpRpcClientTests(unittest.TestCase):
    def test_runs_prompt_until_terminal_agent_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "fake_omp.py"
            script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys

                    print(json.dumps({"type": "ready", "protocolVersion": 1}), flush=True)
                    for line in sys.stdin:
                        command = json.loads(line)
                        if command["type"] == "new_session":
                            print(json.dumps({"id": command["id"], "type": "response", "command": "new_session", "success": True}), flush=True)
                        elif command["type"] == "prompt":
                            print(json.dumps({"id": command["id"], "type": "response", "command": "prompt", "success": True, "data": {"agentInvoked": True}}), flush=True)
                            print(json.dumps({"type": "agent_end", "messages": [], "isTerminal": False}), flush=True)
                            print(json.dumps({"type": "agent_end", "messages": [], "isTerminal": True}), flush=True)
                        elif command["type"] == "get_last_assistant_text":
                            print(json.dumps({"id": command["id"], "type": "response", "command": "get_last_assistant_text", "success": True, "data": {"text": "finished"}}), flush=True)
                    """
                ),
                encoding="utf-8",
            )

            with OmpRpcClient(command=[sys.executable, str(script)], timeout=5) as client:
                self.assertEqual(client.run("do the work"), "finished")

    def test_fails_when_rpc_command_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "rejecting_omp.py"
            script.write_text(
                "import json, sys\n"
                "print(json.dumps({'type': 'ready'}), flush=True)\n"
                "for line in sys.stdin:\n"
                " command = json.loads(line)\n"
                " print(json.dumps({'id': command['id'], 'type': 'response', 'command': command['type'], 'success': False, 'error': 'rejected'}), flush=True)\n",
                encoding="utf-8",
            )

            with (
                OmpRpcClient(command=[sys.executable, str(script)], timeout=5) as client,
                self.assertRaisesRegex(RuntimeError, "rejected"),
            ):
                client.run("do the work")


if __name__ == "__main__":
    unittest.main()
