# clize -- A command-line argument parser for Python
# Copyright (C) 2013 by Yann Kaiser <kaiser.yann@gmail.com>
# See COPYING for details.

from __future__ import print_function

import sys
from functools import partial, update_wrapper
import operator

import six
from sigtools.modifiers import annotate, autokwoargs
from sigtools.specifiers import forwards_to_method
from sigtools.signatures import mask

from clize import util, errors, parser

funcsigs = util.funcsigs

class _CliWrapper(object):
    def __init__(self, obj):
        self.obj = obj

    @property
    def cli(self):
        return self.obj

RequireInspect = partial(util.DefinedBy, lambda s: s.inspect())

def cli_commands(obj, namef, clizer):
    cmds = util.OrderedDict()
    cmd_by_name = {}
    for key, val in util.dict_from_names(obj).items():
        if not key:
            continue
        names = tuple(namef(name) for name in util.maybe_iter(key))
        cli = clizer.get_cli(val)
        cmds[names] = cli
        for name in names:
            cmd_by_name[name] = cli
    return cmds, cmd_by_name

class Clize(six.with_metaclass(util.give_attr_name, object)):
    """Wraps a function into a CLI object that accepts command-line arguments
    and translates them to match the wrapped function's parameters."""

    @forwards_to_method('__init__', 1)
    def __new__(cls, fn=None, **kwargs):
        if fn is None:
            return partial(cls, **kwargs)
        else:
            return super(Clize, cls).__new__(cls)

    def __init__(self, fn, owner=None, alt=(),
                 pass_name=False,
                 help_names=('help', 'h'), helper_class=None, hide_help=False):
        """
        :param sequence alt: Alternate actions the CLI will handle.
        :param bool pass_name: Pass the command name as first argument to the
            wrapped function.
        :param help_names: Names to use to trigger the help.
        :type help_names: sequence of strings
        :param helper_class: A callable to produce a helper object to be
            used when the help is triggered. If unset, uses `.ClizeHelp`.
        :type helper_class: a type like `.ClizeHelp`
        :param bool hide_help: Mark the parameters used to trigger the help
            as undocumented.
        """
        update_wrapper(self, fn)
        self.func = fn
        self.owner = owner
        self.alt = util.maybe_iter(alt)
        self.pass_name = pass_name
        self.help_names = help_names
        self.help_aliases = [util.name_py2cli(s, kw=True) for s in help_names]
        self.helper_class = helper_class
        self.hide_help = hide_help

    def parameters(self):
        """Returns the parameters used to instantiate this class, minus the
        wrapped callable."""
        return {
            'owner': self.owner,
            'alt': self.alt,
            'pass_name': self.pass_name,
            'help_names': self.help_names,
            'helper_class': self.helper_class,
            'hide_help': self.hide_help,
            }

    @classmethod
    def keep(cls, fn=None, **kwargs):
        """Instead of wrapping the decorated callable, sets its ``cli``
        attribute to a `.Clize` instance. Useful if you need to use the
        decorator but must still be able to call the function regularily.
        """
        if fn is None:
            return partial(cls.keep, **kwargs)
        else:
            fn.cli = cls(fn, **kwargs)
            return fn

    @classmethod
    def as_is(cls, obj):
        """Returns a CLI object which uses the given callable with no
        translation."""
        return _CliWrapper(obj)

    @classmethod
    def get_cli(cls, obj, **kwargs):
        """Makes an attempt to discover a command-line interface for the
        given object.

        .. _cli-object:

        The process used is as follows:

        1. If the object has a ``cli`` attribute, it is used with no further
           transformation.
        2. If the object is callable, `.Clize` or whichever object this
           class method is used from is used to build a CLI. ``**kwargs`` are
           forwarded to its initializer.
        3. If the object is iterable, `.SubcommandDispatcher` is used on
           the object, and its `cli <.SubcommandDispatcher.cli>` method
           is used.

        Most notably, `clize.run` uses this class method in order to interpret
        the given object(s).
        """
        try:
            cli = obj.cli
        except AttributeError:
            if callable(obj):
                cli = cls(obj, **kwargs)
            else:
                try:
                    iter(obj)
                except TypeError:
                    raise TypeError("Don't know how to build a cli for "
                                    + repr(obj))
                cli = SubcommandDispatcher(obj).cli
        return cli

    @property
    def cli(self):
        """Returns the object itself, in order to be selected by `.get_cli`"""
        return self

    def __repr__(self):
        return '<Clize for {0!r}>'.format(self.func)

    def __get__(self, obj, owner=None):
        try:
            func = self.func.__get__(obj, owner)
        except AttributeError:
            func = self.func
        if func is self.func:
            return self
        params = self.parameters()
        params['owner'] = obj
        return type(self)(func, **params)

    @util.property_once
    def helper(self):
        """A cli object(usually inherited from `.help.Help`) when the user
        requests a help message. See the constructor for ways to affect this
        attribute."""
        if self.helper_class is None:
            from clize.help import ClizeHelp as class_
        else:
            class_ = self.helper_class
        return class_(self, self.owner)

    @util.property_once
    def signature(self):
        """The `.parser.CliSignature` object used to parse arguments."""
        return parser.CliSignature.from_signature(
            mask(util.funcsigs.signature(self.func), self.pass_name),
            extra=self._process_alt(self.alt))

    def _process_alt(self, alt):
        if self.help_names:
            p = parser.FallbackCommandParameter(
                func=self.helper.cli, undocumented=self.hide_help,
                aliases=self.help_aliases)
            yield p

        for name, func in util.dict_from_names(alt).items():
            func = self.get_cli(func)
            param = parser.AlternateCommandParameter(
                undocumented=False, func=func,
                aliases=[util.name_py2cli(name, kw=True)])
            yield param

    def __call__(self, *args):
        with errors.SetUserErrorContext(cli=self, pname=args[0]):
            func, name, posargs, kwargs = self.read_commandline(args)
            return func(*posargs, **kwargs)

    def read_commandline(self, args):
        """Reads the command-line arguments from args and returns a tuple
        with the callable to run, the name of the program, the positional
        and named arguments to pass to the callable.

        :raises: `.ArgumentError`
        """
        func, post, posargs, kwargs = self.signature.read_arguments(args[1:])
        name = ' '.join([args[0]] + post)
        if func or self.pass_name:
            posargs.insert(0, name)
        return func or self.func, name, posargs, kwargs

def _dispatcher_helper(*args, **kwargs):
    """alias for clize.help.DispatcherHelper, avoiding circular import"""
    from clize.help import DispatcherHelper
    return DispatcherHelper(*args, **kwargs)

def make_dispatcher_helper(*args, **kwargs):
    from clize.help import DispatcherHelper
    return DispatcherHelper(*args, **kwargs)

class SubcommandDispatcher(object):
    clizer = Clize

    def __init__(self, commands=()):
        self.cmds, self.cmds_by_name = cli_commands(
            commands, namef=util.name_py2cli, clizer=self.clizer)

    @Clize(pass_name=True, helper_class=make_dispatcher_helper)
    @annotate(command=(operator.methodcaller('lower'),
                       parser.Parameter.LAST_OPTION),
              args=parser.Parameter.EAT_REST)
    def cli(self, name, command, *args):
        try:
            func = self.cmds_by_name[command]
        except KeyError:
            raise errors.ArgumentError('Unknwon command "{0}"'.format(command))
        return func('{0} {1}'.format(name, command), *args)

@autokwoargs
def run(args=None, catch=(), exit=True, out=None, err=None, *fn, **kwargs):
    """Runs a function or :ref:`CLI object<cli-object>` with ``args``, prints
    the return value if not None, or catches the given exception types as well
    as `clize.UserError` and prints their string representation, then exit with
    the appropriate status code.

    :param sequence args: The arguments to pass the CLI, for instance
        ``('./a_script.py', 'spam', 'ham')``. If unspecified, uses `sys.argv`.
    :param catch: Catch these exceptions and print their string representation
        rather than letting python print an uncaught exception traceback.
    :type catch: sequence of exception classes
    :param bool exit: If true, exit with the appropriate status code once the
        function is done.
    :param file out: The file in which to print the return value of the
        command. If unspecified, uses `sys.stdout`
    :param file err: The file in which to print any exception text.
        If unspecified, uses `sys.stderr`.

    """
    if len(fn) == 1:
        fn = fn[0]
    cli = Clize.get_cli(fn, **kwargs)

    if args is None:
        args = sys.argv
    if out is None:
        out = sys.stdout
    if err is None:
        err = sys.stderr

    try:
        ret = cli(*args)
    except tuple(catch) + (errors.UserError,) as exc:
        print(str(exc), file=err)
        if exit:
            sys.exit(2 if isinstance(exc, errors.ArgumentError) else 1)
    else:
        if ret is not None:
            print(ret, file=out)
        if exit:
            sys.exit()
