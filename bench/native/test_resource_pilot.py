import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from diagnostics import resource_pilot as pilot


def refs():
    result = {name.rsplit('/', 1)[1]: 'example/image@' + pin['manifest']
              for name, pin in pilot.mixed_cycle.PIN['images'].items()}
    result['worker'] = 'example/worker@' + pilot.mixed_cycle.WORKER['worker']['manifest']
    return result


class ResourcePins(unittest.TestCase):
    def test_missing_arguments_and_invalid_refs_fail_before_engine_access(self):
        with patch('sys.argv', ['resource_pilot']), contextlib.redirect_stderr(io.StringIO()), \
             patch.object(pilot.runner, 'find_docker') as docker:
            with self.assertRaises(SystemExit) as error:
                pilot.main()
            self.assertEqual(error.exception.code, 2)
            docker.assert_not_called()
        for invalid in ('{', '[]', json.dumps(refs() | {'redis': 'redis:latest'}),
                        json.dumps(refs() | {'redis': 'example/image@sha256:' + '0' * 64}),
                        json.dumps(refs() | {'api': 1})):
            with self.subTest(invalid=invalid), patch.object(Path, 'read_text', return_value=invalid):
                with self.assertRaises((ValueError, TypeError)):
                    pilot.load_refs(Path('refs.json'))
        with self.assertRaises(OSError):
            pilot.load_refs(Path('/missing/resource-refs.json'))

    def test_installed_image_identity_rejects_digest_layers_and_architecture(self):
        pins = refs()
        pin = pilot.mixed_cycle.PIN['images']['np-v2/api']
        info = {'Architecture': 'arm64', 'RepoDigests': [pins['api']], 'RootFS': {'Layers': pin['diff_ids']}}
        for changed in ({'Architecture': 'amd64'}, {'RepoDigests': []}, {'RootFS': {'Layers': []}}):
            engine = SimpleNamespace(sh=lambda *a, **kw: SimpleNamespace(stdout=json.dumps([info | changed])))
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'installed image identity'):
                pilot.verify_images(engine, pins, Path('.'))

    def test_cleanup_is_project_scoped(self):
        commands = []
        engine = SimpleNamespace(sh=lambda args, **kwargs: commands.append(args) or SimpleNamespace(stdout='owned-id\n' if args[0] == 'ps' else ''))
        pilot.runner.compose_down(engine, 'owned-project')
        self.assertEqual(commands[0][-3:], ['down', '-v', '--remove-orphans'])
        self.assertIn('name=owned-project', commands[1])
        self.assertEqual(commands[2], ['rm', '-f', 'owned-id'])

    def test_running_binary_identity(self):
        identity = {'required_processes': [{'role': 'daemon', 'executable': {'sha256': 'other'}}]}
        with self.assertRaisesRegex(ValueError, 'running daemon'):
            pilot.verify_binary(identity, 'expected')
        identity['required_processes'][0]['executable']['sha256'] = 'expected'
        pilot.verify_binary(identity, 'expected')

    def test_compose_and_warmup_use_pins_without_build_or_pull(self):
        pins = refs()
        saved = []
        commands = []
        with patch.object(pilot.runner.Engine, '__init__', return_value=None), \
             patch.object(pilot, 'save', side_effect=lambda path, value: saved.append(value)):
            engine = pilot.ResourceEngine('ctrs', 'run', pins, Path('/run'))
        engine.sh = lambda args, **kwargs: commands.append((args, kwargs)) or SimpleNamespace(stdout=json.dumps(pilot.mixed_cycle.PIN['api_files_sha256']))
        engine.compose('project', ['up', '-d'])
        engine.compose('project', ['ps', '-q', 'api'])
        pilot.warmup_api(engine, pins['api'])
        self.assertEqual(saved[0]['services'], {'api': {'image': pins['api']}, 'db': {'image': pins['postgres']}, 'cache': {'image': pins['redis']}})
        self.assertEqual(commands[0][0][-5:], ['up', '-d', '--no-build', '--pull', 'never'])
        self.assertIn('/run/compose-override.json', commands[0][0])
        self.assertIn('/run/compose-override.json', commands[1][0])
        self.assertEqual(commands[2][0][:4], ['run', '--rm', '--pull=never', pins['api']])
        self.assertTrue(commands[0][1]['check'] is False)


if __name__ == '__main__':
    unittest.main()
