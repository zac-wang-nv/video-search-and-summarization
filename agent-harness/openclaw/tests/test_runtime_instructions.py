# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run instruction snippets without a checkout; optionally use the real image.

VSS_TEST_IMAGE=<cached image> python3 -m unittest discover -s agent-harness/openclaw/tests
"""

import os
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(os.environ.get("VSS_TEST_SOURCE_ROOT", Path(__file__).resolve().parents[3]))
IMAGE = os.environ.get("VSS_TEST_IMAGE")
WORKSPACE = ROOT / "agent-harness/openclaw/workspace/_nemoclaw"
SKILL = ROOT / "skills/operations/vss-ask-video/SKILL.md"


def bash_block(path, heading):
    section = path.read_text().split(heading, 1)[1]
    return re.search(r"```bash\n(.*?)\n```", section, re.S).group(1)


class EnvironmentInstructions(unittest.TestCase):
    def exports(self, values):
        result = subprocess.run(
            [
                "bash",
                "--noprofile",
                "--norc",
                "-c",
                bash_block(WORKSPACE / "ENV.md", "## Exports")
                + '\nprintf "%s\\n" "$VSS_PUBLIC_URL" "$HOST_IP"',
            ],
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", **values},
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.splitlines()

    def test_explicit_origin_and_host_survive_session_setup(self):
        self.assertEqual(
            self.exports(
                {
                    "VSS_PUBLIC_URL": "https://selected.example:8443",
                    "VSS_GATEWAY_ORIGIN": "https://different.example:9443",
                    "HOST_IP": "operator-host.example",
                }
            ),
            ["https://selected.example:8443", "operator-host.example"],
        )

    def test_harness_origin_is_used_without_public_url(self):
        self.assertEqual(
            self.exports({"VSS_GATEWAY_ORIGIN": "http://selected.example:80"}),
            ["http://selected.example:80", "host.openshell.internal"],
        )

    def test_no_origin_is_invented(self):
        self.assertEqual(self.exports({}), ["", "host.openshell.internal"])

    def test_explicit_empty_origin_and_host_remain_empty(self):
        self.assertEqual(
            self.exports(
                {
                    "VSS_PUBLIC_URL": "",
                    "VSS_GATEWAY_ORIGIN": "http://selected.example:80",
                    "HOST_IP": "",
                }
            ),
            ["", ""],
        )

    def test_notebook_can_still_fill_export(self):
        rendered, count = re.subn(
            r"^export VSS_PUBLIC_URL=.*$",
            'export VSS_PUBLIC_URL="https://selected.example:443"',
            (WORKSPACE / "ENV.md").read_text(),
            flags=re.M,
        )
        self.assertEqual(count, 1)
        self.assertIn('export VSS_PUBLIC_URL="https://selected.example:443"', rendered)


@unittest.skipUnless(IMAGE, "Set VSS_TEST_IMAGE to exercise the installed image CLI")
class InstalledCliInstructions(unittest.TestCase):
    def run_image(self, script):
        return subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--pull=never",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=128",
                "--memory=512m",
                "--cpus=2",
                "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=16m",
                "--env=OPENCLAW_CHILD_OOM_SCORE_ADJ=0",
                "--entrypoint=/bin/bash",
                "-i",
                IMAGE,
                "--noprofile",
                "--norc",
                "-s",
            ],
            input=script,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_both_bootstraps_and_video_selector_use_baked_cli(self):
        skill_bootstrap = bash_block(SKILL, "### Bootstrap the CLI once")
        repo_bootstrap = bash_block(ROOT / "AGENTS.md", "### Setup")
        selector = bash_block(SKILL, "**Path A").split("# Exit 6", 1)[0]
        result = self.run_image(
            "set -eu\n"
            'test ! -e "$HOME/video-search-and-summarization"\n'
            "test ! -e /usr/local/src/vss/.git\n"
            'test "$(command -v vss)" = /usr/local/bin/vss\n'
            'git() { echo "unexpected git" >&2; exit 97; }\n'
            'uv() { echo "unexpected uv" >&2; exit 98; }\n'
            + skill_bootstrap
            + "\n"
            + repo_bootstrap
            + "\n"
            + selector
            + '\n"${VSS[@]}" vlm run --help\n'
            + '\n"${VSS[@]}" vios --help\n'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--media-url", result.stdout)
        self.assertNotIn("unexpected", result.stderr)

    def test_missing_baked_cli_stops_before_development_fallback(self):
        blocks = [
            bash_block(SKILL, "### Bootstrap the CLI once"),
            bash_block(ROOT / "AGENTS.md", "### Setup"),
            bash_block(SKILL, "**Path A").split("# Exit 6", 1)[0],
        ]
        for block in blocks:
            with self.subTest(block=block.splitlines()[0]):
                result = self.run_image(
                    "test -x /usr/local/bin/nemoclaw-start || exit 96\n"
                    "command() { return 1; }\n"
                    'uv() { echo "unexpected uv" >&2; exit 98; }\n'
                    + block
                    + '\necho "unexpected continuation"\n'
                )
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("Baked VSS CLI missing", result.stderr)
                self.assertNotIn("unexpected", result.stdout + result.stderr)

    def test_oom_default_disables_installed_runtime_proc_write(self):
        dockerfile = (ROOT / "agent-harness/openclaw/Dockerfile").read_text()
        self.assertRegex(dockerfile, r"(?m)^ENV OPENCLAW_CHILD_OOM_SCORE_ADJ=0$")
        result = self.run_image("""node --input-type=module <<'JS'
import { t as prepare } from '/usr/local/lib/node_modules/openclaw/dist/linux-oom-score-eO5nXmjv.js';
const options = { platform: 'linux', shellAvailable: () => true };
const baseline = prepare('/bin/bash', ['-c', 'true'], { ...options, env: {} });
const configured = prepare('/bin/bash', ['-c', 'true'], { ...options, env: process.env });
if (!baseline.wrapped || configured.wrapped || configured.command !== '/bin/bash') {
  throw new Error('OpenClaw child OOM-score override did not disable wrapping');
}
console.log('OpenClaw child OOM-score write disabled');
JS
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("write disabled", result.stdout)


if __name__ == "__main__":
    unittest.main()
