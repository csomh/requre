# MIT License
#
# Copyright (c) 2018-2019 Red Hat, Inc.

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import builtins
import functools
import inspect
import re
from enum import Enum
from importlib import reload
from typing import Optional, Dict, List

from requre.utils import Replacement


class ReplaceType(Enum):
    """
    Types for import system what are used in replacement list, to know ho to replace it:
    DECORATOR: decorate original function
    REPLACE: replace object by another one
    REPLACE_MODULE: replace whole module by another implementation
    """

    DECORATOR = 1
    REPLACE = 2
    REPLACE_MODULE = 3


def upgrade_import_system(filters=None, debug_file: Optional[str] = None) -> None:
    """
    High level upgrade import function.

    :param filters: list of filters, for examples see: tests/test_import_system.py
    :param debug_file: file where to store debug information about replacements
    """
    UpgradeImportSystem(filters=filters, debug_file=debug_file).upgrade_import_system()


def decorate(where, what, decorator, who_name=None) -> "UpgradeImportSystem":
    upgraded_import_system = UpgradeImportSystem()
    upgraded_import_system.decorate(
        where=where, what=what, decorator=decorator, who_name=who_name
    )
    return upgraded_import_system


class UpgradeImportSystem:
    def __init__(
        self, filters: Optional[List] = None, debug_file: Optional[str] = None
    ) -> None:
        self.filters = filters or []
        self.debug_file = debug_file
        self._original_import = None
        self.replace_dict: Dict[str, Dict[str, Replacement]] = {}

    def __enter__(self):
        self._original_import = builtins.__import__
        self.replace_dict.clear()
        self.upgrade_import_system()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        builtins.__import__ = self._original_import
        for key_with_replacements in self.replace_dict.values():
            for replacement in key_with_replacements.values():
                reload(replacement.parent)
        self.replace_dict.clear()

    def decorate(self, where, what, decorator, who_name=None) -> "UpgradeImportSystem":
        who_options = {}
        if who_name:
            who_options["who_name"] = who_name
        self.filters.append(
            (where, who_options, {what: [ReplaceType.DECORATOR, decorator]})
        )
        return self

    def upgrade_import_system(self):
        self._upgrade_import_system(builtins.__import__)

    def _upgrade_import_system(self, func):
        @functools.wraps(func)
        def new_import(*args, **kwargs):

            out = func(*args, **kwargs)
            name = list(args)[0]

            for filter_item in self.filters:
                one_filter = filter_item[0]
                additional_filters = filter_item[1]
                if re.search(one_filter, name):
                    mod = inspect.getmodule(inspect.stack()[1][0])
                    fromlist = ()
                    if len(args) > 3:
                        fromlist = list(args)[3]
                    module_name = getattr(mod, "__name__", "")
                    module_file = getattr(mod, "__file__", "")
                    item = {
                        "module_object": out,
                        "who": mod,
                        "who_name": module_name,
                        "who_filename": module_file,
                        "fromlist": fromlist,
                    }

                    if all(
                        [re.search(v, item[k]) for k, v in additional_filters.items()]
                    ):
                        text = list()
                        text.append(
                            f"{module_name} ({module_file})-> {name} ({fromlist})\n"
                        )
                        if len(filter_item) > 2:
                            for key, replacement in filter_item[2].items():
                                replace_type = replacement[0]
                                replace_object = replacement[1]
                                original_obj = out
                                parent_obj = out
                                # avoid multiple replacing, just in case of module,
                                # because python import system has check
                                # so in case of module it has to be replaced everytime.
                                if (
                                    key in self.replace_dict.get(name, {})
                                    and replace_type is not ReplaceType.REPLACE_MODULE
                                ):
                                    text.append(
                                        f"\t{key} in module {name} already replaced: "
                                        f"{one_filter} -> {key}  by {replacement}\n"
                                    )
                                else:
                                    # traverse into
                                    if len(key) > 0:
                                        for key_item in key.split("."):
                                            parent_obj = original_obj
                                            original_obj = getattr(
                                                original_obj, key_item
                                            )

                                    self.replace_dict.setdefault(name, {})
                                    self.replace_dict[name][key] = Replacement(
                                        name=name,
                                        key=key,
                                        one_filter=one_filter,
                                        replacement=replacement,
                                        parent=parent_obj,
                                    )

                                    if replace_type == ReplaceType.REPLACE:
                                        setattr(
                                            parent_obj,
                                            original_obj.__name__,
                                            replace_object,
                                        )
                                        text.append(
                                            f"\treplacing {key} "
                                            f"by function {replace_object.__name__}\n"
                                        )
                                    elif replace_type == ReplaceType.DECORATOR:
                                        setattr(
                                            parent_obj,
                                            original_obj.__name__,
                                            replace_object(original_obj),
                                        )
                                        text.append(
                                            f"\tdecorate {key}  by {replace_object.__name__}\n"
                                        )
                                    elif replace_type == ReplaceType.REPLACE_MODULE:
                                        out = replace_object
                                        text.append(
                                            f"\treplace module {name} in {module_name} "
                                            f"by {replace_object.__name__}\n"
                                        )
                        if self.debug_file:
                            with open(self.debug_file, "a") as fd:
                                fd.write("".join(text))
            return out

        builtins.__import__ = new_import
