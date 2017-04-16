#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import sys
import os
import os.path
import argparse
import warnings

import flask

from . import app, compat
from .compat import PY_LEGACY, getdebug
from .transform.glob import translate


class PluginAction(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        warned = '%s_warning' % self.dest
        if ',' in value and not getattr(namespace, warned, False):
            setattr(namespace, warned, True)
            warnings.warn(
                'Comma-separated --plugin value is deprecated, '
                'use multiple --plugin options instead.'
                )
        values = value.split(',')
        prev = getattr(namespace, self.dest, None)
        if isinstance(prev, list):
            values = prev + values
        setattr(namespace, self.dest, values)


class ArgParse(argparse.ArgumentParser):
    default_directory = os.path.abspath(compat.getcwd())
    default_host = os.getenv('BROWSEPY_HOST', '127.0.0.1')
    default_port = os.getenv('BROWSEPY_PORT', '8080')
    plugin_action_class = PluginAction

    description = 'extendable web file browser'

    def __init__(self, sep=os.sep):
        super(ArgParse, self).__init__(description=self.description)

        self.add_argument(
            'host', nargs='?',
            default=self.default_host,
            help='address to listen (default: %(default)s)')
        self.add_argument(
            'port', nargs='?', type=int,
            default=self.default_port,
            help='port to listen (default: %(default)s)')
        self.add_argument(
            '--directory', metavar='PATH', type=self._directory,
            default=self.default_directory,
            help='base serving directory (default: current path)')
        self.add_argument(
            '--initial', metavar='PATH', type=self._directory,
            help='initial directory (default: same as --directory)')
        self.add_argument(
            '--removable', metavar='PATH', type=self._directory,
            default=None,
            help='base directory for remove (default: none)')
        self.add_argument(
            '--upload', metavar='PATH', type=self._directory,
            default=None,
            help='base directory for upload (default: none)')
        self.add_argument(
            '--exclude', metavar='PATTERN',
            action='append',
            default=[],
            help='exclude paths by pattern (multiple allowed)')
        self.add_argument(
            '--plugin', metavar='MODULE',
            action=self.plugin_action_class,
            default=[],
            help='load plugin module (multiple allowed)')
        self.add_argument('--debug', action='store_true', help='debug mode')

    def _directory(self, arg):
        if not arg:
            return None
        if PY_LEGACY and hasattr(sys.stdin, 'encoding'):
            encoding = sys.stdin.encoding or sys.getdefaultencoding()
            arg = arg.decode(encoding)
        if os.path.isdir(arg):
            return os.path.abspath(arg)
        self.error('%s is not a valid directory' % arg)


def create_exclude_fnc(patterns, base):
    if patterns:
        regex = '|'.join(
            translate(pattern, base=base)
            for pattern in patterns
            )
        print(patterns, regex)
        return re.compile(regex).match
    return None


def main(argv=sys.argv[1:], app=app, parser=ArgParse, run_fnc=flask.Flask.run):
    plugin_manager = app.extensions['plugin_manager']
    args = plugin_manager.load_arguments(argv, parser())
    if args.debug:
        os.environ['DEBUG'] = 'true'
    app.config.update(
        directory_base=args.directory,
        directory_start=args.initial or args.directory,
        directory_remove=args.removable,
        directory_upload=args.upload,
        plugin_modules=args.plugin,
        exclude_fnc=create_exclude_fnc(args.exclude, args.directory)
        )
    plugin_manager.reload()
    run_fnc(
        app,
        host=args.host,
        port=args.port,
        debug=getdebug(),
        use_reloader=False,
        threaded=True
        )


if __name__ == '__main__':
    main()
