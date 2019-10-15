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

import os
from _collections_abc import Hashable
from typing import Dict, List, Any, Optional

import yaml

from .exceptions import PersistentStorageException
from .singleton import SingletonMeta
from .constants import VERSION_REQURE_FILE


class PersistentObjectStorage(metaclass=SingletonMeta):
    """
    Class implements reading/writing simple JSON requests to dict structure
    and return values based on keys.
    It contains methods to reads/stores data to object and load and store them to YAML file

    storage_object: dict with structured data based on keys (eg. simple JSON requests)
    storage_file: file for reading and writing data in storage_object
    """

    internal_object_key = "_requre"
    version_key = "version_storage_file"

    def __init__(self) -> None:
        # call dump() after store() is called
        self.dump_after_store = False
        self._is_write_mode: bool = False
        self.is_flushed = True
        self.storage_object: dict = {}
        self._storage_file: Optional[str] = None

        storage_file_from_env = os.getenv("RESPONSE_FILE")
        if storage_file_from_env:
            self.storage_file = storage_file_from_env

    @property
    def requre_internal_object(self):
        """
        Placeholder to store some custom configuration, or store custom data,
        eg. version of storage file, or some versions of packages

        :return: dict
        """
        return self.storage_object.get(self.internal_object_key, {})

    @requre_internal_object.setter
    def requre_internal_object(self, key_dict: dict):
        if self.internal_object_key not in self.storage_object:
            self.storage_object[self.internal_object_key] = {}
        for k, v in key_dict.items():
            self.storage_object[self.internal_object_key][k] = v

    @property
    def storage_file_version(self):
        """
        Get version of persistent storage file
        :return: int
        """
        return self.requre_internal_object.get(self.version_key, 0)

    @storage_file_version.setter
    def storage_file_version(self, value: int):
        self.requre_internal_object = {self.version_key: value}

    @property
    def storage_file(self):
        return self._storage_file

    @storage_file.setter
    def storage_file(self, value):
        self._storage_file = value
        self._is_write_mode = not os.path.exists(self._storage_file)
        if self.is_write_mode:
            self.is_flushed = False
            self.storage_object = {}
        else:
            self.storage_object = self.load()

    @property
    def is_write_mode(self):
        return self._is_write_mode

    @staticmethod
    def transform_hashable(keys: List) -> List:
        output: List = []
        for item in keys:
            if not item:
                output.append("empty")
            elif not isinstance(item, Hashable):
                output.append(str(item))
            else:
                output.append(item)
        return output

    def store(self, keys: List, values: Any) -> None:
        """
        Stores data to dictionary object based on keys values it will create structure
        if structure does not exist

        It implicitly changes type to string if key is not hashable

        :param keys: items what will be used as keys for dictionary
        :param values: It could be whatever type what is used in original object handling
        :return: None
        """

        current_level = self.storage_object
        hashable_keys = self.transform_hashable(keys)
        for item_num in range(len(hashable_keys)):
            item = hashable_keys[item_num]
            if item_num + 1 < len(hashable_keys):
                if not current_level.get(item):
                    current_level[item] = {}
            else:
                current_level.setdefault(item, [])
                current_level[item].append(values)

            current_level = current_level[item]
        self.is_flushed = False

        if self.dump_after_store:
            self.dump()

    def read(self, keys: List) -> Any:
        """
        Reads data from dictionary object structure based on keys.
        If keys does not exists

        It implicitly changes type to string if key is not hashable

        :param keys: key list for searching in dict
        :return: value assigged to key items
        """
        current_level = self.storage_object
        hashable_keys = self.transform_hashable(keys)
        for item in hashable_keys:

            if item not in current_level:
                raise PersistentStorageException(
                    f"Keys not in storage:{self.storage_file} {hashable_keys}"
                )

            current_level = current_level[item]

        if len(current_level) == 0:
            raise PersistentStorageException(
                "No responses left. Try to regenerate response files."
            )

        result = current_level[0]
        del current_level[0]
        return result

    def dump(self) -> None:
        """
        Explicitly stores content of storage_object to storage_file path

        This method is also called when object is deleted and is set write mode to True

        :return: None
        """
        if self.is_write_mode:
            if self.is_flushed:
                return None
            # dump current version of storage file to storage file
            self.storage_file_version = VERSION_REQURE_FILE
            with open(self.storage_file, "w") as yaml_file:
                yaml.dump(self.storage_object, yaml_file, default_flow_style=False)
            self.is_flushed = True

    def load(self) -> Dict:
        """
        Explicitly loads file content of storage_file to storage_object and return as well

        :return: dict
        """
        with open(self.storage_file, "r") as yaml_file:
            output = yaml.safe_load(yaml_file)
        self.storage_object = output
        return output


def use_persistent_storage_without_overwriting(cls):
    class ClassWithPersistentStorage(cls):
        persistent_storage: Optional[
            PersistentObjectStorage
        ] = PersistentObjectStorage()

    ClassWithPersistentStorage.__name__ = cls.__name__
    return ClassWithPersistentStorage


class StorageCounter:
    counter = 0
    dir_suffix = "file_storage"
    previous = None

    @classmethod
    def reset_counter_if_changed(cls):
        current = os.path.basename(PersistentObjectStorage().storage_file)
        if cls.previous != current:
            cls.counter = 0
            cls.previous = current

    @classmethod
    def next(cls):
        cls.counter += 1
        return cls.counter

    @staticmethod
    def storage_file():
        return os.path.basename(PersistentObjectStorage().storage_file)

    @staticmethod
    def storage_dir():
        return os.path.dirname(PersistentObjectStorage().storage_file)
