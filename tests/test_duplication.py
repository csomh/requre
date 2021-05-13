from tests.testbase import BaseClass
import tempfile
from requre.helpers.simple_object import Simple
from requre.online_replacing import replace


def x():
    return tempfile.mktemp()


class Duplicated(BaseClass):
    @replace("tests.test_duplication.x", decorate=Simple.decorator_plain())
    @replace("tempfile.mktemp", decorate=Simple.decorator_plain())
    def test(self):
        a = x()
        b = tempfile.mktemp()
        self.assertNotEqual(a, b)
