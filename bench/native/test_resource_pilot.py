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
    def test_explicit_owned_root_is_forwarded_to_engine(self):
        with patch.object(pilot.runner.Engine, '__init__', return_value=None) as init, \
                patch.object(pilot, 'save'):
            pilot.ResourceEngine('ctrs', 'run', refs(), Path('/results'), fresh_dir=Path('/owned-root'))
        init.assert_called_once_with('ctrs', 'run', fresh_dir=Path('/owned-root'))

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
        pin = pilot.mixed_cycle.PIN['images']['np-v5/api']
        info = {'Architecture': 'arm64', 'RepoDigests': [pins['api']], 'RootFS': {'Layers': pin['diff_ids']}}
        for changed in ({'Architecture': 'amd64'}, {'RepoDigests': []}, {'RootFS': {'Layers': []}}):
            engine = SimpleNamespace(sh=lambda *a, **kw: SimpleNamespace(stdout=json.dumps([info | changed])))
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'installed image identity'):
                pilot.verify_images(engine, pins, Path('.'))

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
        with patch.object(pilot.ci_jobs, 'cleanup') as cleanup:
            pilot.warmup_api(engine, pins['api'])
        owner = commands[2][0][commands[2][0].index('--name') + 1]
        cleanup.assert_called_once_with(engine, owner, owner)
        self.assertEqual(saved[0]['services'], {'api': {'image': pins['api']}, 'db': {'image': pins['postgres']}, 'cache': {'image': pins['redis']}})
        self.assertEqual(commands[0][0][-5:], ['up', '-d', '--no-build', '--pull', 'never'])
        self.assertIn('/run/compose-override.json', commands[0][0])
        self.assertIn('/run/compose-override.json', commands[1][0])
        self.assertEqual(commands[2][0][:3], ['run', '--rm', '--pull=never'])
        self.assertIn(pins['api'], commands[2][0])
        self.assertIn('dev.ctrs.campaign.run=' + owner, commands[2][0])
        self.assertEqual(commands[2][0][commands[2][0].index('--network') + 1], 'none')
        self.assertTrue(commands[0][1]['check'] is False)

    def test_source_mismatch_cleans_only_verified_warmup(self):
        commands = []
        def sh(args, **kwargs):
            commands.append(args)
            if args[0] == 'run':
                return SimpleNamespace(stdout='{}')
            if args[0] == 'inspect':
                owner = commands[0][commands[0].index('--name') + 1]
                return SimpleNamespace(returncode=0, stdout=json.dumps([
                    {'Config': {'Labels': {'dev.ctrs.campaign.run': owner}}}]))
            return SimpleNamespace(returncode=0)
        engine = SimpleNamespace(sh=sh)
        with self.assertRaisesRegex(ValueError, 'API contents differ'):
            pilot.warmup_api(engine, refs()['api'])
        owner = commands[0][commands[0].index('--name') + 1]
        self.assertEqual(commands[1:], [['inspect', owner], ['rm', '-f', owner]])

    def test_warmup_cleanup_rejects_foreign_container(self):
        commands = []
        def sh(args, **kwargs):
            commands.append(args)
            if args[0] == 'run':
                return SimpleNamespace(stdout='{}')
            return SimpleNamespace(returncode=0, stdout=json.dumps([
                {'Config': {'Labels': {'dev.ctrs.campaign.run': 'foreign'}}}]))
        with self.assertRaisesRegex(RuntimeError, 'ownership mismatch'):
            pilot.warmup_api(SimpleNamespace(sh=sh), refs()['api'])
        self.assertEqual([args[0] for args in commands], ['run', 'inspect'])


if __name__ == '__main__':
    unittest.main()
