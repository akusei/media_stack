# from __future__ import (absolute_import, division, print_function)
# __metaclass__ = type

import fnmatch
import os

from ansible.errors import AnsibleError
from ansible.module_utils.common.yaml import yaml_load
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display


display = Display()


class ActionModule(ActionBase):
    TRANSFERS_FILES = False
    _requires_connection = False

    def _load_users(self, manifest):
        all_groups = []
        users = []
        for user in manifest.get('users', []):
            user["group"] = user.get("group", user["user"])

            all_groups.append(user["group"])
            all_groups.extend(user.get("groups", []))

            users.append(user)

        return list(set(all_groups)), users

    # def _load_users(self, manifest):
    #     all_groups = []
    #     users = []
    #     for user in manifest.get('users', []):
    #         user_group = user.get('group', user['user'])
    #         user_groups = user.get('groups')
    #         all_groups.append(user_group)
    #         user['group'] = user_group
    #         users.append(user)
    #         if user_groups is not None:
    #             all_groups.extend(user_groups)
    #             user['groups'] = user_groups
    #         elif len(user_groups or []) <= 0 and 'groups' in user:
    #             del user['groups']
    #
    #     return list(set(all_groups)), users

    def _resolve_permissions(self, manifest, file_records):
        for perm in manifest.get('permissions', []):
            for pattern in perm.get('paths', []):
                root = pattern.split(os.sep)[0]
                entry = [x['dest'] for x in manifest.get('targets', []) if x.get('src') == root]
                if len(entry) != 0:
                    pattern = pattern.replace(root, entry[0])
                display.v(f'testing pattern {pattern}')
                match = fnmatch.filter([x.get('path', x.get('dest')) for x in file_records], pattern)
                if len(match) == 0:
                    continue

                for m in match:
                    copy = {**perm}
                    if 'paths' in copy:
                        del copy['paths']
                    record = [x for x in file_records if x.get('path', x.get('dest')) == m][0]
                    if record['type'] in ['file', 'template']:
                        record['dest'] = record['dest'].rstrip('.j2')
                    if record['type'] in ['file', 'template'] and 'dir_mode' in copy:
                        del copy['dir_mode']
                    record.update({
                        **copy,
                        'match_pattern': pattern
                    })

    def run(self, tmp=None, task_vars=None):
        result = super(ActionModule, self).run(task_vars=task_vars or {})

        if 'path' not in self._task.args:
            raise AnsibleError("Missing required argument 'path'")

        container_path = self._task.args['path']
        manifest_file = os.path.join(container_path, 'settings.yml')
        # self._templar.available_variables = task_vars
        with open(manifest_file, 'r') as f:
            manifest = self._templar.template(yaml_load(f), fail_on_undefined=False)

        # validate manifest here
        # import json
        # display.display(json.dumps(manifest, indent=2))

        directories = []
        for target in manifest.get('targets', []):
            if 'src' not in target:
                directories.append(
                    {
                        'path': target['dest'],
                        'type': 'dir',
                        'depth': 0
                    }
                )
                continue

            src_dir = os.path.join(container_path, target['src'])
            if not os.path.exists(src_dir):
                raise AnsibleError(f"root directory {target['src']} not found")

            for root, _, files in os.walk(src_dir, followlinks=True):
                for file in files:
                    directories.append(
                        {
                            'target': target['src'],
                            'type': 'template' if str(file).endswith('.j2') else 'file',
                            'src': os.path.join(root, file),
                            'dest': os.path.join(root.replace(src_dir, target['dest']), file),
                            'depth': 0
                        }
                    )
                dest = str(root).replace(src_dir, target['dest'])
                directories.append(
                    {
                        'target': target['src'],
                        'type': 'dir',
                        'path': dest,
                        'depth': len(dest.split(os.sep))
                    }
                )

        self._resolve_permissions(manifest, directories)
        sorted_dirs = sorted(directories, key=lambda x: x['depth'])

        groups, users = self._load_users(manifest)

        result['targets'] = sorted_dirs
        result['groups'] = groups
        result['users'] = users
        result['stack'] = manifest['stack']

        import json
        display.display(json.dumps(result, indent=2))

        return result

    # def run(self, tmp=None, task_vars=None):
    #     if 'path' not in self._task.args:
    #         raise AnsibleError("Missing required argument 'path'")
    #
    #     container_path = self._task.args['path']
    #     manifest_file = os.path.join(container_path, 'settings.yml')
    #     with open(manifest_file, 'r') as f:
    #         manifest = self._templar.template(yaml_load(f), fail_on_undefined=True)
    #
    #     # validate manifest here
    #
    #     directories = []
    #     for target in manifest.get('targets', []):
    #         if 'src' not in target:
    #             directories.append(
    #                 {
    #                     'path': target['dest'],
    #                     'type': 'dir',
    #                     'depth': 0
    #                 }
    #             )
    #             continue
    #
    #         src_dir = os.path.join(container_path, target['src'])
    #         if not os.path.exists(src_dir):
    #             raise AnsibleError(f"root directory {target['src']} not found")
    #
    #         for root, _, files in os.walk(src_dir, followlinks=True):
    #             for file in files:
    #                 directories.append(
    #                     {
    #                         'target': target['src'],
    #                         'type': 'template' if str(file).endswith('.j2') else 'file',
    #                         'src': os.path.join(root, file),
    #                         'dest': os.path.join(root.replace(src_dir, target['dest']), file),
    #                         'depth': 0
    #                     }
    #                 )
    #             dest = str(root).replace(src_dir, target['dest'])
    #             directories.append(
    #                 {
    #                     'target': target['src'],
    #                     'type': 'dir',
    #                     'path': dest,
    #                     'depth': len(dest.split(os.sep))
    #                 }
    #             )
    #
    #     self._resolve_permissions(manifest, directories)
    #     sorted_dirs = sorted(directories, key=lambda x: x['depth'])
    #
    #     groups, users = self._load_users(manifest)
    #
    #     result = super(ActionModule, self).run(task_vars=task_vars or {})
    #
    #     result['targets'] = sorted_dirs
    #     result['groups'] = groups
    #     result['users'] = users
    #     result['stack'] = manifest['stack']
    #
    #     return result
