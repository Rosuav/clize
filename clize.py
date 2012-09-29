# clize - See COPYING for copyright info.
# -*- coding: utf-8 -*

from __future__ import print_function, unicode_literals

from functools import wraps
from collections import namedtuple
import re
from textwrap import TextWrapper

import sys
import os
import inspect
from gettext import gettext as _, ngettext as _n

if not hasattr(inspect, 'FullArgSpec'):
    FullArgSpec = namedtuple(
        'FullArgSpec',
        (
            'args', 'varargs', 'varkw', 'defaults',
            'kwonlyargs', 'kwonlydefaults', 'annotations'
            )
        )
    def getfullargspec(func):
        argspec = inspect.getargspec(func)
        return FullArgSpec(
            argspec.args,
            argspec.varargs,
            argspec.keywords,
            argspec.defaults,
            [], None, {}
            )
else:
    getfullargspec = inspect.getfullargspec

try:
    basestring
except NameError:
    basestring = str
    unicode = str
    decode = lambda s: s
else:
    decode = lambda s: s.decode('utf8')

class ArgumentError(TypeError):

    def __str__(self):
        return str(((self.args[0] + '\n') if self.args[0] else '')
            + help(self.args[2], self.args[1],
                   just_do_usage=True, do_print=False))

Option = namedtuple(
    'Option',
    (
        'source',
        'names',
        'default',
        'type',
        'help',
        'optional',
        'positional',
        'takes_argument',
        'catchall',
        )
    )

def make_flag(
        source,
        names,
        default=False,
        type=bool,
        help='',
        takes_argument=0,
        ):
    return Option(
        source, names, default, type, help,
        optional=True, positional=False,
        takes_argument=takes_argument, catchall=False
        )

Command = namedtuple(
    'Command',
    (
        'description',
        'footnotes',
        'posargs',
        'options',
        )
    )

SuperCommand = namedtuple(
    'SuperCommand',
    (
        'description',
        'footnotes',
        'subcommands',
        )
    )

argdesc = re.compile('^(\w+): (.*)$', re.DOTALL)

def read_docstring(fn):
    doc = inspect.getdoc(fn)
    description = []
    footnotes = []
    opts_help = {}

    if doc:
        for paragraph in doc.split('\n\n'):
            m = argdesc.match(paragraph)

            if m:
                optname, desc = m.groups()
                opts_help[optname] = desc
            else:
                if opts_help:
                    footnotes.append(paragraph)
                else:
                    description.append(paragraph)

    return description, opts_help, footnotes

def annotation_aliases(annotations):
    return tuple(filter(lambda s: isinstance(s, str) and (' ' not in s),
                  annotations))

def read_annotations(annotations, source):
    alias = []
    flags = []
    coerce = None

    try:
        iter(annotations)
    except TypeError:
        annotations = (annotations,)
    else:
        if isinstance(annotations, basestring):
            annotations = (annotations,)

    for i, annotation in enumerate(annotations):
        if isinstance(annotation, int):
            flags.append(annotation)
        elif isinstance(annotation, basestring):
            if ' ' not in annotation:
                alias.append(annotation)
            else:
                raise ValueError(
                    "Aliases may not contain spaces. "
                    "Put argument descriptions in the docstring."
                    )
        elif callable(annotation):
            if coerce is not None:
                raise ValueError(
                    "Coercion function already encountered before "
                    "index {0} of annotation on {1}: {2!r}"
                    .format(i, source, annotation)
                    )
            coerce = annotation
        else:
            raise ValueError(
                "Don't know how to interpret index {0} of "
                "annotation on {1}: {2!r}"
                .format(i, source, annotation)
                )

    return tuple(alias), tuple(flags), coerce

def read_arguments(fn, alias, force_positional, require_excess, coerce):
    argspec = getfullargspec(fn)
    description, opts_help, footnotes = read_docstring(fn)

    posargs = []
    options = []

    for i, argname in enumerate(argspec.args):
        annotations = argspec.annotations.get(argname, ())
        alias_, flags_, coerce_ = read_annotations(annotations, argname)
        if not coerce_:
            coerce_ = coerce.get(argname, coerce_)

        try:
            default = argspec.defaults[-len(argspec.args) + i]
        except (IndexError, TypeError):
            default = None
            optional = False
            type_ = coerce_ or unicode
        else:
            optional = True
            type_ = coerce_ or type(default)

        positional = not optional
        if (
                argname in force_positional
                or clize.POSITIONAL in flags_
                ):
            positional = True

        if positional and options and options[-1].optional:
            optional = True

        option = Option(
            source=argname,
            names=
                (argname.replace('_', '-'),)
                + alias.get(argname, ())
                + alias_,
            default=default,
            type=type_,
            help=opts_help.get(argname, ''),
            optional=optional,
            positional=positional,
            takes_argument=int(optional and type_ != bool),
            catchall=False,
            )
        if positional:
            posargs.append(option)
        else:
            options.append(option)

    if argspec.varargs:
        posargs.append(
            Option(
                source=argspec.varargs,
                names=(argspec.varargs.replace('_', '-'),),
                default=None,
                type=unicode,
                help=opts_help.get(argspec.varargs, ''),
                optional=bool(not require_excess or posargs and posargs[-1].optional),
                positional=True,
                takes_argument=False,
                catchall=True,
            )
        )

    return Command(
        description=tuple(description), footnotes=tuple(footnotes),
        posargs=posargs, options=options)

def get_arg_name(arg):
    name = arg.names[0] + (arg.catchall and '...' or '')
    return (arg.optional and '[' + name + ']'
            or name)

def get_type_name(func):
    return (
            'STR' if func in (unicode, str)
            else
            func.__name__.upper()
        )

def get_option_names(option):
    shorts = []
    longs = []

    for name in option.names:
        if option.positional:
            longs.append(name)
        elif len(name) == 1:
            shorts.append('-' + name)
        else:
            longs.append('--' + name)

    if ((not option.positional and option.type != bool)
            or (option.positional and option.type != unicode)):
        longs[-1] += '=' + get_type_name(option.type)

    if option.positional and option.catchall:
        longs[-1] += '...'

    return ', '.join(shorts + longs)

def get_terminal_width():
    return 70 #fair terminal dice roll

def get_default_for_printing(default):
    ret = repr(default)
    if isinstance(default, unicode) and ret[0] == 'u':
        return ret[1:]
    return ret

def print_arguments(arguments, width=None):
    if width == None:
        width = 0
        for arg in arguments:
            width = max(width, len(get_option_names(arg)))

    help_wrapper = TextWrapper(
        width=get_terminal_width(),
        initial_indent=' ' * (width + 5),
        subsequent_indent=' ' * (width + 5),
        )

    return ('\n'.join(
        ' ' * 2 + '{0:<{width}}  {1}'.format(
            get_option_names(arg),
            help_wrapper.fill(
                arg.help +
                    (_('(default: {0})').format(arg.default)
                     if arg.default not in (None, False)
                     else ''
                    )
            )[width + 4:]
                if arg.help else '',
            width=width,
        ) for arg in arguments))

def help(name, command, just_do_usage=False, do_print=True, **kwargs):
    ret = ""
    ret += (_('Usage: {name}{options} {args}').format(
        name=name + (' command' if 'subcommands' in command._fields
                     else ''),
        options=(
            _(' [OPTIONS]')
                if 'options' not in command._fields
                    or command.options
            else ''),
        args=(
            ' '.join(get_arg_name(arg) for arg in command.posargs)
                if 'posargs' in command._fields else ''
            ),
        ))

    if just_do_usage:
        if do_print:
            print(ret)
        return ret

    tw = TextWrapper(
        width=get_terminal_width()
        )

    ret += '\n\n'.join(
        tw.fill(p) for p in ('',) + command.description) + '\n'
    if 'subcommands' in command._fields and command.subcommands:
        ret += '\n' + _('Available commands:') + '\n'
        ret += print_arguments(command.subcommands) + '\n'
    if 'posargs' in command._fields and command.posargs:
        ret += '\n' + _('Positional arguments:') + '\n'
        ret += print_arguments(command.posargs) + '\n'
    if 'options' in command._fields and command.options:
        ret += '\n' + _('Options:') + '\n'
        ret += print_arguments(command.options) + '\n'
    if 'subcommands' in command._fields and command.subcommands:
        ret += '\n' + tw.fill(_(
            "See '{0} command --help' for more information "
            "on a specific command.").format(name)) + '\n'
    if command.footnotes:
        ret += '\n' + '\n\n'.join(tw.fill(p) for p in command.footnotes)
        ret += '\n'

    if do_print:
        print(ret)

    return ret

def get_option(name, list):
    for option in list:
        if name in option.names:
            return option
    raise KeyError

def coerce_option(val, option, key, command, name):
    try:
        return option.type(val)
    except ValueError:
        key = (len(key) == 1 and '-' + key) or ('--' + key)
        raise ArgumentError(_("{0} needs an argument of type {1}")
            .format(key, option.type.__name__.upper()),
            name, command
            )

def set_arg_value(val, option, key, params, name, command):
    if callable(option.source):
        return option.source(name=name, command=command,
                             val=val, params=params)
    else:
        params[option.source] = coerce_option(
            val, option, key, name, command)

def get_following_arguments(i, option, input, key, command, name):
    if i + option.takes_argument >= len(input):
        raise ArgumentError(
            _n("--{0} needs an argument.",
               "--{0} needs {1} arguments.",
               option.takes_argument)
            .format(key, option.takes_argument),
            command, name
            )

    if option.catchall:
        val_ = input[i+1:]
    else:
        val_ = input[
            i+1:i+option.takes_argument+1]

    return len(val_), ' '.join(val_)

def clize(
        fn=None,
        alias={},
        help_names=('help', 'h'),
        force_positional=(),
        coerce={},
        require_excess=False,
        extra=()
    ):
    def _wrapperer(fn):
        @wraps(fn)
        def _getopts(*input):
            command = read_arguments(
                fn,
                alias, force_positional,
                require_excess, coerce
                )

            if help_names:
                help_option = make_flag(
                    source=help,
                    names=help_names,
                    help=_("Show this help"),
                    )
                command.options.append(help_option)

            command.options.extend(extra)

            name = input[0]
            input = input[1:]

            kwargs = {}
            args = []

            skip_next = 0
            for i, arg in enumerate(input):
                if skip_next:
                    skip_next -= 1
                    continue

                arg = decode(arg)
                if arg.startswith('--'):
                    if len(arg) == 2:
                        args.extend(input[i+1:])
                        break

                    keyarg = arg[2:].split('=', 1)
                    try:
                        option = get_option(keyarg[0], command.options)
                    except KeyError:
                        raise ArgumentError(
                            _("Unrecognized option {0}").format(arg),
                            command,
                            name
                            )
                    else:
                        if option.takes_argument or option.catchall:
                            try:
                                key, val = keyarg
                            except ValueError:
                                key = keyarg[0]

                                skip_next, val = get_following_arguments(
                                    i, option, input, key, command, name
                                    )
                        else:
                            key = keyarg[0]
                            val = True
                        if set_arg_value(
                                val, option, key,
                                kwargs,
                                name, command
                                ):
                            return
                elif arg.startswith('-'):
                    skip_next_ = 0
                    for j, c in enumerate(arg[1:]):
                        if skip_next_:
                            skip_next_ -= 1
                            continue

                        try:
                            option = get_option(c, command.options)
                        except KeyError:
                            raise ArgumentError(_("Unknown option -{0}.").format(c),
                                                command, name)
                        else:
                            if option.takes_argument:
                                if len(arg) > 2+j:
                                    if option.type == int:
                                        val = ""
                                        for k in range(2+j, len(arg)):
                                            if k == 2+j and arg[k] == '-':
                                                val += '-'
                                            elif '0' <= arg[k] and arg[k] <= '9':
                                                val += arg[k]
                                            else:
                                                break
                                    else:
                                        val = arg[2+j:]
                                    skip_next_ = len(val)
                                else:
                                    skip_next, val = get_following_arguments(
                                        i, option, input, option.source, command, name
                                        )
                            else:
                                val = True

                            if set_arg_value(
                                    val, option, c,
                                    kwargs,
                                    name, command
                                    ):
                                return
                else:
                    args.append(arg)

            for i, option in enumerate(command.posargs):
                if i >= len(args):
                    if option.optional:
                        if not option.catchall:
                            args.append(option.default)
                    else:
                        raise ArgumentError(_("Not enough arguments."), command, name)
                if not option.catchall:
                    args[i] = option.type(args[i])


            if len(args) != len(command.posargs):
                if (not command.posargs
                   or not command.posargs[-1].catchall):
                    raise ArgumentError(_("Too many arguments."), command, name)

            for option in command.options:
                if not callable(option.source):
                    kwargs.setdefault(option.source, option.default)

            fn_args = getfullargspec(fn).args
            for i, key in enumerate(fn_args):
                if key in kwargs:
                    args.insert(i, kwargs[key])

            return fn(*args)
        return _getopts

    if fn == None:
        return _wrapperer
    else:
        return _wrapperer(fn)
clize.POSITIONAL = 1

def read_supercommand(fnlist, description, footnotes, help_names):
    subcommands = dict((f.__name__, f) for f in fnlist)
    supercommand = SuperCommand(
        description=tuple(
            x for x in inspect.cleandoc(description).split('\n\n') if x),
        footnotes=tuple(
            x for x in inspect.cleandoc(footnotes).split('\n\n') if x),
        subcommands=[
            Option(
                source=name,
                help=(read_docstring(subcommands[name])[0] or ('',))[0],
                default=None,
                optional=False,
                positional=True,
                names=(name,),
                type=type(''),
                takes_argument=False,
                catchall=False
            ) for name in subcommands]
        )
    return subcommands, supercommand

def run_group(fnlist, args, description='', footnotes='', help_names=()):
    subcommands, supercommand = read_supercommand(
        fnlist, description, footnotes, help_names)
    args = list(args)
    # grab the first positional argument
    for i, arg in enumerate(args[1:]):
        if not arg.startswith('-'):
            if arg not in subcommands:
                raise ArgumentError(
                    _("Unknown command '{0}'").format(arg),
                    supercommand, args[0]
                    )
            # change the command name to be both argv[0] and the
            # subcommand name
            args[0] = args[0] + ' ' + arg
            del args[i+1]
            return subcommands[arg](*args)
            break
    else: # Either no arguments or only options
        for arg in args[1:]:
            if arg.lstrip('-') in help_names:
                help(args[0], supercommand)
                return
        else: # no --help argument
            if len(args) > 1:
                raise ArgumentError(
                    _('No command specified.'), supercommand, args[0])
            else:
                raise ArgumentError(None, supercommand, args[0])

def run_single(fn, args):
    fn(*args)

def run(fn, args=None,
        description="", footnotes="",
        help_names=('help', 'h')):

    args = args if args is not None else sys.argv

    try:
        try:
            fn.__iter__
        except AttributeError:
            run_single(fn, args)
        else:
            run_group(fn, args, description, footnotes, help_names)
    except ArgumentError as e:
        if e.args[0]:
            print(os.path.basename(args[0]) + ': '
                    + unicode(e), file=sys.stderr)
        else:
            print(unicode(e) + '\n' +
                _("Try '{0} --{1}' for more information.").format(
                    args[0], help_names[0]
                    ),
                file=sys.stderr)
            sys.exit(2)
