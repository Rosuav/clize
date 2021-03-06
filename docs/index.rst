**************************************************
clize: Turn functions into command-line interfaces
**************************************************

Clize is an argument parser for `Python <https://www.python.org/>`_. It focuses on minimizing the effort required to create them:

* Command-line interfaces are created by passing functions to `clize.run`.
* Parameter types are deduced from the functions' parameters.
* A ``--help`` message is generated from your docstrings. Seriously, why does
  this still need to be a bullet point?
* Decorators can be used to reuse functionality across functions.
* Clize can be extended with new parameter behavior.

Here's an example:

.. literalinclude:: /../examples/hello.py
   :emphasize-lines: 2,20

.. warning::

    These docs refer to an in-development version of clize. The instructions here will NOT work on the latest stable version, Clize 2.4. You can use the following command to install a compatible version:

    .. code-block:: console

        $ pip install --user --pre 'clize<=3'

`~clize.run` takes the function and automatically produces a command-line
interface for it:

.. code-block:: console

    $ pip install --user clize
    $ python examples/hello.py --help
    Usage: examples/hello.py [OPTIONS] [name]

    Greets the world or the given name.

    Positional arguments:
      name              If specified, only greet this person.

    Options:
      --no-capitalize   Don't capitalize the give name.

    Other actions:
      -h, --help        Show the help
    $ python hello.py
    Hello world!
    $ python hello.py john
    Hello John!
    $ python hello.py --no-capitalize
    Hello john!


.. rubric:: Interested?

* Follow the :ref:`tutorial <basics>`
* Browse the |examples_url|_
* Check out :ref:`why Clize was made <why>`
* Star, watch or fork `Clize on GitHub <https://github.com/epsy/clize>`_

.. only:: html

    Here is the full table of contents:


.. _about:

About Clize
-----------

.. toctree::
    :maxdepth: 1

    why
    history
    faq


.. _tutorial:

Getting started
---------------

This section contains tutorials for the most commonly used features of Clize.

.. toctree::

    basics
    dispatching
    compositing


.. _guides:

Guides
------

These documents document specific aspects or usages of Clize.

.. toctree::

    parser
    porting
    interop


.. _references:

Reference
---------

The user reference lists all capabilities of each kind of parameter. The API reference comes in handy if you're extending clize.

.. toctree::

    reference
    api
