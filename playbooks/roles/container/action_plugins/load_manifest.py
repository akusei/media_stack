# from __future__ import (absolute_import, division, print_function)
# __metaclass__ = type

import fnmatch
import os
from os import path, walk
import re

import ansible.constants as C
from ansible.errors import AnsibleError
from ansible.module_utils.common.yaml import yaml_load
from ansible.module_utils.six import string_types
from ansible.module_utils.common.text.converters import to_native, to_text
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible.utils.vars import combine_vars


display = Display()


class ActionModule(ActionBase):
    TRANSFERS_FILES = False
    _requires_connection = False

    RESERVED_SETTINGS = ['directories', 'targets']

    def _set_dir_defaults(self):
        if not self.depth:
            self.depth = 0

        if self.files_matching:
            self.matcher = re.compile(r'{0}'.format(self.files_matching))
        else:
            self.matcher = None

        if not self.ignore_files:
            self.ignore_files = list()

        if isinstance(self.ignore_files, string_types):
            self.ignore_files = self.ignore_files.split()

        elif isinstance(self.ignore_files, dict):
            return {
                'failed': True,
                'message': '{0} must be a list'.format(self.ignore_files)
            }

    def _set_args(self):
        """ Set instance variables based on the arguments that were passed """

        self.hash_behaviour = self._task.args.get('hash_behaviour', None)
        self.return_results_as_name = self._task.args.get('name', None)
        self.source_dir = self._task.args.get('dir', None)
        self.source_file = self._task.args.get('file', None)
        if not self.source_dir and not self.source_file:
            self.source_file = self._task.args.get('_raw_params')
            if self.source_file:
                self.source_file = self.source_file.rstrip('\n')

        self.depth = self._task.args.get('depth', None)
        self.files_matching = self._task.args.get('files_matching', None)
        self.ignore_unknown_extensions = self._task.args.get('ignore_unknown_extensions', False)
        self.ignore_files = self._task.args.get('ignore_files', None)
        self.valid_extensions = self._task.args.get('extensions', self.VALID_FILE_EXTENSIONS)

        # convert/validate extensions list
        if isinstance(self.valid_extensions, string_types):
            self.valid_extensions = list(self.valid_extensions)
        if not isinstance(self.valid_extensions, list):
            raise AnsibleError('Invalid type for "extensions" option, it must be a list')

    def _load_users(self, manifest):
        all_groups = []
        users = []
        for user in manifest.get('users', []):
            user_group = user.get('group', user['user'])
            user_groups = user.get('groups')
            all_groups.append(user_group)
            user['group'] = user_group
            users.append(user)
            if user_groups is not None:
                all_groups.extend(user_groups)
                user['groups'] = user_groups
            elif len(user_groups or []) <= 0 and 'groups' in user:
                del user['groups']

        return list(set(all_groups)), users

    # def _load_users(self, manifest):
    #     all_groups = []
    #     users = []
    #     for user in manifest.get('users', []):
    #         user_group = user.get('group', user['user'])
    #         all_groups.append(user_group)
    #         if isinstance(user_group, str):
    #             user['groups'].append(groups)
    #             all_groups.append(groups)
    #         elif isinstance(groups, list) and len(groups) > 0:
    #             user['groups'].extend(groups)
    #             all_groups.extend(groups)
    #
    #         all_groups.append(username)
    #         user = {'user': username, 'groups': [username]}
    #         users.append(user)
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
        if 'path' not in self._task.args:
            raise AnsibleError("Missing required argument 'path'")

        container_path = self._task.args['path']
        manifest_file = os.path.join(container_path, 'settings.yml')
        with open(manifest_file, 'r') as f:
            config = yaml_load(f)

        # for key, value in config.items():
        #     if key not in self.RESERVED_SETTINGS:
        #         combine_vars(task_vars.get(key, None), value, merge='replace')

        manifest = self._templar.template(config, fail_on_undefined=True)

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

        result = super(ActionModule, self).run(task_vars=task_vars or {})

        result['targets'] = sorted_dirs
        result['groups'] = groups
        result['users'] = users

        if 'targets' in manifest:
            del manifest['targets']
        if 'users' in manifest:
            del manifest['users']
        if 'permissions' in manifest:
            del manifest['permissions']

        result['ansible_facts'] = manifest

        return result

        # """ Load yml files recursively from a directory.
        # """
        # del tmp  # tmp no longer has any effect
        #
        # if task_vars is None:
        #     task_vars = dict()
        #
        # self.show_content = True
        # self.included_files = []
        #
        # # Validate arguments
        # if 'path' not in self._task.args:
        #     raise AnsibleError("Missing required argument 'path'")
        #
        # dirs = 0
        # files = 0
        # for arg in self._task.args:
        #     if arg in self.VALID_DIR_ARGUMENTS:
        #         dirs += 1
        #     elif arg in self.VALID_FILE_ARGUMENTS:
        #         files += 1
        #     elif arg in self.VALID_ALL:
        #         pass
        #     else:
        #         raise AnsibleError('{0} is not a valid option in include_vars'.format(to_native(arg)))
        #
        # if dirs and files:
        #     raise AnsibleError("You are mixing file only and dir only arguments, these are incompatible")
        #
        # # set internal vars from args
        # self._set_args()
        #
        # results = dict()
        # failed = False
        # if self.source_dir:
        #     self._set_dir_defaults()
        #     self._set_root_dir()
        #     if not path.exists(self.source_dir):
        #         failed = True
        #         err_msg = ('{0} directory does not exist'.format(to_native(self.source_dir)))
        #     elif not path.isdir(self.source_dir):
        #         failed = True
        #         err_msg = ('{0} is not a directory'.format(to_native(self.source_dir)))
        #     else:
        #         for root_dir, filenames in self._traverse_dir_depth():
        #             failed, err_msg, updated_results = (self._load_files_in_dir(root_dir, filenames))
        #             if failed:
        #                 break
        #             results.update(updated_results)
        # else:
        #     try:
        #         self.source_file = self._find_needle('vars', self.source_file)
        #         failed, err_msg, updated_results = (
        #             self._load_files(self.source_file)
        #         )
        #         if not failed:
        #             results.update(updated_results)
        #
        #     except AnsibleError as e:
        #         failed = True
        #         err_msg = to_native(e)
        #
        # if self.return_results_as_name:
        #     scope = dict()
        #     scope[self.return_results_as_name] = results
        #     results = scope
        #
        # result = super(ActionModule, self).run(task_vars=task_vars)
        #
        # if failed:
        #     result['failed'] = failed
        #     result['message'] = err_msg
        # elif self.hash_behaviour is not None and self.hash_behaviour != C.DEFAULT_HASH_BEHAVIOUR:
        #     merge_hashes = self.hash_behaviour == 'merge'
        #     for key, value in results.items():
        #         old_value = task_vars.get(key, None)
        #         results[key] = combine_vars(old_value, value, merge=merge_hashes)
        #
        # result['ansible_included_var_files'] = self.included_files
        # result['ansible_facts'] = results
        # result['_ansible_no_log'] = not self.show_content
        #
        # return result

    def _set_root_dir(self):
        if self._task._role:
            if self.source_dir.split('/')[0] == 'vars':
                path_to_use = (
                    path.join(self._task._role._role_path, self.source_dir)
                )
                if path.exists(path_to_use):
                    self.source_dir = path_to_use
            else:
                path_to_use = (
                    path.join(
                        self._task._role._role_path, 'vars', self.source_dir
                    )
                )
                self.source_dir = path_to_use
        else:
            if hasattr(self._task._ds, '_data_source'):
                current_dir = (
                    "/".join(self._task._ds._data_source.split('/')[:-1])
                )
                self.source_dir = path.join(current_dir, self.source_dir)

    def _log_walk(self, error):
        self._display.vvv('Issue with walking through "%s": %s' % (to_native(error.filename), to_native(error)))

    def _traverse_dir_depth(self):
        """ Recursively iterate over a directory and sort the files in
            alphabetical order. Do not iterate pass the set depth.
            The default depth is unlimited.
        """
        current_depth = 0
        sorted_walk = list(walk(self.source_dir, onerror=self._log_walk, followlinks=True))
        sorted_walk.sort(key=lambda x: x[0])
        for current_root, current_dir, current_files in sorted_walk:
            current_depth += 1
            if current_depth <= self.depth or self.depth == 0:
                current_files.sort()
                yield (current_root, current_files)
            else:
                break

    def _ignore_file(self, filename):
        """ Return True if a file matches the list of ignore_files.
        Args:
            filename (str): The filename that is being matched against.

        Returns:
            Boolean
        """
        for file_type in self.ignore_files:
            try:
                if re.search(r'{0}$'.format(file_type), filename):
                    return True
            except Exception:
                err_msg = 'Invalid regular expression: {0}'.format(file_type)
                raise AnsibleError(err_msg)
        return False

    def _is_valid_file_ext(self, source_file):
        """ Verify if source file has a valid extension
        Args:
            source_file (str): The full path of source file or source file.
        Returns:
            Bool
        """
        file_ext = path.splitext(source_file)
        return bool(len(file_ext) > 1 and file_ext[-1][1:] in self.valid_extensions)

    def _load_files(self, filename, validate_extensions=False):
        """ Loads a file and converts the output into a valid Python dict.
        Args:
            filename (str): The source file.

        Returns:
            Tuple (bool, str, dict)
        """
        results = dict()
        failed = False
        err_msg = ''
        if validate_extensions and not self._is_valid_file_ext(filename):
            failed = True
            err_msg = ('{0} does not have a valid extension: {1}'.format(to_native(filename), ', '.join(self.valid_extensions)))
        else:
            b_data, show_content = self._loader._get_file_contents(filename)
            data = to_text(b_data, errors='surrogate_or_strict')

            self.show_content = show_content
            data = self._loader.load(data, file_name=filename, show_content=show_content)
            if not data:
                data = dict()
            if not isinstance(data, dict):
                failed = True
                err_msg = ('{0} must be stored as a dictionary/hash'.format(to_native(filename)))
            else:
                self.included_files.append(filename)
                results.update(data)

        return failed, err_msg, results

    def _load_files_in_dir(self, root_dir, var_files):
        """ Load the found yml files and update/overwrite the dictionary.
        Args:
            root_dir (str): The base directory of the list of files that is being passed.
            var_files: (list): List of files to iterate over and load into a dictionary.

        Returns:
            Tuple (bool, str, dict)
        """
        results = dict()
        failed = False
        err_msg = ''
        for filename in var_files:
            stop_iter = False
            # Never include main.yml from a role, as that is the default included by the role
            if self._task._role:
                if path.join(self._task._role._role_path, filename) == path.join(root_dir, 'vars', 'main.yml'):
                    stop_iter = True
                    continue

            filepath = path.join(root_dir, filename)
            if self.files_matching:
                if not self.matcher.search(filename):
                    stop_iter = True

            if not stop_iter and not failed:
                if self.ignore_unknown_extensions:
                    if path.exists(filepath) and not self._ignore_file(filename) and self._is_valid_file_ext(filename):
                        failed, err_msg, loaded_data = self._load_files(filepath, validate_extensions=True)
                        if not failed:
                            results.update(loaded_data)
                else:
                    if path.exists(filepath) and not self._ignore_file(filename):
                        failed, err_msg, loaded_data = self._load_files(filepath, validate_extensions=True)
                        if not failed:
                            results.update(loaded_data)

        return failed, err_msg, results